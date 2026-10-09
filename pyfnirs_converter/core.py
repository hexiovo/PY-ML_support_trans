"""Core conversion of explicit PYfNIRs selections into PY-ML matrices."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from . import api, contracts, feature_adapters
from .matlab_bridge import (
    RAW_MAT_EXPORT_SCHEMA,
    RAW_RESULTS_ADAPTER_ID,
    STUDY_MAT_ADAPTER_ID,
    MatlabBridgeError,
    export_mat_document,
)


STUDY_EXPORT_ADAPTER_ID = "pyfnirs.study_export.v1"
_IDENTITY_FIELDS = (
    ("record_id_source_path", "RecordID"),
    ("subject_id_source_path", "SubjectID"),
    ("pair_observation_id_source_path", "PairObservationID"),
    ("pair_id_source_path", "PairID"),
    ("source_id_source_path", "MappedSourceID"),
)


class ConversionError(ValueError):
    """Raised when an explicit selection cannot produce an unambiguous matrix."""


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_document_hash(document: Mapping[str, Any]) -> str:
    try:
        payload = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ConversionError(f"Source document cannot be fingerprinted: {exc}") from exc
    return _sha256_bytes(payload.encode("utf-8"))


def file_sha256(path: str | Path) -> str:
    """Hash an input file without loading it all into memory."""
    digest = hashlib.sha256()
    try:
        with Path(path).open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
    except OSError as exc:
        raise ConversionError(f"Cannot read source file {path}: {exc}") from exc
    return digest.hexdigest()


def _is_study(document: Mapping[str, Any]) -> bool:
    return document.get("schema") == contracts.EXPORT_SCHEMA


def _adapter_for(document: Mapping[str, Any], path: Path, requested: str | None) -> str:
    schema = document.get("schema")
    if schema == RAW_MAT_EXPORT_SCHEMA:
        found = document.get("source_adapter_id")
        if found != RAW_RESULTS_ADAPTER_ID:
            raise ConversionError("Raw MAT source does not identify the supported Results adapter")
        if requested is not None and requested != found:
            raise ConversionError("Selected adapter does not match the raw MAT export")
        return str(found)
    if schema == contracts.EXPORT_SCHEMA:
        if requested is not None:
            if requested not in {STUDY_EXPORT_ADAPTER_ID, STUDY_MAT_ADAPTER_ID}:
                raise ConversionError("Selected adapter does not match the schema-1 Study export")
            return requested
        return STUDY_MAT_ADAPTER_ID if path.suffix.lower() == ".mat" else STUDY_EXPORT_ADAPTER_ID
    raise ConversionError(f"Unsupported source document schema: {schema!r}")


def load_source_document(
    path: str | Path,
    *,
    source_adapter_id: str | None = None,
    matlab_executable: str | Path | None = None,
    cancel_event=None,
) -> tuple[Mapping[str, Any], str]:
    """Load JSON interchange directly or ask the MATLAB bridge to export MAT."""
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise ConversionError(f"Source file does not exist: {source}")
    suffix = source.suffix.lower()
    if suffix == ".json":
        try:
            document = json.loads(source.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ConversionError(f"Cannot read source JSON {source}: {exc}") from exc
        if not isinstance(document, Mapping):
            raise ConversionError("Source JSON root must be an object")
    elif suffix == ".mat":
        requested = source_adapter_id
        if requested == STUDY_EXPORT_ADAPTER_ID:
            raise ConversionError("pyfnirs.study_export.v1 applies to JSON exports; select the Study MAT adapter for .mat")
        try:
            document = export_mat_document(
                source,
                matlab_executable=matlab_executable,
                source_adapter_id=requested,
                cancel_event=cancel_event,
            )
        except MatlabBridgeError as exc:
            raise ConversionError(str(exc)) from exc
    else:
        raise ConversionError("Only .mat and validated .json source files are supported")
    adapter_id = _adapter_for(document, source, source_adapter_id)
    return document, adapter_id


def _typed_scalar(node: Any, label: str) -> Any:
    if not isinstance(node, Mapping) or not isinstance(node.get("matlab_class"), str):
        raise ConversionError(f"{label} is not a typed MATLAB scalar")
    shape = node.get("shape")
    if (
        not isinstance(shape, Sequence)
        or isinstance(shape, (str, bytes))
        or any(not isinstance(size, int) or isinstance(size, bool) or size < 0 for size in shape)
    ):
        raise ConversionError(f"{label} has an invalid MATLAB shape")
    if math.prod(shape) != 1 or "elements" in node or "fields" in node or "table" in node:
        raise ConversionError(f"{label} must be a scalar MATLAB value")
    if node.get("is_missing") is True:
        return None
    raw = node.get("value")
    if not isinstance(raw, str):
        raise ConversionError(f"{label} has no scalar text value")
    matlab_class = node["matlab_class"]
    if matlab_class in {"char", "string", "categorical", "datetime", "duration"}:
        return raw
    if matlab_class == "logical":
        if raw not in {"true", "false"}:
            raise ConversionError(f"{label} has an invalid MATLAB logical value")
        return raw == "true"
    if matlab_class in {"double", "single"}:
        if raw == "NaN":
            return math.nan
        if raw == "Inf":
            return math.inf
        if raw == "-Inf":
            return -math.inf
        try:
            return float(raw)
        except ValueError as exc:
            raise ConversionError(f"{label} has invalid numeric text") from exc
    if matlab_class.startswith(("int", "uint")):
        try:
            return int(raw)
        except ValueError as exc:
            raise ConversionError(f"{label} has invalid integer text") from exc
    raise ConversionError(f"{label} uses unsupported MATLAB class {matlab_class!r}")


def _study_path(path: str) -> tuple[str, str]:
    if not isinstance(path, str) or not path.strip():
        raise ConversionError("Source mapping path must be nonempty")
    parts = path.split(".")
    if parts[0] == "study":
        parts = parts[1:]
    if len(parts) != 2 or not all(parts):
        raise ConversionError(f"Study mapping must name one table column: {path!r}")
    return parts[0], parts[1]


def _study_table(document: Mapping[str, Any], name: str) -> tuple[Mapping[str, Any], ...]:
    tables = document.get("tables")
    if not isinstance(tables, Mapping) or name not in tables:
        raise ConversionError(f"Study table does not exist: {name}")
    table = tables[name]
    if not isinstance(table, Mapping) or not isinstance(table.get("rows"), Sequence):
        raise ConversionError(f"Study table {name} is malformed")
    rows = table["rows"]
    if any(not isinstance(row, Mapping) for row in rows):
        raise ConversionError(f"Study table {name} contains a malformed row")
    return tuple(rows)


def _study_values(document: Mapping[str, Any], path: str) -> tuple[str, tuple[Any, ...]]:
    table_name, column_name = _study_path(path)
    rows = _study_table(document, table_name)
    values: list[Any] = []
    for index, row in enumerate(rows):
        if column_name not in row:
            raise ConversionError(f"Study mapping column does not exist: {path}")
        values.append(_typed_scalar(row[column_name], f"{path}[{index}]") )
    return table_name, tuple(values)


def _resolve_values(document: Mapping[str, Any], adapter_id: str, path: str) -> tuple[Any, ...]:
    if _is_study(document):
        return _study_values(document, path)[1]
    try:
        return feature_adapters.resolve_raw_source_path(document, path)
    except feature_adapters.AdapterError as exc:
        raise ConversionError(str(exc)) from exc


def _typed_text(value: str) -> Mapping[str, Any]:
    return {"matlab_class": "string", "shape": [1, 1], "value": value, "is_missing": False}


def _validate_selection(selection: api.ConversionSelection) -> None:
    if not isinstance(selection, api.ConversionSelection):
        raise ConversionError("Selection must be a ConversionSelection")
    if not selection.source_adapter_id:
        raise ConversionError("Select a source adapter explicitly")
    if not selection.identity.observation_id_source_path:
        raise ConversionError("Select an explicit ObservationID source path")
    if not selection.feature_selections:
        raise ConversionError("Select at least one feature")
    if selection.output_format not in {"csv", "xlsx"}:
        raise ConversionError(f"Unsupported output format: {selection.output_format!r}")
    if selection.merge_mode not in {"per_file", "merge"}:
        raise ConversionError(f"Unsupported merge mode: {selection.merge_mode!r}")
    if selection.collision_policy not in {"skip", "rename"}:
        raise ConversionError(f"Unsupported collision policy: {selection.collision_policy!r}")

    feature_ids: set[str] = set()
    for feature in selection.feature_selections:
        if not isinstance(feature.feature_id, str) or not feature.feature_id.strip():
            raise ConversionError("Every selected feature needs an explicit FeatureID")
        if feature.feature_id in feature_ids:
            raise ConversionError(f"Selected FeatureID is duplicated: {feature.feature_id}")
        feature_ids.add(feature.feature_id)
    names = [mapping.output_name for mapping in (*selection.targets, *selection.covariates)]
    if any(not isinstance(name, str) or not name.strip() for name in names):
        raise ConversionError("Every target/covariate needs a nonempty output name")
    if len(names) != len(set(names)):
        raise ConversionError("Target and covariate output names must be unique")
    reserved = {"ObservationID", *feature_ids}
    collisions = reserved.intersection(names)
    if collisions:
        raise ConversionError(f"Output names collide with reserved matrix columns: {', '.join(sorted(collisions))}")
    if any(mapping.role != "target" for mapping in selection.targets):
        raise ConversionError("Targets must use role='target'")
    if any(mapping.role != "covariate" for mapping in selection.covariates):
        raise ConversionError("Covariates must use role='covariate'")


def _selected_rows(
    document: Mapping[str, Any], selection: api.ConversionSelection
) -> tuple[tuple[Mapping[str, Any], ...], tuple[Mapping[str, Any], ...]]:
    try:
        return feature_adapters.select_feature_rows(document, selection)
    except (feature_adapters.AdapterError, contracts.ContractError) as exc:
        raise ConversionError(str(exc)) from exc


def _ordered_observation_ids(
    document: Mapping[str, Any],
    selection: api.ConversionSelection,
    rows: Sequence[Mapping[str, Any]],
) -> tuple[str, ...]:
    by_feature: dict[str, list[str]] = {item.feature_id: [] for item in selection.feature_selections}
    seen: set[tuple[str, str]] = set()
    for index, row in enumerate(rows):
        observation_id = row.get("ObservationID")
        feature_id = row.get("FeatureID")
        if not isinstance(observation_id, str) or not observation_id.strip():
            raise ConversionError(f"Selected value row {index} has no explicit ObservationID")
        if feature_id not in by_feature:
            raise ConversionError(f"Selected value row {index} has an unselected FeatureID")
        key = (observation_id, str(feature_id))
        if key in seen:
            raise ConversionError(f"Duplicate selected (ObservationID, FeatureID) key: {key}")
        seen.add(key)
        by_feature[str(feature_id)].append(observation_id)
    feature_sets = [set(values) for values in by_feature.values()]
    if any(not values for values in by_feature.values()):
        raise ConversionError("Every selected feature must have at least one value row")
    baseline = feature_sets[0]
    if any(values != baseline for values in feature_sets[1:]):
        raise ConversionError("Selected features cover different ObservationID sets; refusing an implicit intersection or fill")

    if _is_study(document):
        table_name, values = _study_values(document, selection.identity.observation_id_source_path)
        if table_name != "Observations":
            raise ConversionError("Schema-1 Study ObservationID mapping must come from Observations")
        ordered_all = [value for value in values if isinstance(value, str) and value]
        if len(ordered_all) != len(set(ordered_all)):
            raise ConversionError("Study ObservationID mapping contains duplicates")
        if not baseline.issubset(set(ordered_all)):
            missing = sorted(baseline.difference(ordered_all))
            raise ConversionError(f"Selected value rows reference unknown ObservationID values: {missing}")
        return tuple(value for value in ordered_all if value in baseline)

    order: list[str] = []
    for row in rows:
        observation_id = str(row["ObservationID"])
        if observation_id in baseline and observation_id not in order:
            order.append(observation_id)
    return tuple(order)


def _identity_path_map(identity: api.IdentityMapping) -> tuple[tuple[str, str], ...]:
    result = [("ObservationID", identity.observation_id_source_path)]
    result.extend(
        (output_name, path)
        for attribute, output_name in _IDENTITY_FIELDS
        if (path := getattr(identity, attribute)) is not None
    )
    return tuple(result)


def _study_keyed_values(
    document: Mapping[str, Any],
    table_name: str,
    column_name: str,
) -> tuple[dict[str, Any], tuple[str, ...]]:
    rows = _study_table(document, table_name)
    key_column = {"Observations": "ObservationID", "PairLinks": "PairObservationID", "Sources": "SourceID"}.get(table_name)
    if key_column is None:
        raise ConversionError(f"Study table {table_name} has no supported sample join key")
    keyed: dict[str, Any] = {}
    order: list[str] = []
    for index, row in enumerate(rows):
        if key_column not in row or column_name not in row:
            raise ConversionError(f"Study table path {table_name}.{column_name} or join key {key_column} is missing")
        key = _typed_scalar(row[key_column], f"{table_name}[{index}].{key_column}")
        if not isinstance(key, str) or not key:
            raise ConversionError(f"{table_name}[{index}].{key_column} must be nonempty text")
        if key in keyed:
            raise ConversionError(f"{table_name}.{key_column} contains duplicate {key!r}")
        keyed[key] = _typed_scalar(row[column_name], f"{table_name}[{index}].{column_name}")
        order.append(key)
    return keyed, tuple(order)


def _sample_join_key(
    table_name: str,
    sample_id: str,
    study_observation: Mapping[str, Any] | None,
    selected_identity: Mapping[str, Any],
) -> str:
    if table_name == "Observations":
        return sample_id
    if table_name == "PairLinks":
        pair_observation_id = selected_identity.get("PairObservationID")
        if not pair_observation_id and study_observation is not None:
            pair_observation_id = _typed_scalar(study_observation.get("PairObservationID"), "Observations.PairObservationID")
        if not isinstance(pair_observation_id, str) or not pair_observation_id:
            raise ConversionError(f"ObservationID {sample_id} has no explicit PairObservationID for PairLinks join")
        return pair_observation_id
    if table_name == "Sources":
        source_id = selected_identity.get("MappedSourceID")
        if not source_id and study_observation is not None:
            source_id = _typed_scalar(study_observation.get("SourceID"), "Observations.SourceID")
        if not isinstance(source_id, str) or not source_id:
            raise ConversionError(f"ObservationID {sample_id} has no explicit SourceID for Sources join")
        return source_id
    raise ConversionError(f"Study table {table_name} has no supported sample join key")


def _resolve_study_mapping(
    document: Mapping[str, Any],
    path: str,
    sample_ids: Sequence[str],
    observation_rows_by_id: Mapping[str, Mapping[str, Any]],
    selected_identities: Mapping[str, Mapping[str, Any]],
) -> list[Any]:
    table_name, column_name = _study_path(path)
    keyed, _ = _study_keyed_values(document, table_name, column_name)
    values: list[Any] = []
    for sample_id in sample_ids:
        key = _sample_join_key(
            table_name,
            sample_id,
            observation_rows_by_id.get(sample_id),
            selected_identities[sample_id],
        )
        if key not in keyed:
            raise ConversionError(f"{path} has no row for selected ObservationID {sample_id}")
        values.append(keyed[key])
    return values


def _raw_sibling_key_values(
    document: Mapping[str, Any], path: str, key_path: str
) -> tuple[Any, ...] | None:
    if path.rsplit(".", 1)[0] != key_path.rsplit(".", 1)[0]:
        return None
    try:
        return feature_adapters.resolve_raw_source_path(document, key_path)
    except feature_adapters.AdapterError:
        return None


def _resolve_raw_mapping(
    document: Mapping[str, Any],
    path: str,
    sample_ids: Sequence[str],
    selection: api.ConversionSelection,
    identities_by_sample: Mapping[str, Mapping[str, Any]],
) -> list[Any]:
    try:
        values = feature_adapters.resolve_raw_source_path(document, path)
    except feature_adapters.AdapterError as exc:
        raise ConversionError(str(exc)) from exc
    if len(values) == 1:
        return [values[0]] * len(sample_ids)
    if len(values) == len(sample_ids) and len(sample_ids) > 1:
        # Only align by the same explicitly selected identity column; never
        # assume unrelated MATLAB arrays share an axis order.
        for alias, key_path in _identity_path_map(selection.identity):
            keys = _raw_sibling_key_values(document, path, key_path)
            if keys is None or len(keys) != len(values):
                continue
            if any(key is None or key == "" for key in keys) or len(set(keys)) != len(keys):
                continue
            keyed = dict(zip(keys, values))
            expected = [identities_by_sample[sample_id].get(alias, sample_id if alias == "ObservationID" else None)
                        for sample_id in sample_ids]
            if all(value in keyed for value in expected):
                return [keyed[value] for value in expected]
    # A one-sample file can still select a row from a table when one of the
    # user's identity mappings points to a sibling key column.
    if len(sample_ids) == 1:
        sample_id = sample_ids[0]
        for alias, key_path in _identity_path_map(selection.identity):
            keys = _raw_sibling_key_values(document, path, key_path)
            expected = identities_by_sample[sample_id].get(alias, sample_id if alias == "ObservationID" else None)
            if keys is None or len(keys) != len(values) or expected is None:
                continue
            matches = [index for index, key in enumerate(keys) if key == expected]
            if len(matches) == 1:
                return [values[matches[0]]]
    raise ConversionError(
        f"Cannot align {path!r} to selected ObservationIDs using an explicitly mapped identity field"
    )


def _build_identity_values(
    document: Mapping[str, Any],
    selection: api.ConversionSelection,
    sample_ids: Sequence[str],
) -> tuple[dict[str, dict[str, Any]], dict[str, Mapping[str, Any]]]:
    values_by_sample: dict[str, dict[str, Any]] = {sample_id: {"ObservationID": sample_id} for sample_id in sample_ids}
    observations_by_id: dict[str, Mapping[str, Any]] = {}

    if _is_study(document):
        rows = _study_table(document, "Observations")
        for index, row in enumerate(rows):
            observation_id = _typed_scalar(row.get("ObservationID"), f"Observations[{index}].ObservationID")
            if not isinstance(observation_id, str) or not observation_id:
                raise ConversionError(f"Observations[{index}].ObservationID must be nonempty text")
            if observation_id in observations_by_id:
                raise ConversionError(f"Study has duplicate ObservationID {observation_id!r}")
            observations_by_id[observation_id] = row
        path_table, path_values = _study_values(document, selection.identity.observation_id_source_path)
        if path_table != "Observations" or tuple(path_values) != tuple(
            _typed_scalar(row.get("ObservationID"), "Observations.ObservationID") for row in rows
        ):
            raise ConversionError("ObservationID mapping must explicitly resolve Observations.ObservationID in table order")
        for sample_id in sample_ids:
            if sample_id not in observations_by_id:
                raise ConversionError(f"Selected values reference unknown ObservationID {sample_id!r}")
    else:
        identity_path = selection.identity.observation_id_source_path
        raw_ids = _resolve_values(document, selection.source_adapter_id, identity_path)
        nonmissing = [value for value in raw_ids if isinstance(value, str) and value.strip()]
        if len(nonmissing) != len(set(nonmissing)):
            raise ConversionError("ObservationID mapping contains duplicate values")
        if not set(sample_ids).issubset(set(nonmissing)):
            raise ConversionError("Selected feature rows do not resolve through the explicit ObservationID mapping")

    for output_name, path in _identity_path_map(selection.identity):
        if output_name == "ObservationID":
            continue
        if _is_study(document):
            aligned = _resolve_study_mapping(document, path, sample_ids, observations_by_id, values_by_sample)
        else:
            aligned = _resolve_raw_mapping(document, path, sample_ids, selection, values_by_sample)
        for sample_id, value in zip(sample_ids, aligned):
            values_by_sample[sample_id][output_name] = value
    return values_by_sample, observations_by_id


def _resolve_field_mapping(
    document: Mapping[str, Any],
    selection: api.ConversionSelection,
    path: str,
    sample_ids: Sequence[str],
    identities_by_sample: Mapping[str, Mapping[str, Any]],
    observation_rows_by_id: Mapping[str, Mapping[str, Any]],
) -> list[Any]:
    if _is_study(document):
        return _resolve_study_mapping(document, path, sample_ids, observation_rows_by_id, identities_by_sample)
    return _resolve_raw_mapping(document, path, sample_ids, selection, identities_by_sample)


def _definition_feature_id(definition: Mapping[str, Any]) -> str | None:
    value = definition.get("FeatureID")
    if isinstance(value, Mapping):
        try:
            value = _typed_scalar(value, "FeatureDefinitions.FeatureID")
        except ConversionError:
            return None
    return value if isinstance(value, str) else None


def _convert_document(
    document: Mapping[str, Any],
    selection: api.ConversionSelection,
    *,
    adapter_id: str,
    source_fingerprint: str,
    source_path: Path | None,
) -> dict[str, Any]:
    _validate_selection(selection)
    if selection.source_adapter_id != adapter_id:
        raise ConversionError("Selection source adapter does not match the inspected source")
    rows, definitions = _selected_rows(document, selection)
    feature_ids = [feature.feature_id for feature in selection.feature_selections]
    if len(definitions) != len(feature_ids):
        raise ConversionError("Selected feature definitions do not match the requested FeatureIDs")
    for expected_id, definition in zip(feature_ids, definitions):
        if _definition_feature_id(definition) != expected_id:
            raise ConversionError(f"Feature definition does not preserve selected FeatureID {expected_id!r}")

    sample_ids = _ordered_observation_ids(document, selection, rows)
    row_by_key: dict[tuple[str, str], Mapping[str, Any]] = {}
    for row in rows:
        key = (str(row["ObservationID"]), str(row["FeatureID"]))
        row_by_key[key] = row
    for sample_id in sample_ids:
        for feature_id in feature_ids:
            if (sample_id, feature_id) not in row_by_key:
                raise ConversionError(f"Missing explicit value row for ({sample_id}, {feature_id}); refusing to fill")

    identity_values, observation_rows = _build_identity_values(document, selection, sample_ids)
    matrices: list[list[float]] = []
    valid_mask: list[list[bool]] = []
    missing_reasons: list[list[str]] = []
    value_source_ids: list[dict[str, Any]] = []
    for sample_id in sample_ids:
        x_row: list[float] = []
        mask_row: list[bool] = []
        reason_row: list[str] = []
        source_by_feature: dict[str, Any] = {}
        for feature_id in feature_ids:
            value_row = row_by_key[(sample_id, feature_id)]
            valid = value_row.get("IsValid") is True
            value = value_row.get("Value")
            reason = value_row.get("MissingReason", "")
            if not isinstance(reason, str):
                raise ConversionError(f"MissingReason for ({sample_id}, {feature_id}) is not text")
            if valid:
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                    raise ConversionError(f"Value for ({sample_id}, {feature_id}) is not finite")
                if reason:
                    raise ConversionError(f"Valid value ({sample_id}, {feature_id}) has a MissingReason")
                x_row.append(float(value))
                mask_row.append(True)
                reason_row.append("")
            else:
                if not (isinstance(value, float) and math.isnan(value)) or not reason.strip():
                    raise ConversionError(f"Invalid value ({sample_id}, {feature_id}) lacks its NaN and reason")
                x_row.append(math.nan)
                mask_row.append(False)
                reason_row.append(reason)
            source_by_feature[feature_id] = value_row.get("SourceID")
        matrices.append(x_row)
        valid_mask.append(mask_row)
        missing_reasons.append(reason_row)
        value_source_ids.append(source_by_feature)

    targets = {
        mapping.output_name: _resolve_field_mapping(
            document, selection, mapping.source_path, sample_ids, identity_values, observation_rows
        )
        for mapping in selection.targets
    }
    covariates = {
        mapping.output_name: _resolve_field_mapping(
            document, selection, mapping.source_path, sample_ids, identity_values, observation_rows
        )
        for mapping in selection.covariates
    }

    samples: list[dict[str, Any]] = []
    for sample_id, identities, original_source_ids in zip(sample_ids, identity_values.values(), value_source_ids):
        sample = {"ObservationID": _typed_text(sample_id), "SourceID": f"sha256:{source_fingerprint}"}
        for key, value in identities.items():
            if key != "ObservationID":
                sample[key] = value
        sample["ValueSourceIDs"] = original_source_ids
        samples.append(sample)

    normalized_definitions: list[dict[str, Any]] = []
    for feature_id, definition in zip(feature_ids, definitions):
        normalized = dict(definition)
        normalized["FeatureID"] = _typed_text(feature_id)
        normalized_definitions.append(normalized)

    provenance: dict[str, Any] = {
        "source_file_name": (
            str(document.get("source_file_name"))
            if isinstance(document.get("source_file_name"), str)
            else (source_path.name if source_path is not None else "")
        ),
        "source_file_path": str(source_path) if source_path is not None else None,
        "source_fingerprint_sha256": source_fingerprint,
        "source_adapter_id": adapter_id,
        "source_schema": document.get("schema"),
        "identity_mapping": {
            "observation_id": selection.identity.observation_id_source_path,
            **{name: getattr(selection.identity, attribute) for attribute, name in _IDENTITY_FIELDS},
        },
        "target_mappings": [
            {"source_path": item.source_path, "output_name": item.output_name} for item in selection.targets
        ],
        "covariate_mappings": [
            {"source_path": item.source_path, "output_name": item.output_name} for item in selection.covariates
        ],
        "selected_feature_ids": feature_ids,
        "valid_mask": valid_mask,
        "missing_reasons": missing_reasons,
        "value_source_ids": value_source_ids,
        "synthetic_fixture_notice": document.get("study_metadata", {}).get("FixtureNotice")
        if isinstance(document.get("study_metadata"), Mapping)
        else None,
    }
    mlinput: dict[str, Any] = {
        "schema_version": contracts.MLINPUT_SCHEMA_VERSION,
        "X": matrices,
        "FeatureIDs": feature_ids,
        "Samples": samples,
        "Targets": targets,
        "Covariates": covariates,
        "FeatureDefinitions": normalized_definitions,
        "ValidMask": valid_mask,
        "MissingReasons": missing_reasons,
        "Provenance": provenance,
    }
    try:
        contracts.validate_mlinput(mlinput)
    except contracts.ContractError as exc:
        raise ConversionError(f"Converted MLInput violates schema 1: {exc}") from exc
    return mlinput


def convert_export(
    document: Mapping[str, Any], selection: api.ConversionSelection
) -> api.MLInput:
    """Convert a validated study or raw Results export into MLInput."""
    if not isinstance(document, Mapping):
        raise ConversionError("Source document must be an object")
    _validate_selection(selection)
    try:
        adapter_id = _adapter_for(document, Path(str(document.get("source_file_name", "source.json"))), selection.source_adapter_id)
    except ConversionError:
        raise
    return _convert_document(
        document,
        selection,
        adapter_id=adapter_id,
        source_fingerprint=_canonical_document_hash(document),
        source_path=None,
    )


def inspect_source(
    path: Path,
    *,
    source_adapter_id: str | None = None,
    matlab_executable: Path | None = None,
) -> api.SourceInspection:
    source = Path(path).expanduser().resolve()
    document, adapter_id = load_source_document(
        source, source_adapter_id=source_adapter_id, matlab_executable=matlab_executable
    )
    try:
        return feature_adapters.inspect_document(document, source, adapter_id)
    except (feature_adapters.AdapterError, contracts.ContractError) as exc:
        raise ConversionError(str(exc)) from exc


def preview_conversion(
    path: Path,
    selection: api.ConversionSelection,
    *,
    matlab_executable: Path | None = None,
) -> api.ConversionPreview:
    _validate_selection(selection)
    source = Path(path).expanduser().resolve()
    document, adapter_id = load_source_document(
        source, source_adapter_id=selection.source_adapter_id, matlab_executable=matlab_executable
    )
    payload = _convert_document(
        document,
        selection,
        adapter_id=adapter_id,
        source_fingerprint=file_sha256(source),
        source_path=source,
    )
    output_columns = (
        "ObservationID",
        *(mapping.output_name for mapping in selection.targets),
        *(mapping.output_name for mapping in selection.covariates),
        *payload["FeatureIDs"],
    )
    warnings: list[str] = []
    if _is_study(document):
        all_ids = _study_values(document, selection.identity.observation_id_source_path)[1]
        selected = set(sample["ObservationID"]["value"] for sample in payload["Samples"])
        omitted = [value for value in all_ids if isinstance(value, str) and value not in selected]
        if omitted:
            warnings.append(
                f"Excluded {len(omitted)} Study observations with no selected feature rows; this does not fill or intersect feature data."
            )
    return api.ConversionPreview(
        sample_count=len(payload["Samples"]),
        selected_feature_ids=tuple(payload["FeatureIDs"]),
        output_columns=tuple(output_columns),
        targets=selection.targets,
        covariates=selection.covariates,
        missing_count=sum(not value for row in payload["ValidMask"] for value in row),
        rejected_features=(),
        merge_conflicts=(),
        warnings=tuple(warnings),
    )


__all__ = [
    "ConversionError",
    "convert_export",
    "file_sha256",
    "inspect_source",
    "load_source_document",
    "preview_conversion",
]
