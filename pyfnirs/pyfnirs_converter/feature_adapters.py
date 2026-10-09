"""Fail-closed feature adapters for PYfNIRs exports and raw Results MAT files.

The raw MAT source is represented by ``pyfnirs.raw-mat-export/1``: MATLAB
decodes the MAT container into typed nodes, while this module selects only
registry-backed, explicitly parameterized scalar values. No filename or array
position is used as a sample identity.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any

from . import api, contracts


RAW_MAT_SCHEMA = "pyfnirs.raw-mat-export/1"
RAW_RESULTS_ADAPTER_ID = "pyfnirs.raw_results.v1"
STUDY_EXPORT_ADAPTER_ID = "pyfnirs.study_export.v1"
STUDY_MAT_ADAPTER_ID = "pyfnirs.study_mat.v1"
STUDY_DEFINED_CAPABILITY_ID = "study-defined"


class AdapterError(ValueError):
    """Raised when a source shape or scientific definition is not explicit."""


@dataclass(frozen=True)
class _PathPart:
    name: str
    index: int | None = None
    index_kind: str | None = None


@dataclass(frozen=True)
class _TableColumn:
    values: tuple[Mapping[str, Any], ...]


_PATH_PART = re.compile(r"^(?P<name>[A-Za-z][A-Za-z0-9_]*)(?:(?P<brace>\{[1-9][0-9]*\})|(?P<paren>\([1-9][0-9]*\)))?$")
_TEXT_CLASSES = {"char", "string", "categorical", "datetime", "duration"}
_NUMERIC_CLASSES = {"double", "single"} | {
    f"{prefix}{width}"
    for prefix in ("int", "uint")
    for width in ("8", "16", "32", "64")
}


def _load_registry() -> dict[str, Mapping[str, Any]]:
    registry_path = Path(__file__).with_name("capabilities.json")
    try:
        payload = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AdapterError(f"Cannot read PYfNIRs capability registry: {exc}") from exc
    features = payload.get("features")
    if not isinstance(features, list):
        raise AdapterError("PYfNIRs capability registry has no feature list")
    result: dict[str, Mapping[str, Any]] = {}
    for feature in features:
        if not isinstance(feature, Mapping):
            raise AdapterError("PYfNIRs capability registry contains an invalid item")
        capability_id = feature.get("id")
        if not isinstance(capability_id, str) or not capability_id:
            raise AdapterError("PYfNIRs capability registry contains an empty ID")
        if capability_id in result:
            raise AdapterError(f"Duplicate PYfNIRs capability ID: {capability_id}")
        result[capability_id] = feature
    return result


_REGISTRY = _load_registry()


def _parse_path(source_path: str) -> tuple[_PathPart, ...]:
    if not isinstance(source_path, str) or not source_path.strip():
        raise AdapterError("Source path must be nonempty text")
    parts: list[_PathPart] = []
    for raw in source_path.split("."):
        match = _PATH_PART.fullmatch(raw)
        if match is None:
            raise AdapterError(f"Unsupported MATLAB source path syntax: {source_path}")
        index_kind: str | None = None
        index: int | None = None
        if match.group("brace"):
            index_kind = "cell"
            index = int(match.group("brace")[1:-1])
        elif match.group("paren"):
            index_kind = "array"
            index = int(match.group("paren")[1:-1])
        parts.append(_PathPart(match.group("name"), index, index_kind))
    if not parts:
        raise AdapterError("Source path must contain a MATLAB field name")
    return tuple(parts)


def _shape(node: Mapping[str, Any], label: str) -> tuple[int, ...]:
    raw = node.get("shape")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raise AdapterError(f"{label} has no MATLAB shape")
    result: list[int] = []
    for dimension in raw:
        if isinstance(dimension, bool) or not isinstance(dimension, int) or dimension < 0:
            raise AdapterError(f"{label} has an invalid MATLAB shape")
        result.append(dimension)
    return tuple(result)


def _shape_size(shape: Sequence[int]) -> int:
    total = 1
    for dimension in shape:
        total *= dimension
    return total


def _table_columns(node: Mapping[str, Any], label: str) -> Mapping[str, Any]:
    table = node.get("table")
    if not isinstance(table, Mapping):
        raise AdapterError(f"{label} is not an encoded MATLAB table")
    columns = table.get("columns")
    rows = table.get("rows")
    if not isinstance(columns, Sequence) or not isinstance(rows, Sequence):
        raise AdapterError(f"{label} has an invalid MATLAB table")
    if table.get("row_count") != len(rows):
        raise AdapterError(f"{label}.row_count does not match its rows")
    names: list[str] = []
    for column in columns:
        if not isinstance(column, Mapping) or not isinstance(column.get("name"), str):
            raise AdapterError(f"{label} has an invalid table column")
        names.append(column["name"])
    if len(names) != len(set(names)):
        raise AdapterError(f"{label} has duplicate table columns")
    for row in rows:
        if not isinstance(row, Mapping) or set(row) != set(names):
            raise AdapterError(f"{label} has a malformed table row")
    return {name: tuple(row[name] for row in rows) for name in names}


def _resolve_raw_node(document: Mapping[str, Any], source_path: str) -> Mapping[str, Any] | _TableColumn:
    _validate_raw_document(document)
    parts = _parse_path(source_path)
    variables = document["variables"]
    root = parts[0]
    if root.index is not None:
        raise AdapterError("A top-level MATLAB variable cannot use an array index")
    if root.name not in variables:
        raise AdapterError(f"MATLAB source path does not exist: {source_path}")
    current: Mapping[str, Any] | _TableColumn = variables[root.name]
    for part in parts[1:]:
        if isinstance(current, _TableColumn):
            raise AdapterError(f"Cannot traverse a table column at {source_path}")
        if isinstance(current, Mapping) and current.get("matlab_class") == "table":
            columns = _table_columns(current, source_path)
            if part.name not in columns:
                raise AdapterError(f"MATLAB table column does not exist: {source_path}")
            current = _TableColumn(columns[part.name])
        elif isinstance(current, Mapping) and isinstance(current.get("fields"), Mapping):
            fields = current["fields"]
            if part.name not in fields or not isinstance(fields[part.name], Mapping):
                raise AdapterError(f"MATLAB source field does not exist: {source_path}")
            current = fields[part.name]
        else:
            raise AdapterError(f"MATLAB source field cannot be traversed: {source_path}")
        if part.index is not None:
            if isinstance(current, _TableColumn):
                if part.index_kind != "array" or part.index > len(current.values):
                    raise AdapterError(f"MATLAB table row index is outside its recorded height: {source_path}")
                selected = current.values[part.index - 1]
                if not isinstance(selected, Mapping):
                    raise AdapterError(f"MATLAB table column contains an invalid value: {source_path}")
                current = selected
                continue
            elements = current.get("elements")
            if not isinstance(elements, Sequence) or isinstance(elements, (str, bytes)):
                raise AdapterError(f"MATLAB source path is not an indexed array: {source_path}")
            shape = _shape(current, source_path)
            if _shape_size(shape) != len(elements) or part.index > len(elements):
                raise AdapterError(f"MATLAB array index is outside its recorded shape: {source_path}")
            if part.index_kind == "cell" and current.get("matlab_class") != "cell":
                raise AdapterError(f"Curly indexing requires a MATLAB cell array: {source_path}")
            if part.index_kind == "array" and current.get("matlab_class") == "cell":
                raise AdapterError(f"Parenthesis indexing is required for a MATLAB cell array: {source_path}")
            selected = elements[part.index - 1]
            if not isinstance(selected, Mapping):
                raise AdapterError(f"MATLAB array contains an invalid value: {source_path}")
            current = selected
    return current


def _decode_scalar(node: Mapping[str, Any], label: str) -> Any:
    if not isinstance(node, Mapping):
        raise AdapterError(f"{label} is not a typed MATLAB value")
    matlab_class = node.get("matlab_class")
    if not isinstance(matlab_class, str):
        raise AdapterError(f"{label} has no MATLAB class")
    shape = _shape(node, label)
    is_char_row = (
        matlab_class == "char"
        and len(shape) <= 2
        and (not shape or shape[0] == 1 or _shape_size(shape) == 0)
    )
    if (not is_char_row and _shape_size(shape) != 1) or "elements" in node:
        raise AdapterError(f"{label} must be a scalar MATLAB value")
    if "real_elements" in node or "imag_elements" in node:
        raise AdapterError(f"{label} is complex and needs an explicit projection")
    if node.get("is_missing") is True:
        return None
    if "value" not in node or not isinstance(node["value"], str):
        raise AdapterError(f"{label} has no scalar text value")
    raw = node["value"]
    if matlab_class in _TEXT_CLASSES:
        return raw
    if matlab_class == "logical":
        if raw not in {"true", "false"}:
            raise AdapterError(f"{label} has an invalid MATLAB logical value")
        return raw == "true"
    if matlab_class in _NUMERIC_CLASSES:
        if raw == "NaN":
            return math.nan
        if raw == "Inf":
            return math.inf
        if raw == "-Inf":
            return -math.inf
        try:
            number = float(raw)
        except ValueError as exc:
            raise AdapterError(f"{label} has an invalid numeric value") from exc
        if matlab_class.startswith(("int", "uint")):
            try:
                return int(raw)
            except ValueError as exc:
                raise AdapterError(f"{label} has an invalid integer value") from exc
        return number
    raise AdapterError(f"{label} has unsupported MATLAB class {matlab_class}")


def _flatten_typed(node: Mapping[str, Any], label: str) -> tuple[Any, ...]:
    if "real_elements" in node or "imag_elements" in node:
        raise AdapterError(f"{label} is complex and needs an explicit projection")
    if "elements" not in node:
        return (_decode_scalar(node, label),)
    elements = node.get("elements")
    if not isinstance(elements, Sequence) or isinstance(elements, (str, bytes)):
        raise AdapterError(f"{label}.elements is not a sequence")
    shape = _shape(node, label)
    if _shape_size(shape) != len(elements):
        raise AdapterError(f"{label}.elements do not match the recorded MATLAB shape")
    values: list[Any] = []
    for index, element in enumerate(elements):
        if not isinstance(element, Mapping):
            raise AdapterError(f"{label}.elements[{index}] is malformed")
        if element.get("matlab_class") in {"struct", "cell", "table"}:
            raise AdapterError(f"{label} contains nested MATLAB values")
        values.append(_decode_scalar(element, f"{label}[{index + 1}]"))
    return tuple(values)


def resolve_raw_source_path(
    document: Mapping[str, Any], source_path: str
) -> tuple[str | float | int | bool | None, ...]:
    """Resolve an explicit MATLAB path to scalar values in stored order.

    Supported syntax is a dotted path of MATLAB identifiers with optional
    one-based linear ``{n}`` or ``(n)`` array indexing. A MATLAB table column
    resolves to one value per table row. No MATLAB expression is evaluated.
    """
    node = _resolve_raw_node(document, source_path)
    if isinstance(node, _TableColumn):
        values: list[Any] = []
        for row_index, value in enumerate(node.values):
            if not isinstance(value, Mapping):
                raise AdapterError(f"{source_path}[{row_index}] is malformed")
            values.append(_decode_scalar(value, f"{source_path}[{row_index}]") )
        return tuple(values)
    return _flatten_typed(node, source_path)


def inspect_document(
    document: Mapping[str, Any],
    source_path: Path,
    source_adapter_id: str | None = None,
) -> api.SourceInspection:
    """Inspect a validated MATLAB export or raw Results typed-tree envelope."""
    if not isinstance(document, Mapping):
        raise AdapterError("Source document must be a mapping")
    adapter_id = source_adapter_id or document.get("source_adapter_id")
    if document.get("schema") == RAW_MAT_SCHEMA:
        _validate_raw_document(document, adapter_id)
        return _inspect_raw_document(document, Path(source_path), adapter_id or RAW_RESULTS_ADAPTER_ID)
    if document.get("schema") == contracts.EXPORT_SCHEMA:
        if adapter_id not in {STUDY_EXPORT_ADAPTER_ID, STUDY_MAT_ADAPTER_ID}:
            raise AdapterError("A schema-1 study export needs an explicit study adapter ID")
        contracts.validate_export_document(document)
        return _inspect_study_document(document, Path(source_path), adapter_id)
    raise AdapterError("Unsupported PYfNIRs source document schema")


def select_feature_rows(
    document: Mapping[str, Any], selection: api.ConversionSelection
) -> tuple[tuple[Mapping[str, Any], ...], tuple[Mapping[str, Any], ...]]:
    """Apply explicit source selections and return rows plus definitions.

    Rows retain the ObservationID/FeatureID keys and missingness fields. The
    core owns SourceID generation, output mapping, and MLInput validation.
    Raw Results values must pass the current capability registry gate. Schema-1
    study.Values uses ``study-defined`` to carry already normalized values and
    does not attest to the native calculation that produced them.
    """
    if not isinstance(selection, api.ConversionSelection):
        raise AdapterError("Feature selection must be a ConversionSelection")
    if document.get("schema") == RAW_MAT_SCHEMA:
        _validate_raw_document(document, selection.source_adapter_id)
        return _select_raw_rows(document, selection)
    if document.get("schema") == contracts.EXPORT_SCHEMA:
        contracts.validate_export_document(document)
        if selection.source_adapter_id not in {STUDY_EXPORT_ADAPTER_ID, STUDY_MAT_ADAPTER_ID}:
            raise AdapterError("Selection source adapter does not match the study export")
        return _select_study_rows(document, selection)
    raise AdapterError("Unsupported PYfNIRs source document schema")


def _validate_raw_document(
    document: Mapping[str, Any], source_adapter_id: str | None = None
) -> None:
    if document.get("schema") != RAW_MAT_SCHEMA:
        raise AdapterError("Unsupported raw MATLAB export schema")
    adapter_id = document.get("source_adapter_id")
    if adapter_id != RAW_RESULTS_ADAPTER_ID:
        raise AdapterError("Unsupported raw PYfNIRs source adapter ID")
    if source_adapter_id is not None and source_adapter_id != adapter_id:
        raise AdapterError("Source adapter ID does not match the raw MAT export")
    variables = document.get("variables")
    if not isinstance(variables, Mapping):
        raise AdapterError("Raw MAT export has no top-level variables")
    results = variables.get("Results")
    if not isinstance(results, Mapping) or results.get("matlab_class") != "struct":
        raise AdapterError("Raw MAT export must contain a typed Results struct")
    shape = _shape(results, "Results")
    if shape != (1, 1) or not isinstance(results.get("fields"), Mapping):
        raise AdapterError("Raw Results must be a scalar struct")


def _inspect_raw_document(
    document: Mapping[str, Any], source_path: Path, adapter_id: str
) -> api.SourceInspection:
    fields: list[api.SourceField] = []
    results = document["variables"]["Results"]
    _walk_fields(results, "Results", fields, depth=0)
    feature_candidates = _raw_feature_candidates(document)
    identity_candidates: list[str] = []
    target_candidates: list[str] = []
    covariate_candidates: list[str] = []
    for candidate in (
        "Results.RecordID",
        "Results.SubjectID",
        "Results.ObservationID",
        "Results.PairObservationID",
        "Results.Availability.RecordID",
        "Results.Availability.SubjectID",
        "Results.Metadata.StudyManifest.Records.RecordID",
        "Results.Metadata.StudyManifest.Records.SubjectID",
        "Results.Metadata.Pairing.PairID",
    ):
        if _path_exists(document, candidate):
            identity_candidates.append(candidate)
    for table_path in (
        "Results.Metadata.StudyManifest.Records",
        "Results.Metadata.StudyManifest.Subjects",
        "Results.Availability",
    ):
        for column in ("Group", "Condition", "Session", "Timepoint"):
            candidate = f"{table_path}.{column}"
            if _path_exists(document, candidate):
                target_candidates.append(candidate)
                covariate_candidates.append(candidate)
    warnings: list[str] = []
    if not identity_candidates:
        warnings.append(
            "没有找到 Results 内显式的观察/记录身份字段；本文件不能凭文件名或行序建立样本身份。"
        )
    if not feature_candidates:
        warnings.append("没有检测到可由当前能力注册表解释的 PYfNIRs 特征输出。")
    if "Kind" not in results["fields"]:
        warnings.append("该 Results 是旧式无版本结构；仅能检查已登记的固定字段形态。")
    return api.SourceInspection(
        source_path=source_path,
        source_format="matlab_raw_results",
        available_adapters=(adapter_id,),
        fields=tuple(fields),
        feature_candidates=tuple(feature_candidates),
        identity_candidates=tuple(identity_candidates),
        target_candidates=tuple(target_candidates),
        covariate_candidates=tuple(covariate_candidates),
        warnings=tuple(warnings),
    )


def _inspect_study_document(
    document: Mapping[str, Any], source_path: Path, adapter_id: str
) -> api.SourceInspection:
    """Inspect an already normalized, schema-1 study without reinterpreting it.

    ``study-defined`` candidates mean only that the typed export already has a
    FeatureDefinition and scalar Values rows to carry through. They do not
    attest to the native computation or map unknown metrics into the raw
    Results capability registry.
    """
    tables = document["tables"]
    fields: list[api.SourceField] = []
    for table_name, table in tables.items():
        rows = table["rows"]
        columns = table["columns"]
        row_count = len(rows)
        fields.append(
            api.SourceField(
                f"study.{table_name}",
                (row_count, len(columns)),
                "table",
                "observation" if table_name == "Observations" else None,
            )
        )
        for column in columns:
            name = column["name"]
            values = [row[name] for row in rows]
            first = values[0] if values else None
            value_shape = _shape(first, f"study.{table_name}.{name}") if isinstance(first, Mapping) else ()
            fields.append(
                api.SourceField(
                    f"study.{table_name}.{name}",
                    (row_count,) + value_shape,
                    str(column.get("matlab_class", first.get("matlab_class", "unknown") if isinstance(first, Mapping) else "unknown")),
                    _study_field_grain(table_name, name),
                )
            )

    value_rows = tables["Values"]["rows"]
    value_counts: dict[str, int] = {}
    for index, row in enumerate(value_rows):
        feature_id = _study_text(row["FeatureID"], f"Values[{index}].FeatureID")
        value_counts[feature_id] = value_counts.get(feature_id, 0) + 1

    candidates: list[api.FeatureCandidate] = []
    for index, row in enumerate(tables["FeatureDefinitions"]["rows"]):
        feature_id = _study_text(row["FeatureID"], f"FeatureDefinitions[{index}].FeatureID")
        metric = _study_text(row["Metric"], f"FeatureDefinitions[{index}].Metric")
        unit = _study_text(row["Unit"], f"FeatureDefinitions[{index}].Unit", allow_empty=True)
        candidates.append(
            api.FeatureCandidate(
                capability_id=STUDY_DEFINED_CAPABILITY_ID,
                source_path="study.Values",
                shape=(value_counts.get(feature_id, 0),),
                unit=unit or None,
                axes={},
                allowed_summaries=(),
                allowed_complex_projections=(),
                status="supported",
                reason=(
                    f"现有规范 FeatureDefinition：FeatureID={feature_id}，Metric={metric}。"
                    "仅按已存在的 FeatureID 搬运 study.Values；不重新计算，也不代表该 Metric 已通过 raw 32 项能力验证。"
                ),
            )
        )

    observation_columns = _study_column_names(tables["Observations"])
    pair_columns = _study_column_names(tables["PairLinks"])
    identity_candidates = tuple(
        f"study.Observations.{name}"
        for name in ("ObservationID", "RecordID", "SubjectID", "PairObservationID", "SourceID")
        if name in observation_columns
    ) + tuple(
        f"study.PairLinks.{name}"
        for name in ("PairObservationID", "PairID")
        if name in pair_columns
    )
    target_candidates = tuple(
        f"study.Observations.{name}"
        for name in ("Group", "Condition")
        if name in observation_columns
    ) + tuple(
        f"study.PairLinks.{name}"
        for name in ("Condition",)
        if name in pair_columns
    )
    covariate_candidates = tuple(
        f"study.Observations.{name}"
        for name in observation_columns
        if name in {"Group", "Condition", "Session", "Timepoint"} or name.startswith("Cov_")
    ) + tuple(
        f"study.PairLinks.{name}"
        for name in ("Condition", "Session", "Timepoint")
        if name in pair_columns
    )
    return api.SourceInspection(
        source_path=source_path,
        source_format="pyfnirs_study_export",
        available_adapters=(STUDY_EXPORT_ADAPTER_ID, STUDY_MAT_ADAPTER_ID),
        fields=tuple(fields),
        feature_candidates=tuple(candidates),
        identity_candidates=identity_candidates,
        target_candidates=target_candidates,
        covariate_candidates=covariate_candidates,
        warnings=(
            "study-defined 只表示规范 study.Values 中已有可搬运的标量特征值；不等于 raw Results 特征算法已验证。",
        ),
    )


def _study_field_grain(table_name: str, field_name: str) -> str | None:
    if table_name == "Values":
        return "observation_feature"
    if table_name == "Observations":
        return "observation"
    if table_name == "PairLinks":
        return "pair"
    if table_name == "Sources":
        return "source"
    return None


def _study_column_names(table: Mapping[str, Any]) -> tuple[str, ...]:
    columns = table.get("columns", ())
    return tuple(
        column["name"]
        for column in columns
        if isinstance(column, Mapping) and isinstance(column.get("name"), str)
    )


def _study_text(node: Mapping[str, Any], label: str, *, allow_empty: bool = False) -> str:
    value = _decode_scalar(node, label)
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise AdapterError(f"{label} must be text")
    return value


def _walk_fields(
    node: Mapping[str, Any],
    path: str,
    output: list[api.SourceField],
    *,
    depth: int,
) -> None:
    if depth > 10:
        return
    if not isinstance(node, Mapping) or not isinstance(node.get("matlab_class"), str):
        return
    shape = _shape(node, path)
    class_name = node["matlab_class"]
    grain = "record" if path.startswith("Results.Availability") or "Record" in path else None
    output.append(api.SourceField(path, shape, class_name, grain))
    fields = node.get("fields")
    if isinstance(fields, Mapping):
        for name, child in fields.items():
            if isinstance(name, str) and isinstance(child, Mapping):
                _walk_fields(child, f"{path}.{name}", output, depth=depth + 1)
    if class_name == "table" and isinstance(node.get("table"), Mapping):
        table = node["table"]
        columns = table.get("columns", ())
        rows = table.get("rows", ())
        if isinstance(columns, Sequence) and isinstance(rows, Sequence):
            for column in columns:
                if not isinstance(column, Mapping) or not isinstance(column.get("name"), str):
                    continue
                name = column["name"]
                values = [row.get(name) for row in rows if isinstance(row, Mapping)]
                child = values[0] if values and isinstance(values[0], Mapping) else None
                if child is None:
                    continue
                first_shape = _shape(child, f"{path}.{name}")
                output.append(
                    api.SourceField(
                        f"{path}.{name}",
                        (len(rows),) + first_shape,
                        str(column.get("matlab_class", child.get("matlab_class", "unknown"))),
                        "record" if any(token in name.lower() for token in ("record", "subject")) else None,
                    )
                )
    elements = node.get("elements")
    if class_name == "struct" and isinstance(elements, Sequence) and elements:
        first = elements[0]
        if isinstance(first, Mapping) and isinstance(first.get("fields"), Mapping):
            for name, child in first["fields"].items():
                if isinstance(name, str) and isinstance(child, Mapping):
                    _walk_fields(child, f"{path}{{1}}.{name}", output, depth=depth + 1)


def _raw_feature_candidates(document: Mapping[str, Any]) -> list[api.FeatureCandidate]:
    results = document["variables"]["Results"]
    candidates: list[api.FeatureCandidate] = []

    ph = _candidate_persistent_homology(document)
    if ph is not None:
        candidates.append(ph)

    static_fc = _candidate_static_fc(document)
    if static_fc is not None:
        candidates.append(static_fc)

    mvar = _candidate_mvar_granger(document)
    if mvar is not None:
        candidates.append(mvar)

    pair = _candidate_cross_brain_ibs(document)
    if pair is not None:
        candidates.append(pair)

    hurst_path = "Results.data.all"
    if _path_exists(document, hurst_path):
        node = _resolve_raw_node(document, hurst_path)
        if _is_hurst_output(document, node):
            candidates.append(
                api.FeatureCandidate(
                    capability_id="01",
                    source_path=hurst_path,
                    shape=_shape(node, hurst_path),
                    unit=None,
                    axes={},
                    allowed_summaries=(),
                    allowed_complex_projections=(),
                    status="unverified",
                    reason=(
                        "检测到与 Hurst 固定 cell 形态相符的结果，但源文件未保存完整模型参数、"
                        "长度/采样率和明确节点映射指纹；不允许进入模型输入。"
                    ),
                )
            )
    return candidates


def _is_hurst_output(document: Mapping[str, Any], node: Mapping[str, Any] | _TableColumn) -> bool:
    """Recognize only the current Hurst pipeline's tagged two-cell layout."""
    try:
        if _text_field(document, "Results.Metadata.MissingnessAudit.Algorithm") != "Hurst":
            return False
    except AdapterError:
        return False
    if not isinstance(node, Mapping) or node.get("matlab_class") != "cell":
        return False
    try:
        if _shape(node, "Results.data.all") != (1, 2):
            return False
    except AdapterError:
        return False
    entries = node.get("elements")
    if not isinstance(entries, Sequence) or len(entries) != 2:
        return False
    expected_hb = {"HbO", "HbR", "HbT"}
    for entry in entries:
        fields = entry.get("fields") if isinstance(entry, Mapping) else None
        if not isinstance(fields, Mapping) or not expected_hb.issubset(fields):
            return False
        for hb in expected_hb:
            value = fields[hb]
            if not isinstance(value, Mapping) or value.get("matlab_class") not in _NUMERIC_CLASSES:
                return False
            if "elements" not in value or value.get("real_elements") is not None or value.get("imag_elements") is not None:
                return False
            try:
                if _shape_size(_shape(value, f"Results.data.all{{?}}.{hb}")) != len(value["elements"]):
                    return False
            except (AdapterError, TypeError):
                return False
    return True


