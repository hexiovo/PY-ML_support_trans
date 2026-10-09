"""Compare a MATLAB-generated synthetic export with its separate oracle."""
from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pyfnirs_converter.contracts import load_export_document


def scalar_text(value: Mapping[str, Any], label: str) -> str:
    current: Mapping[str, Any] = value
    while "elements" in current:
        elements = current["elements"]
        shape = current["shape"]
        count = 1
        for dimension in shape:
            count *= dimension
        if count != 1 or len(elements) != 1:
            raise ValueError(f"{label} is not scalar")
        current = elements[0]
    if "value" not in current:
        raise ValueError(f"{label} has no scalar value")
    return current["value"]


def table_rows(document: Mapping[str, Any], name: str) -> list[Mapping[str, Any]]:
    return document["tables"][name]["rows"]


def row_index(rows: list[Mapping[str, Any]], key: str, label: str) -> dict[str, Mapping[str, Any]]:
    indexed: dict[str, Mapping[str, Any]] = {}
    for index, row in enumerate(rows):
        value = scalar_text(row[key], f"{label}[{index}].{key}")
        if value in indexed:
            raise ValueError(f"Duplicate {key}: {value}")
        indexed[value] = row
    return indexed


def verify(export_path: Path, expected_path: Path) -> None:
    document, summary = load_export_document(export_path)
    expected = json.loads(expected_path.read_text(encoding="utf-8-sig"))
    if not expected.get("label", "").startswith("SYNTHETIC"):
        raise ValueError("Oracle is not explicitly marked synthetic")
    if document["source_file_name"] != expected["source_file_name"]:
        raise ValueError("MAT export source name differs from the oracle")
    if list(summary.observation_ids) != expected["observation_ids"]:
        raise ValueError("Observation table order or IDs differ from the oracle")
    if list(summary.feature_ids) != expected["feature_ids"]:
        raise ValueError("Feature definition order or IDs differ from the oracle")

    values = table_rows(document, "Values")
    by_key: dict[tuple[str, str], Mapping[str, Any]] = {}
    for row in values:
        key = (scalar_text(row["ObservationID"], "Values.ObservationID"),
               scalar_text(row["FeatureID"], "Values.FeatureID"))
        by_key[key] = row
    observed_matrix: list[list[str]] = []
    observed_validity: list[list[bool]] = []
    observed_reasons: list[list[str]] = []
    for sample_id in expected["sample_ids"]:
        value_row: list[str] = []
        valid_row: list[bool] = []
        reason_row: list[str] = []
        for feature_id in expected["feature_ids"]:
            row = by_key[(sample_id, feature_id)]
            value_row.append(scalar_text(row["Value"], "Values.Value"))
            valid_row.append(scalar_text(row["IsValid"], "Values.IsValid") == "true")
            reason_row.append(scalar_text(row["MissingReason"], "Values.MissingReason"))
        observed_matrix.append(value_row)
        observed_validity.append(valid_row)
        observed_reasons.append(reason_row)
    if observed_matrix != expected["matrix_value_text"]:
        raise ValueError(f"Matrix values differ: {observed_matrix!r}")
    if observed_validity != expected["valid_mask"]:
        raise ValueError(f"Validity mask differs: {observed_validity!r}")
    if observed_reasons != expected["missing_reasons"]:
        raise ValueError(f"Missing reasons differ: {observed_reasons!r}")

    observations = row_index(table_rows(document, "Observations"), "ObservationID", "Observations")
    target_values = [scalar_text(observations[sample_id]["Group"], "Observations.Group")
                     for sample_id in expected["sample_ids"]]
    if target_values != expected["targets"]:
        raise ValueError(f"Explicit Group labels differ: {target_values!r}")
    age_values = [scalar_text(observations[sample_id]["Cov_AgeYears"], "Observations.Cov_AgeYears")
                  for sample_id in expected["sample_ids"]]
    if age_values != expected["age_years_text"]:
        raise ValueError(f"Covariate values differ: {age_values!r}")

    pair_rows = table_rows(document, "PairLinks")
    if len(pair_rows) != 1:
        raise ValueError("Expected exactly one explicit synthetic PairLinks row")
    pair = pair_rows[0]
    for field, expected_key in (
        ("PairObservationID", "pair_observation_id"),
        ("PairID", "pair_id"),
        ("RoleA", "pair_role_a"),
        ("RoleB", "pair_role_b"),
    ):
        if scalar_text(pair[field], f"PairLinks.{field}") != expected[expected_key]:
            raise ValueError(f"PairLinks.{field} differs from the oracle")

    print(
        "PASS: MATLAB typed export matches independent synthetic oracle; "
        f"observations={len(summary.observation_ids)}, features={len(summary.feature_ids)}, "
        f"value_rows={summary.value_rows}, matrix_samples={len(expected['sample_ids'])}"
    )


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python tools/verify_pyfnirs_fixture.py <fixture-directory>", file=sys.stderr)
        return 2
    folder = Path(sys.argv[1]).resolve()
    try:
        verify(folder / "export" / "study_export.json", folder / "expected.json")
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
