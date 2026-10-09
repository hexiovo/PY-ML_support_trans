"""Per-file-isolated batch conversion and optional validated merge."""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
import json
import os
from pathlib import Path
import threading
from typing import Any

from . import api
from .core import ConversionError, _convert_document, file_sha256, load_source_document
from .matlab_bridge import MatlabBridgeCancelled
from .writers import WriterError, write_mlinput


def _is_within(path: Path, directory: Path) -> bool:
    try:
        path.resolve().relative_to(directory.resolve())
        return True
    except ValueError:
        return False


def _discover_inputs(request: api.BatchRequest) -> tuple[Path, ...]:
    output_dir = Path(request.output_dir).expanduser().resolve()
    found: list[Path] = []
    seen: set[Path] = set()
    for raw in request.input_paths:
        path = Path(raw).expanduser().resolve()
        if path.is_file():
            candidates = (path,)
        elif path.is_dir():
            candidates_list: list[Path] = []
            if request.recursive:
                for root, directories, files in os.walk(path):
                    root_path = Path(root).resolve()
                    directories[:] = sorted(
                        name for name in directories
                        if not _is_within(root_path / name, output_dir)
                        and not (root_path / name).is_symlink()
                    )
                    candidates_list.extend(root_path / name for name in sorted(files))
            else:
                candidates_list.extend(path / name for name in sorted(p.name for p in path.iterdir() if p.is_file()))
            candidates = tuple(candidates_list)
        else:
            raise ConversionError(f"Input path does not exist or is not a file/directory: {path}")
        for candidate in candidates:
            if candidate.suffix.lower() not in {".mat", ".json"}:
                continue
            resolved = candidate.resolve()
            if _is_within(resolved, output_dir) or resolved in seen:
                continue
            seen.add(resolved)
            found.append(resolved)
    # Keep caller order for explicit file paths; directory candidates were
    # already sorted within each directory above.
    if not found:
        raise ConversionError("No .mat or .json input files were found outside the output directory")
    return tuple(found)


def _emit(
    callback: Callable[[api.ProgressEvent], None] | None,
    index: int,
    total: int,
    source: Path,
    phase: str,
    percent: float,
    message: str,
) -> None:
    if callback is None:
        return
    try:
        callback(api.ProgressEvent(index, total, source, phase, max(0.0, min(100.0, percent)), message))
    except Exception:
        # A UI observer must not cause a data file to be lost or partially written.
        return


def _convert_one(
    source: Path,
    request: api.BatchRequest,
    cancel_event: threading.Event,
) -> Mapping[str, Any]:
    document, adapter_id = load_source_document(
        source,
        source_adapter_id=request.selection.source_adapter_id,
        matlab_executable=request.matlab_executable,
        cancel_event=cancel_event,
    )
    return _convert_document(
        document,
        request.selection,
        adapter_id=adapter_id,
        source_fingerprint=file_sha256(source),
        source_path=source,
    )


def _output_path(output_dir: Path, base_name: str, output_format: str) -> Path:
    if output_format == "csv":
        return output_dir / base_name
    return output_dir / f"{base_name}.xlsx"