def _candidate_persistent_homology(document: Mapping[str, Any]) -> api.FeatureCandidate | None:
    root_path = "Results.data.PersistentHomology"
    if not _path_exists(document, root_path):
        return None
    try:
        root = _resolve_raw_node(document, root_path)
        hb_fields = tuple(name for name in _field_names(root) if name in {"HbO", "HbR", "HbT"})
        metadata = _resolve_raw_node(document, "Results.Metadata.PersistentHomology")
        fields = metadata.get("fields", {})
        options_node = fields.get("Options") if isinstance(fields, Mapping) else None
        options = _plain_mapping(options_node, "Results.Metadata.PersistentHomology.Options")
        input_semantics = options.get("InputSemantics")
        allowed_semantics = {"absolute_correlation_similarity", "positive_similarity", "rank_similarity"}
        labels = _plain_text_list(fields.get("NodeLabels"), "PersistentHomology.NodeLabels")
        if input_semantics not in allowed_semantics:
            raise AdapterError("Persistent homology needs an explicit dimensionless similarity input semantic")
        if not labels or len(labels) != len(set(labels)):
            raise AdapterError("Persistent homology has no unique saved node order")
        components: set[str] = set()
        for hb in hb_fields:
            status = _text_field(document, f"{root_path}.{hb}.Status")
            if status != "ok":
                continue
            for dimension in ("H0", "H1"):
                for component in (
                    "TotalPersistence",
                    "PersistenceEntropy",
                    "FinitePositiveIntervalCount",
                    "InfiniteIntervalCount",
                ):
                    path = f"{root_path}.{hb}.Features.{dimension}.{component}"
                    if _path_exists(document, path):
                        components.add(f"{dimension}:{component}")
        if not components:
            raise AdapterError("No status=ok scalar persistent-homology summaries were found")
        parameter_fingerprint = _sha256_typed(options_node, fields.get("DistanceFormula"))
        mapping_fingerprint = _sha256_value(labels)
        if not parameter_fingerprint or not mapping_fingerprint:
            raise AdapterError("Persistent-homology parameter or node mapping fingerprint is unavailable")
        cap = _REGISTRY["24"]
        status, reason = _candidate_status("24", "Persistent homology summaries have explicit options and node labels.")
        if options.get("ExternalLibrary") != "none_internal_matlab":
            status = "unverified"
            reason = "持久同调依赖版本未与已登记的 MATLAB 实现一致。"
        return api.FeatureCandidate(
            capability_id="24",
            source_path=root_path,
            shape=_shape(root, root_path),
            unit="dimensionless",
            axes={
                "hemoglobin": hb_fields,
                "input_semantics": (str(input_semantics),),
                "summary": tuple(sorted(components)),
            },
            allowed_summaries=(),
            allowed_complex_projections=(),
            status=status,
            reason=reason,
        )
    except AdapterError as exc:
        return api.FeatureCandidate(
            capability_id="24",
            source_path=root_path,
            shape=_safe_shape(document, root_path),
            unit=None,
            axes={},
            allowed_summaries=(),
            allowed_complex_projections=(),
            status="unverified",
            reason=f"未验证持久同调输出：{exc}",
        )


