"""Fail-closed conversion of a PYEDA result directory into PYML tables.

The converter intentionally operates on the already-produced PYEDA result
bundle. It does not re-run EDA preprocessing, infer identities, or invent
targets. All emitted feature columns are backed by
``intake/feature_definitions.csv`` and all emitted target columns are listed
explicitly in ``intake/analysis_settings.json``.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import tempfile
import threading
import uuid
from typing import Any, Callable, Iterable, Mapping


CORE_VERSION = "0.1.0"
MANIFEST_NAME = "pyml-plugin.json"
IDENTITY_COLUMNS = {
    "participant_task_role": (
        "subject_id", "task", "group_id", "group_type",
        "participant_label", "window", "role",
    ),
    "participant_exposure": (
        "subject_id", "task", "group_id", "group_type",
        "participant_label", "window", "role",
    ),
    "records": (
        "recording_id", "subject_id", "task", "group_id", "group_type",
        "participant_label", "event_id", "role", "actor", "window",
        "sequence",
    ),
}
SOURCE_FILES = {
    "participant_task_role": "features/participant_task_role_features.csv",
    "participant_exposure": "features/participant_feature_exposure.csv",
    "records": "features/records",
}
OUTPUT_COLUMNS = ("sample_id", "meta", "feature", "target")
_SAFE_ID = re.compile(r"[^A-Za-z0-9_.-]+")


class ConversionError(RuntimeError):
    """Raised when the bundle cannot be converted without guessing."""


class ConversionCancelled(ConversionError):
    """Raised when the operator cancels a conversion."""


ProgressCallback = Callable[[str, int, int, str], None]


@dataclass(frozen=True)
class ConversionOptions:
    """Explicit conversion choices recorded in every output directory."""

    source: str = "participant_task_role"
    include_outcomes: bool = False
    only_valid_records: bool = True
    verify_manifest_hashes: bool = True
    max_record_files: int | None = None

    def __post_init__(self) -> None:
        if self.source not in SOURCE_FILES:
            raise ValueError(f"unsupported source profile: {self.source}")
        if self.max_record_files is not None and self.max_record_files < 1:
            raise ValueError("max_record_files must be positive")


class _Progress:
    def __init__(self, run_dir: Path, callback: ProgressCallback | None):
        self.run_dir = run_dir
        self.callback = callback
        self.lock = threading.Lock()
        self.payload: dict[str, Any] = {
            "status": "running", "stage": "initialise", "current": 0,
            "total": 1, "detail": "", "updated_at": _now(),
        }
        self._write()

    def update(self, stage: str, current: int, total: int, detail: str = "") -> None:
        total = max(1, int(total))
        current = max(0, min(int(current), total))
        with self.lock:
            self.payload.update({
                "status": "running", "stage": stage, "current": current,
                "total": total, "detail": str(detail), "updated_at": _now(),
            })
            self._write()
        if self.callback is not None:
            self.callback(stage, current, total, str(detail))

    def finish(self, status: str, detail: str = "") -> None:
        with self.lock:
            self.payload.update({
                "status": status, "detail": str(detail), "updated_at": _now(),
            })
            self._write()

    def _write(self) -> None:
        path = self.run_dir / "progress.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)
        with (self.run_dir / "progress.log").open("a", encoding="utf-8") as stream:
            stream.write(
                f"{self.payload['updated_at']}\t{self.payload['stage']}\t"
                f"{self.payload['current']}/{self.payload['total']}\t"
                f"{self.payload['detail']}\n"
            )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ConversionError(f"无法读取 JSON：{path}：{exc}") from exc
    if not isinstance(payload, dict):
        raise ConversionError(f"JSON 顶层必须是对象：{path}")
    return payload


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            headers = list(reader.fieldnames or [])
            if not headers or any(not h for h in headers):
                raise ConversionError(f"CSV 缺少有效表头：{path}")
            if len(headers) != len(set(headers)):
                raise ConversionError(f"CSV 存在重复列名：{path}")
            rows = [dict(row) for row in reader]
    except ConversionError:
        raise
    except (OSError, UnicodeError, csv.Error) as exc:
        raise ConversionError(f"无法读取 CSV：{path}：{exc}") from exc
    return headers, rows


def _read_gzip_csv(path: Path) -> tuple[list[str], Iterable[dict[str, str]]]:
    import gzip

    try:
        stream = gzip.open(path, "rt", encoding="utf-8-sig", newline="")
        reader = csv.DictReader(stream)
        headers = list(reader.fieldnames or [])
        if not headers or len(headers) != len(set(headers)):
            stream.close()
            raise ConversionError(f"压缩 CSV 缺少或重复表头：{path}")
        return headers, _closing_rows(stream, reader)
    except ConversionError:
        raise
    except (OSError, UnicodeError, csv.Error) as exc:
        raise ConversionError(f"无法读取压缩 CSV：{path}：{exc}") from exc


def _closing_rows(stream: Any, reader: Iterable[dict[str, str]]) -> Iterable[dict[str, str]]:
    try:
        yield from reader
    finally:
        stream.close()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _manifest_index(root: Path) -> tuple[dict[str, Any], dict[str, str]]:
    manifest_path = root / "manifest.json"
    manifest = _read_json(manifest_path)
    entries = manifest.get("artifacts", [])
    if not isinstance(entries, list):
        raise ConversionError("manifest.json 的 artifacts 必须是数组")
    index: dict[str, str] = {}
    for item in entries:
        if isinstance(item, dict) and isinstance(item.get("path"), str) and isinstance(item.get("sha256"), str):
            index[item["path"].replace("\\", "/")] = item["sha256"]
    return manifest, index


def _verify_hash(root: Path, rel: str, expected: str, *, required: bool) -> dict[str, Any]:
    path = root / Path(rel)
    if not path.is_file():
        if required:
            raise ConversionError(f"清单中的输入文件不存在：{rel}")
        return {"path": rel, "status": "missing"}
    actual = _sha256(path)
    if expected and actual != expected:
        raise ConversionError(f"来源文件哈希不一致：{rel}")
    return {"path": rel, "status": "verified", "sha256": actual}


def _finite(value: str) -> bool:
    if value is None or str(value).strip() == "":
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError, OverflowError):
        return False


def _safe_id(value: str) -> str:
    text = _SAFE_ID.sub("_", str(value).strip())
    return text or "missing"


def _sample_id(profile: str, row: Mapping[str, str], identity: tuple[str, ...]) -> str:
    parts = [profile] + [str(row.get(column, "")).strip() for column in identity]
    # Human-readable identifiers help downstream grouping; the digest prevents
    # collisions when a source value contains separators or unusual Unicode.
    readable = "__".join(_safe_id(part) for part in parts)
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:12]
    return f"{readable}__{digest}"


def _require_bundle(root: Path) -> None:
    if not root.is_dir():
        raise ConversionError(f"输入目录不存在：{root}")
    required = ["manifest.json", "summary.json", "intake/analysis_settings.json", "intake/feature_definitions.csv"]
    missing = [rel for rel in required if not (root / rel).is_file()]
    if missing:
        raise ConversionError("不是完整的 PYEDA 结果包，缺少：" + ", ".join(missing))


def _schema(root: Path, options: ConversionOptions) -> dict[str, Any]:
    _require_bundle(root)
    manifest, manifest_hashes = _manifest_index(root)
    settings = _read_json(root / "intake/analysis_settings.json")
    features = settings.get("features")
    outcomes = settings.get("outcomes", [])
    if not isinstance(features, list) or not all(isinstance(x, str) and x for x in features):
        raise ConversionError("analysis_settings.json 的 features 必须是非空字符串数组")
    if not isinstance(outcomes, list) or not all(isinstance(x, str) and x for x in outcomes):
        raise ConversionError("analysis_settings.json 的 outcomes 必须是字符串数组")
    def_headers, def_rows = _read_csv(root / "intake/feature_definitions.csv")
    if "feature" not in def_headers:
        raise ConversionError("feature_definitions.csv 缺少 feature 列")
    definitions = {row.get("feature", ""): row for row in def_rows if row.get("feature")}
    source_rel = SOURCE_FILES[options.source]
    if options.source != "records" and not (root / source_rel).is_file():
        raise ConversionError(f"缺少所选特征表：{source_rel}")
    return {
        "manifest": manifest,
        "manifest_hashes": manifest_hashes,
        "settings": settings,
        "features": list(features),
        "outcomes": list(outcomes),
        "definitions": definitions,
        "definition_headers": def_headers,
        "source_rel": source_rel,
    }


def inspect_bundle(root: Path | str, options: ConversionOptions | None = None) -> dict[str, Any]:
    """Inspect a bundle without writing output or changing source files."""
    root = Path(root).expanduser().resolve()
    options = options or ConversionOptions()
    schema = _schema(root, options)
    if options.source == "records":
        files = sorted((root / schema["source_rel"]).glob("*.csv.gz"))
        if options.max_record_files:
            files = files[:options.max_record_files]
        if not files:
            raise ConversionError("features/records 中没有 .csv.gz 文件")
        headers, _ = _read_gzip_csv(files[0])
        row_count = None
    else:
        headers, rows = _read_csv(root / schema["source_rel"])
        row_count = len(rows)
    identity = IDENTITY_COLUMNS[options.source]
    missing_identity = [column for column in identity if column not in headers]
    missing_features = [name for name in schema["features"] if name not in headers]
    missing_outcomes = [name for name in schema["outcomes"] if name not in headers]
    return {
        "status": "ready" if not missing_identity and not missing_features else "blocked",
        "input": str(root), "source": options.source, "source_table": schema["source_rel"],
        "rows": row_count, "record_files": len(files) if options.source == "records" else None,
        "identity_columns": list(identity), "feature_count": len(schema["features"]),
        "outcome_count": len(schema["outcomes"]) if options.include_outcomes else 0,
        "missing_identity": missing_identity, "missing_features": missing_features,
        "missing_outcomes": missing_outcomes,
        "analysis_signature": schema["manifest"].get("analysis_signature"),
        "qualification": schema["settings"].get("qualification"),
    }


def _write_csv(path: Path, headers: list[str], rows: Iterable[Mapping[str, Any]]) -> int:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=headers, extrasaction="raise")
        writer.writeheader()
        count = 0
        for row in rows:
            writer.writerow({key: "" if value is None else value for key, value in row.items()})
            count += 1
    return count


def _selected_columns(headers: list[str], schema: dict[str, Any], options: ConversionOptions) -> tuple[list[str], list[str], list[str]]:
    identity = list(IDENTITY_COLUMNS[options.source])
    missing_identity = [column for column in identity if column not in headers]
    if missing_identity:
        raise ConversionError("所选来源缺少身份列：" + ", ".join(missing_identity))
    missing_features = [name for name in schema["features"] if name not in headers]
    if missing_features:
        raise ConversionError("所选来源缺少已登记 EDA 特征：" + ", ".join(missing_features))
    outcomes = [name for name in schema["outcomes"] if name in headers] if options.include_outcomes else []
    return identity, list(schema["features"]), outcomes


def _build_rows(
    rows: Iterable[Mapping[str, str]],
    headers: list[str],
    schema: dict[str, Any],
    options: ConversionOptions,
    progress: _Progress,
    cancel: threading.Event | None,
) -> tuple[list[str], list[dict[str, str]], list[dict[str, str]], dict[str, Any]]:
    identity, features, outcomes = _selected_columns(headers, schema, options)
    metadata = (
        [column for column in headers if column not in identity and column not in features and column not in schema["outcomes"]]
        if options.include_outcomes else [column for column in ("status",) if column in headers and column not in features]
    )
    # Quality columns stay metadata; they are not silently promoted to model features.
    meta_columns = [f"meta__{column}" for column in metadata]
    feature_columns = [f"feature__{column}" for column in features]
    target_columns = [f"target__{column}" for column in outcomes]
    data_headers = ["sample_id", *[f"meta__{column}" for column in identity], *meta_columns, *feature_columns, *target_columns]
    mask_headers = ["sample_id", *feature_columns, *target_columns]
    output_rows: list[dict[str, str]] = []
    mask_rows: list[dict[str, str]] = []
    seen: set[str] = set()
    source_status: dict[str, int] = {}
    total = 0
    valid = 0
    missing_feature_cells = 0
    missing_target_cells = 0
    for total, source_row in enumerate(rows, 1):
        if cancel is not None and cancel.is_set():
            raise ConversionCancelled("用户取消了转换")
        status = str(source_row.get("status", "")).strip()
        source_status[status or "unspecified"] = source_status.get(status or "unspecified", 0) + 1
        if options.source == "records" and options.only_valid_records and status != "valid":
            if total % 100 == 0:
                progress.update("读取并筛选", total, max(total, 1), f"已跳过 {status or '无状态'}")
            continue
        sample_id = _sample_id(options.source, source_row, tuple(identity))
        if sample_id in seen:
            raise ConversionError(f"身份键重复，拒绝静默合并：{sample_id}")
        seen.add(sample_id)
        row: dict[str, str] = {"sample_id": sample_id}
        mask: dict[str, str] = {"sample_id": sample_id}
        for column in identity:
            row[f"meta__{column}"] = str(source_row.get(column, ""))
        for column in metadata:
            row[f"meta__{column}"] = str(source_row.get(column, ""))
        for column in features:
            value = str(source_row.get(column, ""))
            row[f"feature__{column}"] = value
            ok = _finite(value)
            mask[f"feature__{column}"] = "1" if ok else "0"
            missing_feature_cells += int(not ok)
        for column in outcomes:
            value = str(source_row.get(column, ""))
            row[f"target__{column}"] = value
            ok = _finite(value)
            mask[f"target__{column}"] = "1" if ok else "0"
            missing_target_cells += int(not ok)
        output_rows.append(row)
        mask_rows.append(mask)
        valid += 1
        if total % 100 == 0:
            progress.update("读取并筛选", total, max(total, 1), f"已保留 {valid} 行")
    if not output_rows:
        raise ConversionError("所选来源没有可转换的有效行")
    # Verify the composite identity is unique at the source semantic level.
    return data_headers, output_rows, mask_rows, {
        "input_rows": total, "output_rows": valid, "source_status": source_status,
        "metadata_columns": metadata, "features": features, "outcomes": outcomes,
        "missing_feature_cells": missing_feature_cells,
        "missing_target_cells": missing_target_cells,
    }


def _feature_dictionary(schema: dict[str, Any], info: dict[str, Any], options: ConversionOptions) -> dict[str, Any]:
    definitions = schema["definitions"]
    features = []
    for name in info["features"]:
        definition = dict(definitions.get(name, {}))
        definition.update({"source_column": name, "output_column": f"feature__{name}"})
        features.append(definition)
    targets = [
        {"source_column": name, "output_column": f"target__{name}",
         "status": "explicit_from_analysis_settings"}
        for name in info["outcomes"]
    ]
    return {
        "schema_version": 1,
        "source_project": "PYEDA",
        "identity_columns": list(IDENTITY_COLUMNS[options.source]),
        "features": features,
        "targets": targets,
        "metadata_columns": [f"meta__{name}" for name in info["metadata_columns"]],
        "mask_semantics": "1 means a finite numeric cell was preserved; 0 means blank/non-finite source value.",
        "target_policy": "Targets are exported only when explicitly listed in intake/analysis_settings.json; no target is inferred.",
    }


def _source_hashes(root: Path, schema: dict[str, Any], options: ConversionOptions, progress: _Progress) -> list[dict[str, Any]]:
    rels = ["manifest.json", "summary.json", "intake/analysis_settings.json", "intake/feature_definitions.csv", schema["source_rel"]]
    if options.source == "records":
        files = sorted((root / schema["source_rel"]).glob("*.csv.gz"))
        if options.max_record_files:
            files = files[:options.max_record_files]
        if not files:
            raise ConversionError("features/records 中没有 .csv.gz 文件")
        rels = ["manifest.json", "summary.json", "intake/analysis_settings.json", "intake/feature_definitions.csv"] + [str(p.relative_to(root)).replace("\\", "/") for p in files]
    results = []
    total = len(rels)
    manifest_hashes = schema["manifest_hashes"]
    for index, rel in enumerate(rels, 1):
        expected = manifest_hashes.get(rel, "")
        path = root / rel
        if not path.is_file():
            raise ConversionError(f"缺少输入文件：{rel}")
        if not options.verify_manifest_hashes:
            results.append({"path": rel, "status": "not_verified", "sha256": _sha256(path)})
        elif rel != "manifest.json" and not expected:
            # A source not committed into the manifest is still recorded, but is
            # visibly unverified instead of being treated as trusted.
            results.append({"path": rel, "status": "not_in_manifest", "sha256": _sha256(path)})
        else:
            results.append(_verify_hash(root, rel, expected, required=True))
        progress.update("核对来源哈希", index, total, rel)
    return results


def _verify_source_unchanged(root: Path, source_hashes: list[dict[str, Any]], progress: _Progress) -> None:
    total = len(source_hashes)
    for index, item in enumerate(source_hashes, 1):
        path = root / item["path"]
        actual = _sha256(path)
        if actual != item.get("sha256"):
            raise ConversionError(f"转换期间来源文件发生变化：{item['path']}")
        progress.update("复核来源未变更", index, total, item["path"])


def _new_run_dir(output: Path) -> Path:
    output = output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    if output.exists() and any(output.iterdir()):
        raise ConversionError(f"输出目录必须为空：{output}")
    return output


def convert_bundle(
    root: Path | str,
    output: Path | str,
    options: ConversionOptions | None = None,
    *,
    progress_callback: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
) -> dict[str, Any]:
    """Convert a PYEDA bundle and return the persisted batch summary."""
    root = Path(root).expanduser().resolve()
    output = _new_run_dir(Path(output))
    options = options or ConversionOptions()
    progress = _Progress(output, progress_callback)
    try:
        progress.update("检查输入契约", 0, 1, str(root))
        schema = _schema(root, options)
        source_hashes = _source_hashes(root, schema, options, progress)
        if options.source == "records":
            files = sorted((root / schema["source_rel"]).glob("*.csv.gz"))
            if options.max_record_files:
                files = files[:options.max_record_files]
            headers, _ = _read_gzip_csv(files[0])
            # Re-open each file lazily to avoid loading the complete event table.
            def rows() -> Iterable[dict[str, str]]:
                for index, path in enumerate(files, 1):
                    if cancel_event is not None and cancel_event.is_set():
                        raise ConversionCancelled("用户取消了转换")
                    file_headers, iterator = _read_gzip_csv(path)
                    if file_headers != headers:
                        raise ConversionError(f"记录文件表头不一致：{path.name}")
                    for row in iterator:
                        yield row
                    progress.update("读取记录文件", index, len(files), path.name)
            rows = rows()
        else:
            source_path = root / schema["source_rel"]
            headers, source_rows = _read_csv(source_path)
            rows = iter(source_rows)
        data_headers, data_rows, mask_rows, info = _build_rows(
            rows, headers, schema, options, progress, cancel_event
        )
        progress.update("写入数据表", 0, 3, "dataset.csv")
        _write_csv(output / "dataset.csv", data_headers, data_rows)
        progress.update("写入数据表", 1, 3, "valid_mask.csv")
        _write_csv(output / "valid_mask.csv", ["sample_id", *[c for c in data_headers if c.startswith(("feature__", "target__"))]], mask_rows)
        progress.update("写入数据表", 2, 3, "feature_dictionary.json")
        dictionary = _feature_dictionary(schema, info, options)
        (output / "feature_dictionary.json").write_text(json.dumps(dictionary, ensure_ascii=False, indent=2), encoding="utf-8")
        progress.update("写入数据表", 3, 3, "完成")
        _verify_source_unchanged(root, source_hashes, progress)
        source_summary = _read_json(root / "summary.json")
        manifest = schema["manifest"]
        provenance = {
            "schema_version": 1, "plugin": {"name": "PYEDA EDA 数据转换器", "version": CORE_VERSION},
            "source_project": "PYEDA", "input_root": str(root), "output_root": str(output),
            "source_profile": options.source, "options": asdict(options), "source_hashes": source_hashes,
            "analysis_signature": manifest.get("analysis_signature"), "graphics_signature": manifest.get("graphics_signature"),
            "qualification": schema["settings"].get("qualification"),
            "target_status": "explicit_from_analysis_settings" if info["outcomes"] else "not_exported",
            "target_columns": [f"target__{x}" for x in info["outcomes"]],
            "training": "NOT RUN", "statistics": "NOT RUN",
            "scientific_readiness": "conversion_only; preserve grouping by subject_id before modelling",
            "identity_policy": "Composite source identities are preserved in meta__ columns; no subject, task, role or target is inferred.",
        }
        if options.include_outcomes:
            provenance["source_summary"] = source_summary
        (output / "provenance.json").write_text(json.dumps(provenance, ensure_ascii=False, indent=2), encoding="utf-8")
        plan = {
            "schema_version": 1, "status": "completed_supported_tables", "task": "format_conversion_only",
            "source_project": "PYEDA", "input": str(root), "output": str(output),
            "source_table": schema["source_rel"], "identity_columns": list(IDENTITY_COLUMNS[options.source]),
            "feature_columns": [f"feature__{x}" for x in info["features"]],
            "target_columns": [f"target__{x}" for x in info["outcomes"]],
            "target_generation": "none", "aggregation": "none", "fit": "none",
            "checks": ["manifest hashes", "source schema", "unique sample IDs", "finite masks", "source unchanged during conversion"],
        }
        (output / "conversion.plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        summary = {
            "status": "completed_supported_tables", "source_profile": options.source,
            "input": str(root), "output": str(output), "rows": info["output_rows"],
            "features": len(info["features"]), "targets": len(info["outcomes"]),
            "feature_cells_missing_or_nonfinite": info["missing_feature_cells"],
            "target_cells_missing_or_nonfinite": info["missing_target_cells"],
            "excluded_rows": info["input_rows"] - info["output_rows"],
            "source_status": info["source_status"], "metadata_columns": info["metadata_columns"],
            "analysis_signature": manifest.get("analysis_signature"),
            "target_status": provenance["target_status"], "training": "NOT RUN", "statistics": "NOT RUN",
            "files": ["dataset.csv", "valid_mask.csv", "feature_dictionary.json", "provenance.json", "conversion.plan.json"],
        }
        (output / "batch_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        (output / "转换结果.txt").write_text(
            "PYEDA EDA 特征转换完成。\n"
            f"数据表：{output / 'dataset.csv'}\n"
            f"行数：{info['output_rows']}；EDA 特征：{len(info['features'])}；显式结果列：{len(info['outcomes'])}\n"
            "未执行训练或统计推断；建模前按 subject_id/team 重新定义独立单位并检查缺失。\n",
            encoding="utf-8-sig",
        )
        progress.finish("completed_supported_tables", str(output))
        return summary
    except ConversionCancelled as exc:
        partial = {"status": "cancelled", "input": str(root), "output": str(output), "error": str(exc)}
        (output / "batch_summary.json").write_text(json.dumps(partial, ensure_ascii=False, indent=2), encoding="utf-8")
        progress.finish("cancelled", str(exc))
        raise
    except Exception as exc:
        failure = {"status": "failed", "input": str(root), "output": str(output), "error": str(exc)}
        (output / "batch_summary.json").write_text(json.dumps(failure, ensure_ascii=False, indent=2), encoding="utf-8")
        progress.finish("failed", str(exc))
        raise
