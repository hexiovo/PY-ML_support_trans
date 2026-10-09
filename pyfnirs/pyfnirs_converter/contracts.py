"""Schema and integrity checks for the PYfNIRs MATLAB export contract.

MATLAB owns decoding of MATLAB tables. This module validates its typed JSON
export without guessing sample identity, feature order, labels, or missing
values.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import json
import math
from pathlib import Path
from typing import Any


EXPORT_SCHEMA = "pyfnirs.matlab-export/1"
MLINPUT_SCHEMA_VERSION = 1
REQUIRED_VALUE_COLUMNS = (
    "ObservationID",
    "FeatureID",
    "Value",
    "IsValid",
    "MissingReason",
    "SourceID",
)
BASE_TABLE_SCHEMAS: dict[str, tuple[tuple[str, str], ...]] = {
    "Sources": (
        ("SourceID", "string"), ("Kind", "string"), ("SchemaVersion", "double"),
        ("FilePath", "string"), ("PayloadPath", "string"), ("Fingerprint", "string"),
        ("Adapter", "string"), ("Capability", "string"),
    ),
    "Observations": (
        ("ObservationID", "string"), ("RecordID", "string"), ("SubjectID", "string"),
        ("PairObservationID", "string"), ("Group", "string"), ("Condition", "string"),
        ("Session", "string"), ("Timepoint", "string"), ("Include", "logical"),
        ("SourceID", "string"),
    ),
    "PairLinks": (
        ("PairObservationID", "string"), ("PairID", "string"), ("RecordIDA", "string"),
        ("RecordIDB", "string"), ("SubjectIDA", "string"), ("SubjectIDB", "string"),
        ("RoleA", "string"), ("RoleB", "string"), ("Condition", "string"),
        ("Session", "string"), ("Timepoint", "string"),
    ),
    "FeatureDefinitions": (
        ("FeatureID", "string"), ("Metric", "string"), ("Level", "string"),
        ("Hemoglobin", "string"), ("NodeA", "string"), ("NodeB", "string"),
        ("RoleA", "string"), ("RoleB", "string"), ("FrequencyLowHz", "double"),
        ("FrequencyHighHz", "double"), ("WindowStartSeconds", "double"),
        ("WindowEndSeconds", "double"), ("Scale", "double"), ("Unit", "string"),
        ("Transform", "string"), ("Direction", "string"), ("Dimension", "string"),
        ("ParameterFingerprint", "string"), ("MappingFingerprint", "string"),
    ),
    "Values": (
        ("ObservationID", "string"), ("FeatureID", "string"), ("Value", "double"),
        ("IsValid", "logical"), ("MissingReason", "string"), ("SourceID", "string"),
    ),
    "CovariateMetadata": (
        ("ColumnName", "string"), ("Level", "string"), ("Origin", "string"),
        ("DataKey", "string"),
    ),
}
SOURCE_CAPABILITIES = {"direct", "needs_summary", "preview", "unsupported"}
COVARIATE_LEVELS = {"subject", "record", "pair", "pair_observation"}
FEATURE_LEVELS = {"CH", "ROI", "PAIR", "NETWORK", "GLOBAL"}
FEATURE_HEMOGLOBINS = {"HbO", "HbR", "HbT", "none"}
FEATURE_TRANSFORMS = {"none", "fisher_z", "feature_difference", "other"}
FEATURE_DIRECTIONS = {"scalar", "undirected", "directed", "cross_brain"}
FEATURE_DIMENSIONS = {"scalar", "node", "edge", "window", "frequency", "scale", "tensor"}


class ContractError(ValueError):
    """Raised when an export violates the documented data contract."""


@dataclass(frozen=True)
class ExportSummary:
    """Identity and row counts extracted from a validated MATLAB export."""

    observation_ids: tuple[str, ...]
    feature_ids: tuple[str, ...]
    value_rows: int
    duplicate_value_keys: int = 0


def _fail(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def _sequence(value: Any, label: str) -> Sequence[Any]:
    _fail(
        isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)),
        f"{label} must be a sequence",
    )
    return value


def _shape_product(shape: Sequence[Any], label: str) -> int:
    result = 1
    for dimension in shape:
        _fail(
            isinstance(dimension, int) and not isinstance(dimension, bool) and dimension >= 0,
            f"{label} has an invalid MATLAB dimension",
        )
        result *= dimension
    return result


def _validate_typed_value(value: Any, label: str) -> None:
    _fail(isinstance(value, Mapping), f"{label} must be a typed MATLAB value")
    class_name = value.get("matlab_class")
    _fail(isinstance(class_name, str) and bool(class_name.strip()), f"{label}.matlab_class is required")
    shape = _sequence(value.get("shape"), f"{label}.shape")
    count = _shape_product(shape, f"{label}.shape")
    if "is_missing" in value:
        _fail(isinstance(value["is_missing"], bool), f"{label}.is_missing must be boolean")
    forms = [key for key in ("value", "elements", "fields", "table") if key in value]
    _fail(len(forms) == 1, f"{label} must have exactly one encoded value form")
    form = forms[0]
    if form == "value":
        _fail(isinstance(value["value"], str), f"{label}.value must be text")
        _fail(class_name in {"char", "string", "categorical", "datetime", "duration"} or count == 1,
              f"{label} scalar has a non-scalar MATLAB shape")
    elif form == "elements":
        elements = _sequence(value["elements"], f"{label}.elements")
        _fail(len(elements) == count, f"{label}.elements do not match the recorded shape")
        for index, element in enumerate(elements):
            _validate_typed_value(element, f"{label}.elements[{index}]")
    elif form == "fields":
        fields = value["fields"]
        _fail(isinstance(fields, Mapping), f"{label}.fields must be an object")
        for name, field_value in fields.items():
            _fail(isinstance(name, str) and bool(name), f"{label} has an invalid field name")
            _validate_typed_value(field_value, f"{label}.{name}")
    else:
        _validate_table(value["table"], f"{label}.table")


def _validate_table(table: Any, label: str) -> tuple[tuple[str, ...], Sequence[Mapping[str, Any]]]:
    _fail(isinstance(table, Mapping), f"{label} must be an object")
    columns = _sequence(table.get("columns"), f"{label}.columns")
    names: list[str] = []
    for index, column in enumerate(columns):
        _fail(isinstance(column, Mapping), f"{label}.columns[{index}] must be an object")
        name = column.get("name")
        matlab_class = column.get("matlab_class")
        _fail(isinstance(name, str) and bool(name.strip()), f"{label} has an empty column name")
        _fail(isinstance(matlab_class, str) and bool(matlab_class), f"{label}.{name} has no MATLAB class")
        names.append(name)
    _fail(len(names) == len(set(names)), f"{label} contains duplicate column names")
    rows = _sequence(table.get("rows"), f"{label}.rows")
    _fail(table.get("row_count") == len(rows), f"{label}.row_count does not match its rows")
    expected = set(names)
    for row_index, row in enumerate(rows):
        _fail(isinstance(row, Mapping), f"{label}.rows[{row_index}] must be an object")
        _fail(set(row) == expected, f"{label}.rows[{row_index}] has missing or unexpected columns")
        for name in names:
            _validate_typed_value(row[name], f"{label}.rows[{row_index}].{name}")
    row_names = table.get("row_names", [])
    _fail(isinstance(row_names, list), f"{label}.row_names must be a list")
    _fail(not row_names or len(row_names) == len(rows), f"{label}.row_names do not match its rows")
    return tuple(names), rows


def _scalar(value: Mapping[str, Any], label: str) -> Mapping[str, Any]:
    if "elements" in value:
        elements = _sequence(value["elements"], f"{label}.elements")
        shape = _sequence(value.get("shape"), f"{label}.shape")
        _fail(_shape_product(shape, f"{label}.shape") == 1 and len(elements) == 1,
              f"{label} must be a scalar, not an array")
        return _scalar(elements[0], label)
    _fail("value" in value, f"{label} must be a scalar text or number")
    return value


def _text(value: Mapping[str, Any], label: str, *, allow_empty: bool = False) -> str:
    cell = _scalar(value, label)
    class_name = cell.get("matlab_class")
    _fail(class_name in {"char", "string", "categorical"}, f"{label} must be a text identifier")
    if cell.get("is_missing", False):
        _fail(allow_empty, f"{label} must not be missing")
        return ""
    result = cell.get("value")
    _fail(isinstance(result, str), f"{label} must be text")
    if not allow_empty:
        _fail(bool(result.strip()), f"{label} must be nonempty")
    return result


def _number(value: Mapping[str, Any], label: str) -> Decimal:
    cell = _scalar(value, label)
    class_name = cell.get("matlab_class", "")
    numeric = class_name in {"double", "single"} or class_name.startswith(("int", "uint"))
    _fail(numeric, f"{label} must be a real MATLAB numeric scalar")
    raw = cell.get("value")
    _fail(isinstance(raw, str), f"{label} has no numeric text")
    try:
        result = Decimal(raw)
    except InvalidOperation as exc:
        raise ContractError(f"{label} is not valid numeric text") from exc
    _fail(not result.is_infinite(), f"{label} may not be infinite")
    return result


def _boolean(value: Mapping[str, Any], label: str) -> bool:
    cell = _scalar(value, label)
    _fail(cell.get("matlab_class") == "logical", f"{label} must be a MATLAB logical scalar")
    raw = cell.get("value")
    _fail(raw in {"true", "false"}, f"{label} must be true or false")
    return raw == "true"


def _table_field(table: Mapping[str, Any], name: str, label: str) -> tuple[tuple[str, ...], Sequence[Mapping[str, Any]]]:
    columns, rows = _validate_table(table, label)
    _fail(name in columns, f"{label} is missing required column {name}")
    return columns, rows


def _validate_contract_table(name: str, table: Any) -> tuple[tuple[str, ...], Sequence[Mapping[str, Any]]]:
    label = f"tables.{name}"
    names, rows = _validate_table(table, label)
    schema = BASE_TABLE_SCHEMAS[name]
    base_names = tuple(column_name for column_name, _ in schema)
    _fail(names[: len(base_names)] == base_names, f"{label} has missing or reordered schema columns")
    extras = names[len(base_names) :]
    _fail(name == "Observations" or not extras, f"{label} has unexpected columns")
    if name == "Observations":
        _fail(all(column.startswith("Cov_") for column in extras),
              "Observations may only extend the schema with Cov_ columns")
    descriptors = {column["name"]: column for column in table["columns"]}
    for column_name, expected_class in schema:
        _fail(descriptors[column_name].get("matlab_class") == expected_class,
              f"{label}.{column_name} must have MATLAB class {expected_class}")
    allowed_covariate_classes = {"string", "logical", "categorical", "double", "single"}
    allowed_covariate_classes.update(f"{prefix}{bits}" for prefix in ("int", "uint") for bits in ("8", "16", "32", "64"))
    for column_name in extras:
        _fail(descriptors[column_name].get("matlab_class") in allowed_covariate_classes,
              f"{label}.{column_name} has an unsupported covariate class")
    return names, rows


def _row_text(row: Mapping[str, Any], name: str, label: str, *, allow_empty: bool = False) -> str:
    return _text(row[name], f"{label}.{name}", allow_empty=allow_empty)


def _validate_feature_range(lower: Decimal, upper: Decimal, label: str) -> None:
    omitted = lower.is_nan() and upper.is_nan()
    valid = (
        lower.is_finite()
        and upper.is_finite()
        and lower >= 0
        and upper > lower
    )
    _fail(omitted or valid, f"{label} bounds must both be NaN or an ordered finite range")


def _validate_feature_definitions(rows: Sequence[Mapping[str, Any]]) -> None:
    """Mirror the source PYfNIRs feature-definition semantic contract."""
    for index, row in enumerate(rows):
        prefix = f"FeatureDefinitions[{index}]"
        for field in (
            "Metric", "Level", "Unit", "Transform", "Direction",
            "Dimension", "ParameterFingerprint",
        ):
            _row_text(row, field, prefix)

        level = _row_text(row, "Level", prefix)
        hemoglobin = _row_text(row, "Hemoglobin", prefix)
        transform = _row_text(row, "Transform", prefix)
        direction = _row_text(row, "Direction", prefix)
        dimension = _row_text(row, "Dimension", prefix)
        _fail(level in FEATURE_LEVELS, f"{prefix}.Level contains an unsupported value")
        _fail(hemoglobin in FEATURE_HEMOGLOBINS,
              f"{prefix}.Hemoglobin contains an unsupported value")
        _fail(transform in FEATURE_TRANSFORMS,
              f"{prefix}.Transform contains an unsupported value")
        _fail(direction in FEATURE_DIRECTIONS,
              f"{prefix}.Direction contains an unsupported value")
        _fail(dimension in FEATURE_DIMENSIONS,
              f"{prefix}.Dimension contains an unsupported value")

        node_a = _row_text(row, "NodeA", prefix, allow_empty=True)
        node_b = _row_text(row, "NodeB", prefix, allow_empty=True)
        role_a = _row_text(row, "RoleA", prefix, allow_empty=True)
        role_b = _row_text(row, "RoleB", prefix, allow_empty=True)
        if direction != "scalar":
            _fail(bool(node_a.strip()) and bool(node_b.strip()) and dimension == "edge",
                  f"{prefix} edges require both node labels and edge dimension")
        if direction == "cross_brain":
            _fail(bool(role_a.strip()) and bool(role_b.strip()),
                  f"{prefix} cross-brain edges require both role labels")

        frequency_low = _number(row["FrequencyLowHz"], f"{prefix}.FrequencyLowHz")
        frequency_high = _number(row["FrequencyHighHz"], f"{prefix}.FrequencyHighHz")
        _validate_feature_range(frequency_low, frequency_high, f"{prefix}.frequency")
        window_start = _number(row["WindowStartSeconds"], f"{prefix}.WindowStartSeconds")
        window_end = _number(row["WindowEndSeconds"], f"{prefix}.WindowEndSeconds")
        _validate_feature_range(window_start, window_end, f"{prefix}.window")
        scale = _number(row["Scale"], f"{prefix}.Scale")
        _fail(scale.is_nan() or (scale.is_finite() and scale > 0),
              f"{prefix}.Scale must be positive or NaN")


def validate_export_document(document: Any) -> ExportSummary:
    """Validate a typed JSON export and its explicit sample/feature references.

    The check preserves the MATLAB table row order. It never pivots, sorts,
    fills, or rewrites feature values.
    """
    _fail(isinstance(document, Mapping), "MATLAB export root must be an object")
    _fail(document.get("schema") == EXPORT_SCHEMA, "Unsupported MATLAB export schema")
    _fail(document.get("study_kind") == "PYfNIRsDA.Study", "Unexpected study.Kind")
    _fail(document.get("study_schema_version") == 1, "Unsupported study.SchemaVersion")
    _fail(isinstance(document.get("source_file_name"), str), "source_file_name is required")
    _fail(isinstance(document.get("matlab_version"), str), "matlab_version is required")
    metadata = document.get("study_metadata", {})
    _fail(isinstance(metadata, Mapping), "study_metadata must be an object")
    for name, value in metadata.items():
        _validate_typed_value(value, f"study_metadata.{name}")

    tables = document.get("tables")
    _fail(isinstance(tables, Mapping), "tables must be an object")
    for required in BASE_TABLE_SCHEMAS:
        _fail(required in tables, f"study is missing required table {required}")
    for name, table in tables.items():
        _fail(isinstance(name, str) and bool(name.strip()), "table name must be nonempty text")
        if name in BASE_TABLE_SCHEMAS:
            _validate_contract_table(name, table)
        else:
            _validate_table(table, f"tables.{name}")

    _, source_rows = _validate_contract_table("Sources", tables["Sources"])
    _, observation_rows = _validate_contract_table("Observations", tables["Observations"])
    _, pair_rows = _validate_contract_table("PairLinks", tables["PairLinks"])
    _, feature_rows = _validate_contract_table("FeatureDefinitions", tables["FeatureDefinitions"])
    _, values_rows = _validate_contract_table("Values", tables["Values"])
    _, covariate_rows = _validate_contract_table("CovariateMetadata", tables["CovariateMetadata"])

    source_ids = tuple(_row_text(row, "SourceID", f"Sources[{index}]") for index, row in enumerate(source_rows))
    _fail(source_ids, "Sources must contain at least one row")
    _fail(len(source_ids) == len(set(source_ids)), "Sources.SourceID values must be unique")
    source_id_set = set(source_ids)
    for index, row in enumerate(source_rows):
        prefix = f"Sources[{index}]"
        _row_text(row, "Kind", prefix)
        _row_text(row, "FilePath", prefix)
        _row_text(row, "Fingerprint", prefix)
        _row_text(row, "Adapter", prefix)
        capability = _row_text(row, "Capability", prefix)
        _fail(capability in SOURCE_CAPABILITIES, f"{prefix}.Capability is unsupported")
        schema_version = _number(row["SchemaVersion"], f"{prefix}.SchemaVersion")
        _fail(schema_version.is_finite() and schema_version >= 1 and schema_version == schema_version.to_integral_value(),
              f"{prefix}.SchemaVersion must be a positive integer")

    observation_ids_list: list[str] = []
    observation_by_id: dict[str, Mapping[str, Any]] = {}
    subject_by_record: dict[str, str] = {}
    pair_observation_ids: set[str] = set()
    pair_observation_by_id: dict[str, Mapping[str, Any]] = {}
    observation_column_names = tuple(column["name"] for column in tables["Observations"]["columns"])
    for index, row in enumerate(observation_rows):
        prefix = f"Observations[{index}]"
        observation_id = _row_text(row, "ObservationID", prefix)
        source_id = _row_text(row, "SourceID", prefix)
        _fail(source_id in source_id_set, f"{prefix}.SourceID references an unknown SourceID")
        _boolean(row["Include"], f"{prefix}.Include")
        record_id = _row_text(row, "RecordID", prefix, allow_empty=True)
        subject_id = _row_text(row, "SubjectID", prefix, allow_empty=True)
        pair_observation_id = _row_text(row, "PairObservationID", prefix, allow_empty=True)
        _row_text(row, "Group", prefix, allow_empty=True)
        _row_text(row, "Condition", prefix, allow_empty=True)
        _row_text(row, "Session", prefix, allow_empty=True)
        _row_text(row, "Timepoint", prefix, allow_empty=True)
        is_subject = bool(subject_id.strip())
        is_pair_observation = bool(pair_observation_id.strip())
        _fail(is_subject != is_pair_observation,
              f"{prefix} must identify exactly one subject or pair observation")
        if is_subject:
            _fail(bool(record_id.strip()), f"{prefix}.RecordID is required for subject observations")
            _fail(record_id not in subject_by_record, f"Duplicate subject RecordID: {record_id}")
            subject_by_record[record_id] = subject_id
        else:
            _fail(not record_id.strip(), f"{prefix}.RecordID must be blank for pair observations")
            pair_observation_ids.add(pair_observation_id)
            pair_observation_by_id[pair_observation_id] = row
        observation_ids_list.append(observation_id)
        observation_by_id[observation_id] = row

    observation_ids = tuple(observation_ids_list)
    _fail(observation_ids, "Observations must contain at least one row")
    _fail(len(observation_ids) == len(set(observation_ids)), "ObservationID values must be unique")
    feature_ids = tuple(
        _row_text(row, "FeatureID", f"FeatureDefinitions[{index}]")
        for index, row in enumerate(feature_rows)
    )
    _fail(observation_ids, "Observations must contain at least one row")
    _fail(feature_ids, "FeatureDefinitions must contain at least one row")
    _fail(len(observation_ids) == len(set(observation_ids)), "ObservationID values must be unique")
    _fail(len(feature_ids) == len(set(feature_ids)), "FeatureID values must be unique")
    _fail(values_rows, "Values must contain at least one row")
    _validate_feature_definitions(feature_rows)

    observations = set(observation_ids)
    features = set(feature_ids)
    seen_pairs: set[str] = set()
    pairs_by_id: dict[str, set[tuple[str, str]]] = {}
    for index, row in enumerate(pair_rows):
        prefix = f"PairLinks[{index}]"
        pair_observation_id = _row_text(row, "PairObservationID", prefix)
        pair_id = _row_text(row, "PairID", prefix)
        record_a = _row_text(row, "RecordIDA", prefix)
        record_b = _row_text(row, "RecordIDB", prefix)
        subject_a = _row_text(row, "SubjectIDA", prefix)
        subject_b = _row_text(row, "SubjectIDB", prefix)
        role_a = _row_text(row, "RoleA", prefix)
        role_b = _row_text(row, "RoleB", prefix)
        _fail(pair_observation_id not in seen_pairs, "PairLinks.PairObservationID values must be unique")
        seen_pairs.add(pair_observation_id)
        _fail(pair_observation_id in pair_observation_ids,
              f"{prefix}.PairObservationID does not resolve to an observation")
        _fail(record_a != record_b and subject_a != subject_b, f"{prefix} cannot pair a member with itself")
        _fail(subject_by_record.get(record_a) == subject_a, f"{prefix}.RecordIDA does not match SubjectIDA")
        _fail(subject_by_record.get(record_b) == subject_b, f"{prefix}.RecordIDB does not match SubjectIDB")
        observation = pair_observation_by_id[pair_observation_id]
        for field in ("Condition", "Session", "Timepoint"):
            _fail(
                _row_text(row, field, prefix, allow_empty=True)
                == _row_text(observation, field, f"Observations.PairObservationID={pair_observation_id}", allow_empty=True),
                f"{prefix}.{field} conflicts with the paired observation",
            )
        pairs_by_id.setdefault(pair_id, set()).add(tuple(sorted((subject_a, subject_b))))
    _fail(seen_pairs == pair_observation_ids, "PairLinks must map one-to-one to pair observations")
    _fail(all(len(member_sets) == 1 for member_sets in pairs_by_id.values()),
          "Rows with the same PairID must identify the same subject members")

    value_keys: set[tuple[str, str]] = set()
    for index, row in enumerate(values_rows):
        prefix = f"Values[{index}]"
        observation_id = _row_text(row, "ObservationID", prefix)
        feature_id = _row_text(row, "FeatureID", prefix)
        source_id = _row_text(row, "SourceID", prefix)
        _fail(observation_id in observations, f"{prefix} references unknown ObservationID {observation_id}")
        _fail(feature_id in features, f"{prefix} references unknown FeatureID {feature_id}")
        _fail(source_id in source_id_set, f"{prefix}.SourceID references an unknown SourceID")
        key = (observation_id, feature_id)
        _fail(key not in value_keys, f"Duplicate (ObservationID, FeatureID) key: {key}")
        value_keys.add(key)
        numeric_value = _number(row["Value"], f"{prefix}.Value")
        valid = _boolean(row["IsValid"], f"{prefix}.IsValid")
        reason = _row_text(row, "MissingReason", prefix, allow_empty=True)
        if valid:
            _fail(numeric_value.is_finite(), f"{prefix}.Value must be finite when IsValid is true")
            _fail(not reason.strip(), f"{prefix}.MissingReason must be blank when IsValid is true")
        else:
            _fail(numeric_value.is_nan(), f"{prefix}.Value must be NaN when IsValid is false")
            _fail(bool(reason.strip()), f"{prefix}.MissingReason is required when IsValid is false")

    covariate_columns = {name for name in observation_column_names if name.startswith("Cov_")}
    metadata_columns: set[str] = set()
    for index, row in enumerate(covariate_rows):
        prefix = f"CovariateMetadata[{index}]"
        column_name = _row_text(row, "ColumnName", prefix)
        level = _row_text(row, "Level", prefix)
        _row_text(row, "Origin", prefix)
        _row_text(row, "DataKey", prefix)
        _fail(level in COVARIATE_LEVELS, f"{prefix}.Level is unsupported")
        _fail(column_name in covariate_columns, f"{prefix}.ColumnName has no Cov_ observation column")
        _fail(column_name not in metadata_columns, f"Duplicate covariate metadata for {column_name}")
        metadata_columns.add(column_name)

    return ExportSummary(
        observation_ids=observation_ids,
        feature_ids=feature_ids,
        value_rows=len(values_rows),
    )


def load_export_document(path: str | Path) -> tuple[Mapping[str, Any], ExportSummary]:
    """Load and validate ``study_export.json`` written by the MATLAB bridge."""
    source = Path(path)
    try:
        document = json.loads(source.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ContractError(f"Cannot read MATLAB export {source}: {exc}") from exc
    return document, validate_export_document(document)


def _rows(value: Any, label: str) -> Sequence[Sequence[Any]]:
    rows = _sequence(value, label)
    return [_sequence(row, f"{label}[{index}]") for index, row in enumerate(rows)]


def _unique_text(values: Any, label: str) -> list[str]:
    sequence = _sequence(values, label)
    result: list[str] = []
    for index, item in enumerate(sequence):
        _fail(isinstance(item, str) and bool(item.strip()), f"{label}[{index}] must be nonempty text")
        result.append(item)
    _fail(len(result) == len(set(result)), f"{label} values must be unique")
    return result


def validate_mlinput(value: Any) -> None:
    """Validate the in-memory MLInput schema 1 payload used by the converter.

    Required mapping keys are ``schema_version``, ``X``, ``FeatureIDs``,
    ``Samples``, ``Targets``, ``Covariates``, ``FeatureDefinitions``,
    ``ValidMask``, ``MissingReasons``, and ``Provenance``.
    """
    _fail(isinstance(value, Mapping), "MLInput must be an object")
    _fail(value.get("schema_version") == MLINPUT_SCHEMA_VERSION, "Unsupported MLInput schema_version")
    feature_ids = _unique_text(value.get("FeatureIDs"), "FeatureIDs")
    matrix = _rows(value.get("X"), "X")
    samples = _sequence(value.get("Samples"), "Samples")
    _fail(len(matrix) == len(samples), "X row count must equal Samples count")
    _fail(matrix, "X must contain at least one sample")
    sample_ids: list[str] = []
    for index, sample in enumerate(samples):
        _fail(isinstance(sample, Mapping), f"Samples[{index}] must be an object")
        sample_ids.append(_text(sample.get("ObservationID"), f"Samples[{index}].ObservationID"))
    _fail(len(sample_ids) == len(set(sample_ids)), "Samples ObservationID values must be unique")
    for row_index, row in enumerate(matrix):
        _fail(len(row) == len(feature_ids), f"X[{row_index}] column count must equal FeatureIDs count")

    mask = _rows(value.get("ValidMask"), "ValidMask")
    reasons = _rows(value.get("MissingReasons"), "MissingReasons")
    _fail(len(mask) == len(matrix), "ValidMask row count must equal X row count")
    _fail(len(reasons) == len(matrix), "MissingReasons row count must equal X row count")
    for row_index, (x_row, mask_row, reason_row) in enumerate(zip(matrix, mask, reasons)):
        _fail(len(mask_row) == len(feature_ids), f"ValidMask[{row_index}] column count is wrong")
        _fail(len(reason_row) == len(feature_ids), f"MissingReasons[{row_index}] column count is wrong")
        for col_index, (number, is_valid, reason) in enumerate(zip(x_row, mask_row, reason_row)):
            label = f"X[{row_index}][{col_index}]"
            _fail(isinstance(is_valid, bool), f"ValidMask[{row_index}][{col_index}] must be boolean")
            _fail(isinstance(reason, str), f"MissingReasons[{row_index}][{col_index}] must be text")
            if is_valid:
                _fail(isinstance(number, (int, float)) and not isinstance(number, bool),
                      f"{label} must be numeric when marked valid")
                _fail(math.isfinite(float(number)), f"{label} must be finite when marked valid")
                _fail(not reason.strip(), f"{label} must have a blank MissingReason when valid")
            else:
                _fail(bool(reason.strip()), f"{label} has no MissingReason")
                is_nan = isinstance(number, float) and math.isnan(number)
                _fail(number is None or is_nan,
                      f"{label} must be NaN or null when invalid")

    for field in ("Targets", "Covariates"):
        mapping = value.get(field)
        _fail(isinstance(mapping, Mapping), f"{field} must map names to per-sample values")
        for name, values in mapping.items():
            _fail(isinstance(name, str) and bool(name.strip()), f"{field} contains an empty name")
            _fail(len(_sequence(values, f"{field}.{name}")) == len(samples),
                  f"{field}.{name} length must equal Samples count")

    definitions = _sequence(value.get("FeatureDefinitions"), "FeatureDefinitions")
    _fail(len(definitions) == len(feature_ids), "FeatureDefinitions count must equal FeatureIDs count")
    definition_ids: list[str] = []
    for index, definition in enumerate(definitions):
        _fail(isinstance(definition, Mapping), f"FeatureDefinitions[{index}] must be an object")
        definition_ids.append(_text(definition.get("FeatureID"), f"FeatureDefinitions[{index}].FeatureID"))
    _fail(definition_ids == feature_ids, "FeatureDefinitions order must match FeatureIDs order exactly")
    _fail(isinstance(value.get("Provenance"), Mapping), "Provenance must be an object")