def _candidate_static_fc(document: Mapping[str, Any]) -> api.FeatureCandidate | None:
    root_path = "Results.data.all"
    if not _path_exists(document, root_path):
        return None
    try:
        data = _resolve_raw_node(document, root_path)
        hb_fields = tuple(name for name in _field_names(data) if name in {"HbO", "HbR", "HbT"})
        if not hb_fields:
            return None
        metadata = _resolve_raw_node(document, "Results.Metadata.FC")
        model = _number_field(document, "Results.Metadata.FC.ModelIndex")
        if model != 1:
            raise AdapterError("Only Pearson static FC is currently adapted; other models remain unverified")
        if _text_field(document, "Results.Metadata.FC.Kind") != "static":
            raise AdapterError("FC metadata does not identify a static matrix")
        parameter_fingerprint = _text_field(document, "Results.Metadata.FC.ParameterFingerprint")
        nodes = _plain_text_list(_field(metadata, "NodeOrder"), "Results.Metadata.FC.NodeOrder")
        if not nodes or len(nodes) != len(set(nodes)):
            raise AdapterError("FC node order must be explicit and unique")
        for hb in hb_fields:
            matrix = _resolve_raw_node(document, f"{root_path}.{hb}")
            if _shape(matrix, f"{root_path}.{hb}") != (len(nodes), len(nodes)):
                raise AdapterError(f"{hb} FC matrix shape does not match saved node order")
            values = _numeric_vector(matrix, f"{root_path}.{hb}")
            if not _symmetric(values, len(nodes), tolerance=1e-12):
                raise AdapterError(f"{hb} FC matrix is not symmetric within saved precision")
        if not parameter_fingerprint:
            raise AdapterError("FC parameter fingerprint is missing")
        status, reason = _candidate_status("07", "Pearson static FC matrix, node order, and parameters are present.")
        return api.FeatureCandidate(
            capability_id="07",
            source_path=root_path,
            shape=_shape(_resolve_raw_node(document, f"{root_path}.{hb_fields[0]}"), root_path),
            unit="dimensionless",
            axes={
                "algorithm": ("Pearson",),
                "hemoglobin": hb_fields,
                "node_a": tuple(nodes),
                "node_b": tuple(nodes),
            },
            allowed_summaries=(),
            allowed_complex_projections=(),
            status=status,
            reason=reason,
        )
    except AdapterError as exc:
        return api.FeatureCandidate(
            capability_id="07",
            source_path=root_path,
            shape=_safe_shape(document, root_path),
            unit=None,
            axes={},
            allowed_summaries=(),
            allowed_complex_projections=(),
            status="unverified",
            reason=f"未验证静态无向 FC：{exc}",
        )