def _exists(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def _available_path(output_dir: Path, base_name: str, output_format: str) -> tuple[Path, bool]:
    candidate = _output_path(output_dir, base_name, output_format)
    return candidate, _exists(candidate)


def _rename_candidate(output_dir: Path, base_name: str, output_format: str, start: int = 2) -> tuple[Path, int]:
    index = start
    while index < 100_000:
        candidate = _output_path(output_dir, f"{base_name}_{index}", output_format)
        if not _exists(candidate):
            return candidate, index + 1
        index += 1
    raise WriterError(f"Cannot find a free output name for {base_name!r}")


def _write_payload(
    payload: Mapping[str, Any],
    output_dir: Path,
    base_name: str,
    request: api.BatchRequest,
) -> tuple[tuple[Path, ...] | None, bool]:
    """Return paths and whether a collision-policy skip was selected."""
    output_dir.mkdir(parents=True, exist_ok=True)
    candidate, exists = _available_path(output_dir, base_name, request.selection.output_format)
    if exists and request.selection.collision_policy == "skip":
        return None, True
    next_index = 2
    if exists:
        candidate, next_index = _rename_candidate(
            output_dir, base_name, request.selection.output_format
        )
    while True:
        try:
            paths = write_mlinput(
                payload,
                candidate,
                output_format=request.selection.output_format,
            )
            return paths, False
        except FileExistsError:
            if request.selection.collision_policy == "skip":
                return None, True
            candidate, next_index = _rename_candidate(
                output_dir, base_name, request.selection.output_format, next_index
            )


def _stable(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=True)


def _merge_payloads(payloads: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not payloads:
        raise ConversionError("No successfully converted files are available to merge")
    first = payloads[0]
    invariant_fields = ("FeatureIDs", "FeatureDefinitions")
    for index, current in enumerate(payloads[1:], start=2):
        for field in invariant_fields:
            if _stable(current[field]) != _stable(first[field]):
                raise ConversionError(f"Merge conflict in {field} for input {index}; refusing reorder, intersection, or zero-fill")
        first_provenance = first["Provenance"]
        current_provenance = current["Provenance"]
        for field in (
            "source_adapter_id",
            "target_mappings",
            "covariate_mappings",
            "identity_mapping",
        ):
            if _stable(current_provenance.get(field)) != _stable(first_provenance.get(field)):
                raise ConversionError(f"Merge conflict in explicit mapping {field} for input {index}")
        if tuple(current["Targets"]) != tuple(first["Targets"]):
            raise ConversionError(f"Merge conflict in target column names for input {index}")
        if tuple(current["Covariates"]) != tuple(first["Covariates"]):
            raise ConversionError(f"Merge conflict in covariate column names for input {index}")

    merged: dict[str, Any] = {
        "schema_version": first["schema_version"],
        "X": [],
        "FeatureIDs": list(first["FeatureIDs"]),
        "Samples": [],
        "Targets": {name: [] for name in first["Targets"]},
        "Covariates": {name: [] for name in first["Covariates"]},
        "FeatureDefinitions": list(first["FeatureDefinitions"]),
        "ValidMask": [],
        "MissingReasons": [],
    }
    seen_ids: set[str] = set()
    for payload in payloads:
        for sample in payload["Samples"]:
            observation_id = sample.get("ObservationID")
            observation_value = observation_id.get("value") if isinstance(observation_id, Mapping) else observation_id
            if observation_value in seen_ids:
                raise ConversionError(f"Duplicate ObservationID across merged sources: {observation_value!r}")
            seen_ids.add(str(observation_value))
        merged["X"].extend(payload["X"])
        merged["Samples"].extend(payload["Samples"])
        merged["ValidMask"].extend(payload["ValidMask"])
        merged["MissingReasons"].extend(payload["MissingReasons"])
        for name in merged["Targets"]:
            merged["Targets"][name].extend(payload["Targets"][name])
        for name in merged["Covariates"]:
            merged["Covariates"][name].extend(payload["Covariates"][name])

    first_provenance = dict(first["Provenance"])
    first_provenance["merged_sources"] = [dict(payload["Provenance"]) for payload in payloads]
    first_provenance["valid_mask"] = merged["ValidMask"]
    first_provenance["missing_reasons"] = merged["MissingReasons"]
    first_provenance["value_source_ids"] = [sample.get("ValueSourceIDs", {}) for sample in merged["Samples"]]
    merged["Provenance"] = first_provenance
    return merged


def _not_processed(source: Path, message: str = "Not processed") -> api.FileResult:
    return api.FileResult(source, "not_processed", (), None, (), message)


def _convert_per_file(
    request: api.BatchRequest,
    files: Sequence[Path],
    progress_callback: Callable[[api.ProgressEvent], None] | None,
    cancel_event: threading.Event,
) -> api.BatchResult:
    results: list[api.FileResult] = []
    cancelled = False
    output_dir = Path(request.output_dir).expanduser().resolve()
    total = len(files)
    for index, source in enumerate(files, start=1):
        if cancel_event.is_set():
            cancelled = True
            results.append(_not_processed(source, "Batch was cancelled before this file started"))
            _emit(progress_callback, index, total, source, "not_processed", (index - 1) * 100 / total, "Cancelled before start")
            continue
        _emit(progress_callback, index, total, source, "reading", (index - 1) * 100 / total, "Loading and validating source")
        try:
            payload = _convert_one(source, request, cancel_event)
            if cancel_event.is_set():
                cancelled = True
                results.append(api.FileResult(source, "cancelled", (), None, (), "Cancelled before output was written"))
                continue
            sample_count = len(payload["Samples"])
            feature_ids = tuple(payload["FeatureIDs"])
            base_name = source.stem
            _emit(progress_callback, index, total, source, "writing", (index - 0.25) * 100 / total, "Publishing output")
            paths, skipped = _write_payload(payload, output_dir, base_name, request)
            status = "skipped" if skipped else "success"
            message = "Output already exists; skipped by collision policy" if skipped else None
            results.append(api.FileResult(source, status, paths or (), sample_count, feature_ids, message))
            phase = "skipped" if skipped else "completed"
            _emit(progress_callback, index, total, source, phase, index * 100 / total, message or "File completed")
        except Exception as exc:
            if cancel_event.is_set() and isinstance(exc, (MatlabBridgeCancelled, ConversionError)):
                cancelled = True
                results.append(api.FileResult(source, "cancelled", (), None, (), str(exc)))
                _emit(progress_callback, index, total, source, "cancelled", index * 100 / total, str(exc))
            else:
                results.append(api.FileResult(source, "failed", (), None, (), f"{type(exc).__name__}: {exc}"))
                _emit(progress_callback, index, total, source, "failed", index * 100 / total, str(exc))
    return api.BatchResult(tuple(results), cancelled or cancel_event.is_set())


def _convert_merged(
    request: api.BatchRequest,
    files: Sequence[Path],
    progress_callback: Callable[[api.ProgressEvent], None] | None,
    cancel_event: threading.Event,
) -> api.BatchResult:
    output_dir = Path(request.output_dir).expanduser().resolve()
    total = len(files)
    converted: list[tuple[Path, Mapping[str, Any]]] = []
    results: list[api.FileResult | None] = [None] * total
    failed = False
    cancelled = False
    for index, source in enumerate(files, start=1):
        if cancel_event.is_set():
            cancelled = True
            for pending in range(index - 1, total):
                results[pending] = _not_processed(files[pending], "Merged output was not written because the batch was cancelled")
            break
        _emit(progress_callback, index, total, source, "reading", (index - 1) * 100 / total, "Loading source for merge")
        try:
            payload = _convert_one(source, request, cancel_event)
            converted.append((source, payload))
            _emit(progress_callback, index, total, source, "validated", index * 85 / total, "Source is valid for merge")
        except Exception as exc:
            if cancel_event.is_set() and isinstance(exc, (MatlabBridgeCancelled, ConversionError)):
                cancelled = True
                results[index - 1] = api.FileResult(source, "cancelled", (), None, (), str(exc))
                for pending in range(index, total):
                    results[pending] = _not_processed(files[pending], "Merged output was not written because the batch was cancelled")
                break
            failed = True
            results[index - 1] = api.FileResult(source, "failed", (), None, (), f"{type(exc).__name__}: {exc}")

    if cancelled:
        for previous_source, previous_payload in converted:
            previous_index = files.index(previous_source)
            results[previous_index] = _not_processed(previous_source, "Validated, but merged output was not written because the batch was cancelled")
        return api.BatchResult(tuple(item or _not_processed(files[index]) for index, item in enumerate(results)), True)
    if failed:
        for source, payload in converted:
            results[files.index(source)] = _not_processed(source, "Validated, but merge was aborted because another input failed")
        return api.BatchResult(tuple(item or _not_processed(files[index]) for index, item in enumerate(results)), False)

    try:
        merged = _merge_payloads([payload for _, payload in converted])
        if cancel_event.is_set():
            return api.BatchResult(
                tuple(_not_processed(source, "Merged output was not written because the batch was cancelled") for source in files),
                True,
            )
        _emit(progress_callback, total, total, files[-1], "writing", 90.0, "Publishing merged output")
        paths, skipped = _write_payload(merged, output_dir, "merged", request)
        status = "skipped" if skipped else "success"
        message = "Merged output already exists; skipped by collision policy" if skipped else None
        for index, (source, payload) in enumerate(converted, start=1):
            results[index - 1] = api.FileResult(
                source,
                status,
                paths or (),
                len(payload["Samples"]),
                tuple(payload["FeatureIDs"]),
                message,
            )
            _emit(progress_callback, index, total, source, "skipped" if skipped else "completed", 100.0,
                  message or "Included in merged output")
    except Exception as exc:
        for index, source in enumerate(files):
            results[index] = api.FileResult(source, "failed", (), None, (), f"{type(exc).__name__}: {exc}")
        _emit(progress_callback, total, total, files[-1], "failed", 100.0, str(exc))
    return api.BatchResult(tuple(item or _not_processed(files[index]) for index, item in enumerate(results)), False)


def convert_batch(
    request: api.BatchRequest,
    *,
    progress_callback: Callable[[api.ProgressEvent], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> api.BatchResult:
    """Convert files individually or merge only fully compatible MLInput payloads."""
    if not isinstance(request, api.BatchRequest):
        raise ConversionError("Batch request must be a BatchRequest")
    if not Path(request.output_dir).expanduser().resolve().parent.exists() and not Path(request.output_dir).expanduser().resolve().parent.is_dir():
        # The writers may create the output directory itself, but not a missing ancestor chain issue.
        Path(request.output_dir).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
    cancel = cancel_event if cancel_event is not None else threading.Event()
    files = _discover_inputs(request)
    if request.selection.merge_mode == "merge":
        return _convert_merged(request, files, progress_callback, cancel)
    return _convert_per_file(request, files, progress_callback, cancel)


__all__ = ["convert_batch"]
