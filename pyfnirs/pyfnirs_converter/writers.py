"""Write a validated MLInput as a PY-ML-readable CSV bundle or XLSX file."""
from __future__ import annotations

import csv
import json
import math
import os
from pathlib import Path
import shutil
import tempfile
from collections.abc import Mapping, Sequence
from typing import Any

from .contracts import validate_mlinput


class WriterError(ValueError):
    """Raised when an MLInput cannot be represented by the requested format."""


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _typed_scalar(value: Mapping[str, Any]) -> Any | None:
    """Decode a scalar MATLAB interchange cell for human-readable tables.

    The authoritative in-memory source may retain typed MATLAB wrappers. A
    review workbook should show their scalar value while preserving compound
    arrays and structs as JSON through ``_cell_value``.
    """
    matlab_class = value.get("matlab_class")
    shape = value.get("shape")
    raw = value.get("value")
    if (
        not isinstance(matlab_class, str)
        or not isinstance(shape, list)
        or any(not isinstance(size, int) or isinstance(size, bool) for size in shape)
        or math.prod(shape) != 1
        or not isinstance(raw, str)
        or "elements" in value
        or "fields" in value
        or "table" in value
    ):
        return None
    if value.get("is_missing") is True:
        return None
    if matlab_class in {"char", "string", "categorical", "datetime", "duration"}:
        return raw
    if matlab_class == "logical":
        if raw in {"true", "false"}:
            return raw == "true"
        return None
    if matlab_class in {"double", "single"} or matlab_class.startswith(("int", "uint")):
        try:
            if raw == "NaN":
                return math.nan
            if raw == "Inf":
                return math.inf
            if raw == "-Inf":
                return -math.inf
            if matlab_class.startswith(("int", "uint")):
                return int(raw)
            return float(raw)
        except ValueError:
            return None
    return None


def _cell_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return ""
    if isinstance(value, float) and value.is_integer() and abs(value) <= 2**53:
        # Keep the readable integer form only while every integer remains
        # exactly representable; larger floats need their round-trip form.
        if value != 0 or math.copysign(1.0, value) > 0:
            return int(value)
    if isinstance(value, Mapping):
        if value.get("is_missing") is True:
            return ""
        decoded = _typed_scalar(value)
        if decoded is not None:
            return _cell_value(decoded)
        if "matlab_class" in value:
            return _json_text(value)
        return _json_text(value)
    if isinstance(value, (list, tuple)):
        return _json_text(value)
    return value


def _feature_matrix_rows(payload: Mapping[str, Any]) -> tuple[list[str], list[list[Any]]]:
    samples = payload["Samples"]
    feature_ids = payload["FeatureIDs"]
    targets = payload["Targets"]
    covariates = payload["Covariates"]
    matrix = payload["X"]
    target_names = list(targets)
    covariate_names = list(covariates)
    header = ["ObservationID", *target_names, *covariate_names, *feature_ids]
    rows: list[list[Any]] = []
    for index, sample in enumerate(samples):
        rows.append([
            _cell_value(sample["ObservationID"]),
            *(_cell_value(targets[name][index]) for name in target_names),
            *(_cell_value(covariates[name][index]) for name in covariate_names),
            *(_cell_value(value) for value in matrix[index]),
        ])
    return header, rows


def _records_rows(records: Sequence[Mapping[str, Any]]) -> tuple[list[str], list[list[Any]]]:
    headers: list[str] = []
    seen: set[str] = set()
    for record in records:
        for key in record:
            if key not in seen:
                headers.append(str(key))
                seen.add(str(key))
    return headers, [[_cell_value(record.get(header)) for header in headers] for record in records]


def _validate_for_export(payload: Mapping[str, Any]) -> None:
    validate_mlinput(payload)
    if not payload["FeatureIDs"]:
        raise WriterError("At least one selected feature is required for output")
    if not payload["Samples"]:
        raise WriterError("At least one sample is required for output")