def _candidate_mvar_granger(document: Mapping[str, Any]) -> api.FeatureCandidate | None:
    root_path = "Results.data.WithinBrainMVARGranger"
    if not _path_exists(document, root_path):
        return None
    try:
        root = _resolve_raw_node(document, root_path)
        hb_fields = tuple(name for name in _field_names(root) if name in {"HbO", "HbR"})
        if not hb_fields:
            return None
        metadata = _resolve_raw_node(document, "Results.Metadata.MVARGranger")
        metadata_fields = metadata.get("fields", {})
        formula = _text_field(document, "Results.Metadata.MVARGranger.FormulaVersion")
        convention = _text_field(document, "Results.Metadata.MVARGranger.DirectionConvention")
        options_node = metadata_fields.get("Options") if isinstance(metadata_fields, Mapping) else None
        options = _plain_mapping(options_node, "Results.Metadata.MVARGranger.Options")
        if formula != "conditional_log_residual_variance_ratio_v1":
            raise AdapterError("MVAR formula version is not frozen to the registered log-ratio definition")
        if convention != "row_source_column_target":
            raise AdapterError("MVAR row/column direction convention is absent or different")
        window = options.get("Window")
        if not isinstance(window, Mapping) or window.get("Enabled") is not False:
            raise AdapterError("Windowed MVAR-Granger is not supported by this scalar edge adapter")
        node_labels = _roi_labels(document)
        if not node_labels or len(node_labels) != len(set(node_labels)):
            raise AdapterError("MVAR output lacks a unique saved ROI node order")
        for hb in hb_fields:
            status = _text_field(document, f"{root_path}.{hb}.Status")
            if status != "ok":
                raise AdapterError(f"MVAR output for {hb} has status {status!r}, not 'ok'")
            matrix_path = f"{root_path}.{hb}.GrangerStrength"
            matrix = _resolve_raw_node(document, matrix_path)
            if _shape(matrix, matrix_path) != (len(node_labels), len(node_labels)):
                raise AdapterError(f"{hb} MVAR matrix shape does not match ROI node labels")
            _numeric_vector(matrix, matrix_path)
        parameter_fingerprint = _sha256_typed(
            options_node,
            metadata_fields.get("SamplingRate"),
            metadata_fields.get("FormulaVersion"),
        )
        if not parameter_fingerprint:
            raise AdapterError("MVAR parameter fingerprint is unavailable")
        status, reason = _candidate_status("14", "Full-record MVAR-Granger metadata, direction, and ROI order are present.")
        return api.FeatureCandidate(
            capability_id="14",
            source_path=root_path,
            shape=_shape(_resolve_raw_node(document, f"{root_path}.{hb_fields[0]}.GrangerStrength"), root_path),
            unit="dimensionless",
            axes={
                "formula": (formula,),
                "hemoglobin": hb_fields,
                "source_node": tuple(node_labels),
                "target_node": tuple(node_labels),
            },
            allowed_summaries=(),
            allowed_complex_projections=(),
            status=status,
            reason=reason,
        )
    except AdapterError as exc:
        return api.FeatureCandidate(
            capability_id="14",
            source_path=root_path,
            shape=_safe_shape(document, root_path),
            unit=None,
            axes={},
            allowed_summaries=(),
            allowed_complex_projections=(),
            status="unverified",
            reason=f"未验证有向 Granger 输出：{exc}",
        )


def _candidate_cross_brain_ibs(document: Mapping[str, Any]) -> api.FeatureCandidate | None:
    root_path = "Results.data.all"
    if not _path_exists(document, root_path):
        return None
    try:
        root = _resolve_raw_node(document, root_path)
        if not isinstance(root, Mapping) or root.get("matlab_class") != "cell":
            return None
        entries = root.get("elements", ())
        if not entries:
            return None
        first = entries[0]
        hb_fields = tuple(name for name in _field_names(first) if name in {"HbO", "HbR", "HbT"})
        if not hb_fields:
            return None
        pairing_path = "Results.Metadata.Pairing"
        pairing = _plain_mapping(_resolve_raw_node(document, pairing_path), pairing_path)
        roles = _plain_text_list(_field(_resolve_raw_node(document, pairing_path), "Roles"), f"{pairing_path}.Roles")
        subjects = _plain_text_list(_field(_resolve_raw_node(document, pairing_path), "SubjectIDs"), f"{pairing_path}.SubjectIDs")
        record_node = _optional_resolve(document, f"{pairing_path}.InputRecordIDs")
        if record_node is None:
            record_node = _optional_resolve(document, f"{pairing_path}.RecordIDs")
        records = _plain_text_list(record_node, f"{pairing_path}.InputRecordIDs") if record_node else []
        if pairing.get("PairingMode") != "study_manifest_pairid" or not pairing.get("PairID"):
            raise AdapterError("IBS needs an explicit StudyManifest PairID")
        if len(roles) != 2 or len(set(roles)) != 2 or len(subjects) != 2 or len(set(subjects)) != 2 or len(records) != 2:
            raise AdapterError("IBS needs two ordered role, subject, and record identities")
        labels_a = _optional_text_list(document, f"{pairing_path}.NodeLabelsA")
        labels_b = _optional_text_list(document, f"{pairing_path}.NodeLabelsB")
        if not labels_a or not labels_b:
            raise AdapterError("IBS source does not persist node labels for both roles")
        sync = _optional_resolve(document, "Results.Metadata.PairedEventMotion")
        if sync is None or _text_field(document, "Results.Metadata.PairedEventMotion.Status") != "available":
            raise AdapterError("IBS source has no available pair synchronization evidence")
        ibs_metadata = _optional_resolve(document, "Results.Metadata.IBS")
        if ibs_metadata is None:
            raise AdapterError("IBS source does not persist its model and sampling parameters")
        parameter_fingerprint = _text_field(document, "Results.Metadata.IBS.ParameterFingerprint")
        if not parameter_fingerprint:
            raise AdapterError("IBS parameter fingerprint is missing")
        for hb in hb_fields:
            matrix_path = f"{root_path}{{1}}.{hb}"
            matrix = _resolve_raw_node(document, matrix_path)
            if _shape(matrix, matrix_path) != (len(labels_a), len(labels_b)):
                raise AdapterError("IBS matrix shape does not match both saved role node orders")
            _numeric_vector(matrix, matrix_path)
        cap = _REGISTRY["15"]
        status, reason = _candidate_status("15", "Pair identities, roles, synchronization, node orders, and parameters are explicit.")
        return api.FeatureCandidate(
            capability_id="15",
            source_path=root_path,
            shape=_shape(_resolve_raw_node(document, f"{root_path}{{1}}.{hb_fields[0]}"), root_path),
            unit="dimensionless",
            axes={
                "hemoglobin": hb_fields,
                "role_a": (roles[0],),
                "role_b": (roles[1],),
                "node_a": tuple(labels_a),
                "node_b": tuple(labels_b),
            },
            allowed_summaries=(),
            allowed_complex_projections=(),
            status=status,
            reason=reason,
        )
    except AdapterError as exc:
        return api.FeatureCandidate(
            capability_id="15",
            source_path=root_path,
            shape=_safe_shape(document, root_path),
            unit=None,
            axes={},
            allowed_summaries=(),
            allowed_complex_projections=(),
            status="unverified",
            reason=f"未验证跨脑 IBS 输出：{exc}",
        )


def _candidate_status(capability_id: str, ready_reason: str) -> tuple[str, str]:
    entry = _REGISTRY.get(capability_id)
    if entry is None:
        return "unsupported", "能力 ID 不在 PYfNIRs 注册表中。"
    status = entry.get("converterActualStatus")
    if status not in {"supported", "conditionally_supported"}:
        return "unverified", f"转换器状态为 {status!r}；尚未通过本阶段验证。"
    return str(status), ready_reason


def _select_raw_rows(
    document: Mapping[str, Any], selection: api.ConversionSelection
) -> tuple[tuple[Mapping[str, Any], ...], tuple[Mapping[str, Any], ...]]:
    if not selection.feature_selections:
        raise AdapterError("至少需要选择一个已验证特征")
    rows: list[Mapping[str, Any]] = []
    definitions: list[Mapping[str, Any]] = []
    feature_ids: set[str] = set()
    for feature in selection.feature_selections:
        if feature.feature_id in feature_ids:
            raise AdapterError(f"FeatureID must be unique: {feature.feature_id}")
        feature_ids.add(feature.feature_id)
        _require_registered_selectable(feature.capability_id)
        if feature.source_path != _raw_path_for_capability(feature.capability_id):
            raise AdapterError(
                f"Capability {feature.capability_id} does not permit source path {feature.source_path!r}"
            )
        if feature.frequency_band_hz is not None or feature.time_window_seconds is not None:
            raise AdapterError("This raw adapter does not permit unregistered frequency bands or time windows")
        if feature.complex_projection is not None or feature.summary_method is not None or feature.summary_parameters:
            raise AdapterError("This raw adapter requires a registered explicit projection or summary; none is permitted here")
        if feature.capability_id == "24":
            row, definition = _select_ph(document, selection, feature)
        elif feature.capability_id == "07":
            row, definition = _select_static_fc(document, selection, feature)
        elif feature.capability_id == "14":
            row, definition = _select_mvar(document, selection, feature)
        elif feature.capability_id == "15":
            row, definition = _select_ibs(document, selection, feature)
        else:
            raise AdapterError(f"No implemented raw Results adapter for capability {feature.capability_id}")
        rows.append(row)
        definitions.append(definition)
    return tuple(rows), tuple(definitions)