def write_csv_bundle(payload: Mapping[str, Any], destination_dir: str | Path) -> tuple[Path, ...]:
    """Atomically publish a complete four-file bundle without overwriting."""
    _validate_for_export(payload)
    destination = Path(destination_dir)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(f"CSV bundle destination already exists: {destination}")
    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent))
    try:
        feature_header, feature_rows = _feature_matrix_rows(payload)
        samples_header, sample_rows = _records_rows(payload["Samples"])
        dictionary_header, dictionary_rows = _records_rows(payload["FeatureDefinitions"])
        tables = (
            ("FeatureMatrix.csv", feature_header, feature_rows),
            ("Samples.csv", samples_header, sample_rows),
            ("FeatureDictionary.csv", dictionary_header, dictionary_rows),
        )
        paths: list[Path] = []
        for name, header, rows in tables:
            if not header:
                raise WriterError(f"Cannot write {name}: table has no columns")
            path = staging / name
            with path.open("x", encoding="utf-8-sig", newline="") as stream:
                writer = csv.writer(stream, lineterminator="\n")
                writer.writerow(header)
                writer.writerows(rows)
            paths.append(destination / name)
        provenance_path = staging / "Provenance.json"
        with provenance_path.open("x", encoding="utf-8") as stream:
            json.dump(payload["Provenance"], stream, ensure_ascii=False, sort_keys=True, indent=2)
            stream.write("\n")
        paths.append(destination / "Provenance.json")
        # On Windows, rename refuses an existing destination and publishes
        # the complete staged directory in one filesystem operation.
        staging.rename(destination)
        return tuple(paths)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _xlsx_cell_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, (Mapping, list, tuple)):
        return _json_text(value)
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _xlsx_cell(worksheet: Any, value: Any, write_only_cell: Any) -> Any:
    """Make every string an explicit text cell, including strings starting ``=``.

    openpyxl otherwise infers formula cells from strings beginning with ``=``.
    That changes data such as IDs and labels, and formula cells without cached
    results can be read back as missing values by spreadsheet consumers.
    """
    value = _xlsx_cell_value(value)
    if isinstance(value, str):
        cell = write_only_cell(worksheet, value=value)
        cell.data_type = "s"
        return cell
    if isinstance(value, float):
        # openpyxl formats numeric floats with 16 significant digits. Use the
        # shortest round-tripping decimal while keeping the cell numeric.
        cell = write_only_cell(worksheet, value=repr(value))
        cell.data_type = "n"
        return cell
    return value


def _assert_xlsx_limits(tables: Sequence[tuple[str, Sequence[str], Sequence[Sequence[Any]]]]) -> None:
    max_rows = 1_048_576
    max_columns = 16_384
    for name, headers, rows in tables:
        if len(headers) > max_columns:
            raise WriterError(f"{name} has {len(headers)} columns; XLSX limit is {max_columns}")
        if len(rows) + 1 > max_rows:
            raise WriterError(f"{name} has {len(rows) + 1} rows; XLSX limit is {max_rows}")


def write_xlsx(payload: Mapping[str, Any], destination_path: str | Path) -> tuple[Path, ...]:
    """Write one four-sheet workbook, refusing existing destinations and overflows."""
    _validate_for_export(payload)
    try:
        from openpyxl import Workbook
        from openpyxl.cell import WriteOnlyCell
    except ImportError as exc:  # pragma: no cover - dependency is pinned in support
        raise WriterError("XLSX output requires the installed openpyxl dependency") from exc

    destination = Path(destination_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    feature_header, feature_rows = _feature_matrix_rows(payload)
    samples_header, sample_rows = _records_rows(payload["Samples"])
    dictionary_header, dictionary_rows = _records_rows(payload["FeatureDefinitions"])
    provenance = payload["Provenance"]
    provenance_rows = [["Key", "Value"], *[[str(key), _json_text(value)] for key, value in provenance.items()]]
    tables = (
        ("FeatureMatrix", feature_header, feature_rows),
        ("Samples", samples_header, sample_rows),
        ("FeatureDictionary", dictionary_header, dictionary_rows),
        ("Provenance", provenance_rows[0], provenance_rows[1:]),
    )
    _assert_xlsx_limits(tables)

    workbook = Workbook(write_only=True)
    for title, headers, rows in tables:
        sheet = workbook.create_sheet(title=title)
        sheet.append([_xlsx_cell(sheet, value, WriteOnlyCell) for value in headers])
        for row in rows:
            sheet.append([_xlsx_cell(sheet, value, WriteOnlyCell) for value in row])

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=f".{destination.stem}-", suffix=".xlsx", dir=destination.parent, delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
        workbook.save(temporary_path)
        # A hard link makes the fully saved workbook visible at once and fails
        # atomically if another process already created the destination.
        os.link(temporary_path, destination)
        return (destination,)
    except Exception:
        raise
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def write_mlinput(
    payload: Mapping[str, Any],
    destination: str | Path,
    *,
    output_format: str,
) -> tuple[Path, ...]:
    """Choose the G4 writer for a validated schema-1 MLInput."""
    if output_format == "csv":
        return write_csv_bundle(payload, destination)
    if output_format == "xlsx":
        return write_xlsx(payload, destination)
    raise WriterError(f"Unsupported output format {output_format!r}")


__all__ = ["WriterError", "write_csv_bundle", "write_mlinput", "write_xlsx"]