def _select_study_rows(
    document: Mapping[str, Any], selection: api.ConversionSelection
) -> tuple[tuple[Mapping[str, Any], ...], tuple[Mapping[str, Any], ...]]:
    tables = document["tables"]
    definition_rows = tables["FeatureDefinitions"]["rows"]
    value_rows = tables["Values"]["rows"]
    definitions_by_id: dict[str, Mapping[str, Any]] = {}
    for index, row in enumerate(definition_rows):
        feature_id = _text_cell(row["FeatureID"], f"FeatureDefinitions[{index}].FeatureID")
        definitions_by_id[feature_id] = row
    selected_rows: list[Mapping[str, Any]] = []
    selected_definitions: list[Mapping[str, Any]] = []
    seen_features: set[str] = set()
    for feature in selection.feature_selections:
        if feature.feature_id in seen_features:
            raise AdapterError(f"FeatureID must be unique: {feature.feature_id}")
        seen_features.add(feature.feature_id)
        if feature.capability_id != STUDY_DEFINED_CAPABILITY_ID:
            raise AdapterError("Schema-1 study.Value rows must use the study-defined transfer capability")
        if feature.source_path != "study.Values":
            raise AdapterError("Schema-1 study features must be selected from study.Values")
        if feature.axis_selection:
            raise AdapterError("study-defined values already have a complete FeatureDefinition; extra axes are not permitted")
        if feature.frequency_band_hz is not None or feature.time_window_seconds is not None:
            raise AdapterError("study.Values is already scalar and does not permit a new band/window projection")
        if feature.complex_projection is not None or feature.summary_method is not None or feature.summary_parameters:
            raise AdapterError("study.Values selections do not permit a second projection or summary")
        typed_definition = definitions_by_id.get(feature.feature_id)
        if typed_definition is None:
            raise AdapterError(f"FeatureID is not present in study.FeatureDefinitions: {feature.feature_id}")
        definition = {name: _decode_scalar(typed, f"FeatureDefinitions.{feature.feature_id}.{name}")
                      for name, typed in typed_definition.items()}
        if definition.get("FeatureID") != feature.feature_id:
            raise AdapterError("Selected FeatureID does not exactly match its existing FeatureDefinition")
        matching = [row for row in value_rows if _text_cell(row["FeatureID"], "Values.FeatureID") == feature.feature_id]
        if not matching:
            raise AdapterError(f"study.Values contains no rows for FeatureID {feature.feature_id}")
        for value_index, value_row in enumerate(matching):
            observation_id = _text_cell(value_row["ObservationID"], f"Values[{value_index}].ObservationID")
            number = _decode_scalar(value_row["Value"], f"Values[{value_index}].Value")
            valid = _decode_scalar(value_row["IsValid"], f"Values[{value_index}].IsValid")
            reason = _text_cell(value_row["MissingReason"], f"Values[{value_index}].MissingReason", allow_empty=True)
            if valid and (not isinstance(number, (int, float)) or isinstance(number, bool) or not math.isfinite(float(number))):
                raise AdapterError(f"Valid study value is not finite for ObservationID {observation_id}")
            if not valid and (not isinstance(number, float) or not math.isnan(number) or not reason):
                raise AdapterError(f"Invalid study value lacks its explicit NaN/reason for ObservationID {observation_id}")
            selected_rows.append({
                "ObservationID": observation_id,
                "FeatureID": feature.feature_id,
                "Value": number,
                "IsValid": bool(valid),
                "MissingReason": reason,
                "SourceID": _text_cell(value_row["SourceID"], f"Values[{value_index}].SourceID"),
            })
        selected_definitions.append(definition)
    return tuple(selected_rows), tuple(selected_definitions)


def _select_ph(
    document: Mapping[str, Any], selection: api.ConversionSelection, feature: api.FeatureSelection
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    axes = feature.axis_selection
    required = {"hemoglobin", "input_semantics", "summary"}
    _require_exact_axes(axes, required)
    if feature.source_path != "Results.data.PersistentHomology":
        raise AdapterError("Persistent homology source path does not match its registered adapter")
    hb = _axis_text(axes, "hemoglobin")
    input_semantics = _axis_text(axes, "input_semantics")
    summary = _axis_text(axes, "summary")
    if ":" not in summary:
        raise AdapterError("Persistent-homology summary must identify its homology dimension and scalar field")
    dimension, component = summary.split(":", 1)
    if dimension not in {"H0", "H1"}:
        raise AdapterError("Persistent-homology dimension must be H0 or H1")
    if component not in {"TotalPersistence", "PersistenceEntropy", "FinitePositiveIntervalCount", "InfiniteIntervalCount"}:
        raise AdapterError("Persistent-homology summary field is not registered")
    options = _plain_mapping(_resolve_raw_node(document, "Results.Metadata.PersistentHomology.Options"), "PersistentHomology.Options")
    if options.get("InputSemantics") != input_semantics:
        raise AdapterError("Selected persistent-homology input semantic does not match source metadata")
    labels = _plain_text_list(_resolve_raw_node(document, "Results.Metadata.PersistentHomology.NodeLabels"), "PersistentHomology.NodeLabels")
    if not labels or len(labels) != len(set(labels)):
        raise AdapterError("Persistent-homology node order is missing or duplicated")
    if _text_field(document, f"{feature.source_path}.{hb}.Status") != "ok":
        raise AdapterError(f"Persistent-homology output for {hb} is not status=ok")
    value_path = f"{feature.source_path}.{hb}.Features.{dimension}.{component}"
    value = _number_value(_resolve_raw_node(document, value_path), value_path)
    identity = _observation_id(document, selection)
    unit = "count" if component.endswith("Count") else "dimensionless"
    definition = _definition(
        feature,
        metric=f"PersistentHomology_{dimension}_{component}",
        level="GLOBAL",
        hemoglobin=hb,
        node_a="",
        node_b="",
        role_a="",
        role_b="",
        unit=unit,
        transform="none",
        direction="scalar",
        dimension="scalar",
        parameter_fingerprint=_sha256_typed(
            _resolve_raw_node(document, "Results.Metadata.PersistentHomology.Options"),
            _resolve_raw_node(document, "Results.Metadata.PersistentHomology.DistanceFormula"),
        ),
        mapping_fingerprint=_sha256_value(labels),
    )
    return _value_row(identity, feature.feature_id, value, "source_nonfinite"), definition


def _select_static_fc(
    document: Mapping[str, Any], selection: api.ConversionSelection, feature: api.FeatureSelection
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    axes = feature.axis_selection
    _require_exact_axes(axes, {"algorithm", "hemoglobin", "node_a", "node_b"})
    if _axis_text(axes, "algorithm") != "Pearson":
        raise AdapterError("Only the explicitly selected Pearson model is supported for static FC")
    if _number_field(document, "Results.Metadata.FC.ModelIndex") != 1:
        raise AdapterError("Source FC model is not Pearson")
    if _text_field(document, "Results.Metadata.FC.Kind") != "static":
        raise AdapterError("Source FC is not a static connection matrix")
    nodes = _plain_text_list(_resolve_raw_node(document, "Results.Metadata.FC.NodeOrder"), "FC.NodeOrder")
    if not nodes or len(nodes) != len(set(nodes)):
        raise AdapterError("FC node order must be explicit and unique")
    node_a = _axis_text(axes, "node_a")
    node_b = _axis_text(axes, "node_b")
    if node_a not in nodes or node_b not in nodes or nodes.index(node_a) >= nodes.index(node_b):
        raise AdapterError("Undirected FC selection requires node_a earlier than node_b in saved node order")
    hb = _axis_text(axes, "hemoglobin")
    matrix_path = f"Results.data.all.{hb}"
    matrix = _resolve_raw_node(document, matrix_path)
    values = _numeric_vector(matrix, matrix_path)
    size = len(nodes)
    if _shape(matrix, matrix_path) != (size, size) or not _symmetric(values, size, 1e-12):
        raise AdapterError("Pearson FC matrix shape or symmetry disagrees with its saved node order")
    i, j = nodes.index(node_a), nodes.index(node_b)
    value = values[i + j * size]
    definition = _definition(
        feature,
        metric="StaticFC_Pearson",
        level="ROI",
        hemoglobin=hb,
        node_a=node_a,
        node_b=node_b,
        role_a="",
        role_b="",
        unit="dimensionless",
        transform="none",
        direction="undirected",
        dimension="edge",
        parameter_fingerprint=_text_field(document, "Results.Metadata.FC.ParameterFingerprint"),
        mapping_fingerprint=_sha256_value(nodes),
    )
    return _value_row(_observation_id(document, selection), feature.feature_id, value, "source_nonfinite"), definition


def _select_mvar(
    document: Mapping[str, Any], selection: api.ConversionSelection, feature: api.FeatureSelection
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    axes = feature.axis_selection
    _require_exact_axes(axes, {"formula", "hemoglobin", "source_node", "target_node"})
    formula = _axis_text(axes, "formula")
    if formula != "conditional_log_residual_variance_ratio_v1":
        raise AdapterError("MVAR formula is not the registered conditional log residual-variance ratio")
    if _text_field(document, "Results.Metadata.MVARGranger.FormulaVersion") != formula:
        raise AdapterError("Selected MVAR formula differs from source metadata")
    if _text_field(document, "Results.Metadata.MVARGranger.DirectionConvention") != "row_source_column_target":
        raise AdapterError("MVAR direction convention must be row_source_column_target")
    options = _plain_mapping(_resolve_raw_node(document, "Results.Metadata.MVARGranger.Options"), "MVARGranger.Options")
    window = options.get("Window")
    if not isinstance(window, Mapping) or window.get("Enabled") is not False:
        raise AdapterError("Windowed MVAR-Granger is not supported")
    hb = _axis_text(axes, "hemoglobin")
    source_node = _axis_text(axes, "source_node")
    target_node = _axis_text(axes, "target_node")
    if source_node == target_node:
        raise AdapterError("A directed edge requires distinct source and target nodes")
    nodes = _roi_labels(document)
    if not nodes or len(nodes) != len(set(nodes)):
        raise AdapterError("MVAR output lacks a unique saved ROI node order")
    if source_node not in nodes or target_node not in nodes:
        raise AdapterError("MVAR edge node does not occur in the saved ROI order")
    status = _text_field(document, f"Results.data.WithinBrainMVARGranger.{hb}.Status")
    if status != "ok":
        raise AdapterError(f"MVAR output has status={status!r}")
    matrix_path = f"Results.data.WithinBrainMVARGranger.{hb}.GrangerStrength"
    matrix = _resolve_raw_node(document, matrix_path)
    values = _numeric_vector(matrix, matrix_path)
    size = len(nodes)
    if _shape(matrix, matrix_path) != (size, size):
        raise AdapterError("MVAR matrix shape does not match its ROI node order")
    value = values[nodes.index(source_node) + nodes.index(target_node) * size]
    definition = _definition(
        feature,
        metric="MVAR_GrangerStrength",
        level="ROI",
        hemoglobin=hb,
        node_a=source_node,
        node_b=target_node,
        role_a="",
        role_b="",
        unit="dimensionless",
        transform="none",
        direction="directed",
        dimension="edge",
        parameter_fingerprint=_sha256_typed(
            _resolve_raw_node(document, "Results.Metadata.MVARGranger.Options"),
            _resolve_raw_node(document, "Results.Metadata.MVARGranger.FormulaVersion"),
        ),
        mapping_fingerprint=_sha256_value(nodes),
    )
    return _value_row(_observation_id(document, selection), feature.feature_id, value, "source_nonfinite"), definition


def _select_ibs(
    document: Mapping[str, Any], selection: api.ConversionSelection, feature: api.FeatureSelection
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    axes = feature.axis_selection
    _require_exact_axes(axes, {"hemoglobin", "role_a", "role_b", "node_a", "node_b"})
    pairing = _plain_mapping(_resolve_raw_node(document, "Results.Metadata.Pairing"), "Pairing")
    if pairing.get("PairingMode") != "study_manifest_pairid":
        raise AdapterError("IBS pairing must come from an explicit StudyManifest PairID")
    if not pairing.get("PairID"):
        raise AdapterError("IBS PairID is missing")
    roles = _plain_text_list(_resolve_raw_node(document, "Results.Metadata.Pairing.Roles"), "Pairing.Roles")
    subjects = _plain_text_list(_resolve_raw_node(document, "Results.Metadata.Pairing.SubjectIDs"), "Pairing.SubjectIDs")
    record_node = _optional_resolve(document, "Results.Metadata.Pairing.InputRecordIDs") or _optional_resolve(
        document, "Results.Metadata.Pairing.RecordIDs"
    )
    records = _plain_text_list(record_node, "Pairing.RecordIDs") if record_node is not None else []
    if len(roles) != 2 or len(set(roles)) != 2 or len(subjects) != 2 or len(set(subjects)) != 2 or len(records) != 2:
        raise AdapterError("IBS needs two explicit ordered roles, subjects, and record IDs")
    role_a, role_b = _axis_text(axes, "role_a"), _axis_text(axes, "role_b")
    if (role_a, role_b) != tuple(roles):
        raise AdapterError("Selected IBS roles do not match source role order")
    labels_a = _plain_text_list(_resolve_raw_node(document, "Results.Metadata.Pairing.NodeLabelsA"), "Pairing.NodeLabelsA")
    labels_b = _plain_text_list(_resolve_raw_node(document, "Results.Metadata.Pairing.NodeLabelsB"), "Pairing.NodeLabelsB")
    if not labels_a or not labels_b or len(set(labels_a)) != len(labels_a) or len(set(labels_b)) != len(labels_b):
        raise AdapterError("IBS needs explicit, unique node orders for both roles")
    if _text_field(document, "Results.Metadata.PairedEventMotion.Status") != "available":
        raise AdapterError("IBS synchronization evidence is unavailable")
    parameter_fingerprint = _text_field(document, "Results.Metadata.IBS.ParameterFingerprint")
    if not parameter_fingerprint:
        raise AdapterError("IBS algorithm parameter fingerprint is missing")
    hb = _axis_text(axes, "hemoglobin")
    node_a, node_b = _axis_text(axes, "node_a"), _axis_text(axes, "node_b")
    if node_a not in labels_a or node_b not in labels_b:
        raise AdapterError("IBS node selection does not match the role-specific node orders")
    matrix_path = f"Results.data.all{{1}}.{hb}"
    matrix = _resolve_raw_node(document, matrix_path)
    values = _numeric_vector(matrix, matrix_path)
    if _shape(matrix, matrix_path) != (len(labels_a), len(labels_b)):
        raise AdapterError("IBS matrix shape does not match the role-specific node orders")
    value = values[labels_a.index(node_a) + labels_b.index(node_b) * len(labels_a)]
    definition = _definition(
        feature,
        metric="IBS_strength",
        level="PAIR",
        hemoglobin=hb,
        node_a=node_a,
        node_b=node_b,
        role_a=role_a,
        role_b=role_b,
        unit="dimensionless",
        transform="none",
        direction="cross_brain",
        dimension="edge",
        parameter_fingerprint=parameter_fingerprint,
        mapping_fingerprint=_sha256_value({"roles": roles, "node_order_a": labels_a, "node_order_b": labels_b}),
    )
    return _value_row(_observation_id(document, selection), feature.feature_id, value, "source_nonfinite"), definition


def _require_registered_selectable(capability_id: str) -> None:
    if capability_id not in _REGISTRY:
        raise AdapterError(f"Capability ID {capability_id!r} is not in the PYfNIRs registry")
    status = _REGISTRY[capability_id].get("converterActualStatus")
    if status not in {"supported", "conditionally_supported"}:
        raise AdapterError(f"Capability {capability_id} is not selectable; current status is {status!r}")


def _raw_path_for_capability(capability_id: str) -> str:
    paths = {
        "07": "Results.data.all",
        "14": "Results.data.WithinBrainMVARGranger",
        "15": "Results.data.all",
        "24": "Results.data.PersistentHomology",
    }
    if capability_id not in paths:
        raise AdapterError(f"Capability {capability_id} has no raw Results selection path")
    return paths[capability_id]


def _observation_id(document: Mapping[str, Any], selection: api.ConversionSelection) -> str:
    source_path = selection.identity.observation_id_source_path
    values = resolve_raw_source_path(document, source_path)
    nonmissing = [value for value in values if value is not None and (not isinstance(value, str) or value.strip())]
    if not nonmissing or any(not isinstance(value, str) for value in nonmissing):
        raise AdapterError("Observation ID mapping must resolve to explicit nonempty text values")
    distinct = tuple(dict.fromkeys(nonmissing))
    if len(distinct) != 1:
        raise AdapterError("One Results file resolves to multiple observation IDs; it cannot be treated as one sample")
    return distinct[0]


def _value_row(observation_id: str, feature_id: str, value: float, missing_reason: str) -> Mapping[str, Any]:
    valid = math.isfinite(float(value))
    return {
        "ObservationID": observation_id,
        "FeatureID": feature_id,
        "Value": float(value) if valid else math.nan,
        "IsValid": valid,
        "MissingReason": "" if valid else missing_reason,
    }


def _definition(
    feature: api.FeatureSelection,
    *,
    metric: str,
    level: str,
    hemoglobin: str,
    node_a: str,
    node_b: str,
    role_a: str,
    role_b: str,
    unit: str,
    transform: str,
    direction: str,
    dimension: str,
    parameter_fingerprint: str,
    mapping_fingerprint: str,
) -> Mapping[str, Any]:
    if not parameter_fingerprint or not mapping_fingerprint:
        raise AdapterError("Feature definition needs explicit parameter and mapping fingerprints")
    return {
        "FeatureID": feature.feature_id,
        "CapabilityID": feature.capability_id,
        "SourcePath": feature.source_path,
        "Metric": metric,
        "Level": level,
        "Hemoglobin": hemoglobin,
        "NodeA": node_a,
        "NodeB": node_b,
        "RoleA": role_a,
        "RoleB": role_b,
        "FrequencyLowHz": math.nan,
        "FrequencyHighHz": math.nan,
        "WindowStartSeconds": math.nan,
        "WindowEndSeconds": math.nan,
        "Scale": 1.0,
        "Unit": unit,
        "Transform": transform,
        "Direction": direction,
        "Dimension": dimension,
        "ParameterFingerprint": parameter_fingerprint,
        "MappingFingerprint": mapping_fingerprint,
    }


def _validate_definition_axes(
    definition: Mapping[str, Any], axis_selection: Mapping[str, Any]
) -> None:
    if not isinstance(axis_selection, Mapping):
        raise AdapterError("Feature axis selection must be a mapping")
    fields = {
        "level": "Level",
        "hemoglobin": "Hemoglobin",
        "node_a": "NodeA",
        "node_b": "NodeB",
        "role_a": "RoleA",
        "role_b": "RoleB",
    }
    required = {axis for axis, field in fields.items() if definition.get(field) not in (None, "", "none")}
    _require_exact_axes(axis_selection, required)
    for axis, field in fields.items():
        if axis in required and str(axis_selection[axis]) != str(definition[field]):
            raise AdapterError(f"Selected {axis} axis does not match the FeatureDefinition")


def _require_exact_axes(axes: Mapping[str, Any], required: set[str]) -> None:
    if not isinstance(axes, Mapping) or set(axes) != required:
        raise AdapterError(f"Feature axis selection must contain exactly: {', '.join(sorted(required))}")


def _axis_text(axes: Mapping[str, Any], name: str) -> str:
    value = axes.get(name)
    if not isinstance(value, str) or not value.strip():
        raise AdapterError(f"Feature axis {name!r} must be selected explicitly")
    return value


def _capability_for_metric(metric: str) -> str | None:
    normalized = metric.strip().casefold()
    matches: list[str] = []
    for capability_id, feature in _REGISTRY.items():
        if normalized in {capability_id.casefold(), str(feature.get("name", "")).strip().casefold()}:
            matches.append(capability_id)
            continue
        evidence = feature.get("sourceEvidence", {})
        code_files = evidence.get("sourceCodeFiles", ()) if isinstance(evidence, Mapping) else ()
        if isinstance(code_files, str):
            code_files = code_files.split()
        if any(Path(str(code_file)).stem.casefold() == normalized for code_file in code_files):
            matches.append(capability_id)
    return matches[0] if len(matches) == 1 else None


def _path_exists(document: Mapping[str, Any], path: str) -> bool:
    try:
        _resolve_raw_node(document, path)
        return True
    except AdapterError:
        return False


def _optional_resolve(document: Mapping[str, Any], path: str) -> Mapping[str, Any] | _TableColumn | None:
    try:
        return _resolve_raw_node(document, path)
    except AdapterError:
        return None


def _safe_shape(document: Mapping[str, Any], path: str) -> tuple[int, ...]:
    try:
        node = _resolve_raw_node(document, path)
        return _shape(node, path) if isinstance(node, Mapping) else (len(node.values),)
    except AdapterError:
        return ()


def _field(node: Mapping[str, Any] | _TableColumn, name: str) -> Mapping[str, Any] | _TableColumn:
    if not isinstance(node, Mapping) or not isinstance(node.get("fields"), Mapping):
        raise AdapterError(f"MATLAB value has no field {name}")
    result = node["fields"].get(name)
    if not isinstance(result, Mapping):
        raise AdapterError(f"MATLAB value has no field {name}")
    return result


def _field_names(node: Mapping[str, Any] | _TableColumn) -> tuple[str, ...]:
    if not isinstance(node, Mapping):
        return ()
    fields = node.get("fields")
    if isinstance(fields, Mapping):
        return tuple(name for name in fields if isinstance(name, str))
    if node.get("matlab_class") == "table":
        table = node.get("table", {})
        columns = table.get("columns", ()) if isinstance(table, Mapping) else ()
        return tuple(column["name"] for column in columns if isinstance(column, Mapping) and isinstance(column.get("name"), str))
    return ()


def _text_field(document: Mapping[str, Any], path: str) -> str:
    values = resolve_raw_source_path(document, path)
    if len(values) != 1 or not isinstance(values[0], str) or not values[0].strip():
        raise AdapterError(f"{path} must be an explicit nonempty text scalar")
    return values[0]


def _number_field(document: Mapping[str, Any], path: str) -> float:
    values = resolve_raw_source_path(document, path)
    if len(values) != 1 or isinstance(values[0], bool) or not isinstance(values[0], (int, float)):
        raise AdapterError(f"{path} must be a numeric scalar")
    if not math.isfinite(float(values[0])):
        raise AdapterError(f"{path} must be finite")
    return float(values[0])


def _text_cell(cell: Mapping[str, Any], label: str, *, allow_empty: bool = False) -> str:
    value = _decode_scalar(cell, label)
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise AdapterError(f"{label} must be text")
    return value


def _plain_text_list(node: Mapping[str, Any] | _TableColumn | None, label: str) -> list[str]:
    if node is None:
        return []
    if isinstance(node, _TableColumn):
        raw_values = node.values
        values = tuple(_decode_scalar(value, f"{label}[{index}]") for index, value in enumerate(raw_values))
    else:
        values = _flatten_typed(node, label)
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise AdapterError(f"{label} must contain only nonempty text values")
    return [str(value) for value in values]


def _optional_text_list(document: Mapping[str, Any], path: str) -> list[str]:
    node = _optional_resolve(document, path)
    if node is None:
        return []
    return _plain_text_list(node, path)


def _plain_mapping(node: Mapping[str, Any] | _TableColumn | None, label: str) -> dict[str, Any]:
    if not isinstance(node, Mapping) or not isinstance(node.get("fields"), Mapping):
        raise AdapterError(f"{label} must be a MATLAB scalar struct")
    values: dict[str, Any] = {}
    for name, child in node["fields"].items():
        if not isinstance(name, str) or not isinstance(child, Mapping):
            continue
        if child.get("matlab_class") in {"struct", "cell", "table"}:
            if child.get("matlab_class") == "struct" and isinstance(child.get("fields"), Mapping):
                values[name] = _plain_mapping(child, f"{label}.{name}")
            else:
                values[name] = tuple(_flatten_typed(child, f"{label}.{name}"))
        elif "elements" in child:
            values[name] = tuple(_flatten_typed(child, f"{label}.{name}"))
        else:
            values[name] = _decode_scalar(child, f"{label}.{name}")
    return values


def _number_value(node: Mapping[str, Any] | _TableColumn, label: str) -> float:
    if not isinstance(node, Mapping):
        raise AdapterError(f"{label} must be a numeric scalar")
    value = _decode_scalar(node, label)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AdapterError(f"{label} must be numeric")
    return float(value)


def _numeric_vector(node: Mapping[str, Any], label: str) -> tuple[float, ...]:
    if node.get("matlab_class") not in _NUMERIC_CLASSES:
        raise AdapterError(f"{label} must be a real MATLAB numeric array")
    values = _flatten_typed(node, label)
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in values):
        raise AdapterError(f"{label} contains a nonnumeric value")
    return tuple(float(value) for value in values)


def _symmetric(values: Sequence[float], size: int, tolerance: float) -> bool:
    if len(values) != size * size:
        return False
    for row in range(size):
        for column in range(row + 1, size):
            left = values[row + column * size]
            right = values[column + row * size]
            if math.isnan(left) or math.isnan(right):
                if not (math.isnan(left) and math.isnan(right)):
                    return False
            elif not math.isfinite(left) or not math.isfinite(right) or abs(left - right) > tolerance:
                return False
    return True


def _roi_labels(document: Mapping[str, Any]) -> list[str]:
    candidates = (
        "Results.Metadata.MVARGranger.NodeLabels",
        "Results.ROIdetail.ROI_name",
    )
    for candidate in candidates:
        if _path_exists(document, candidate):
            labels = _plain_text_list(_resolve_raw_node(document, candidate), candidate)
            if labels:
                return labels
    return []


def _sha256_typed(*values: Any) -> str:
    if not values or any(value is None for value in values):
        return ""
    payload = json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _sha256_value(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = [
    "AdapterError",
    "RAW_MAT_SCHEMA",
    "RAW_RESULTS_ADAPTER_ID",
    "STUDY_EXPORT_ADAPTER_ID",
    "STUDY_MAT_ADAPTER_ID",
    "STUDY_DEFINED_CAPABILITY_ID",
    "inspect_document",
    "resolve_raw_source_path",
    "select_feature_rows",
]
