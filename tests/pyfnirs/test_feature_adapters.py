"""Discriminating tests for normalized study transfer and raw Results adapters."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from pyfnirs_converter import api
from pyfnirs_converter import feature_adapters as adapters


_RAW_FIXTURE_PATH = os.environ.get("PYFNIRS_RAW_RESULTS_FIXTURE")
RAW_FIXTURE = Path(_RAW_FIXTURE_PATH).expanduser().resolve() if _RAW_FIXTURE_PATH else None
HAS_RAW_FIXTURE = RAW_FIXTURE is not None and all(
    (RAW_FIXTURE / name).is_file()
    for name in ("raw_results_synthetic.json", "expected.json", "raw_results_synthetic.mat")
)
RAW_FIXTURE_SKIP_REASON = (
    "Set PYFNIRS_RAW_RESULTS_FIXTURE to the generated raw Results fixture directory "
    "containing its JSON, independent expected.json, and MATLAB .mat file."
)


def _typed(matlab_class: str, value: str, shape: tuple[int, ...] = (1, 1)) -> dict[str, object]:
    return {
        "matlab_class": matlab_class,
        "shape": list(shape),
        "value": value,
        "is_missing": False,
    }


def _numeric_array(values: list[float], shape: tuple[int, ...]) -> dict[str, object]:
    return {
        "matlab_class": "double",
        "shape": list(shape),
        "elements": [_typed("double", str(value)) for value in values],
    }


def _struct(fields: dict[str, object]) -> dict[str, object]:
    return {"matlab_class": "struct", "shape": [1, 1], "fields": fields}


def _cell(elements: list[object], shape: tuple[int, ...]) -> dict[str, object]:
    return {"matlab_class": "cell", "shape": list(shape), "elements": elements}


def _raw_document() -> dict[str, object]:
    """Build a compact typed tree for negative shape tests only.

    Positive scientific selection tests load the independently exported
    MATLAB fixture named by ``PYFNIRS_RAW_RESULTS_FIXTURE``.
    """
    return {
        "schema": adapters.RAW_MAT_SCHEMA,
        "source_adapter_id": adapters.RAW_RESULTS_ADAPTER_ID,
        "variables": {
            "Results": _struct({
                "Kind": _typed("char", "PYfNIRs.Results", (1, 15)),
                "RecordID": _typed("char", "REC-UNRELATED", (1, 13)),
                "data": _struct({"all": _struct({"HbO": _numeric_array([1, 2, 2, 1], (2, 2))})}),
            })
        },
    }


def _load_raw_fixture() -> dict[str, object]:
    if not HAS_RAW_FIXTURE or RAW_FIXTURE is None:
        raise RuntimeError(RAW_FIXTURE_SKIP_REASON)
    return json.loads((RAW_FIXTURE / "raw_results_synthetic.json").read_text(encoding="utf-8"))


def _base_study_export() -> dict[str, object]:
    def scalar(cls: str, value: str) -> dict[str, object]:
        return _typed(cls, value)

    def table(columns: list[tuple[str, str]], rows: list[dict[str, object]]) -> dict[str, object]:
        return {
            "row_count": len(rows),
            "columns": [{"name": name, "matlab_class": cls, "units": "", "description": ""} for name, cls in columns],
            "rows": rows,
            "row_names": [],
        }

    source_columns = [
        ("SourceID", "string"), ("Kind", "string"), ("SchemaVersion", "double"),
        ("FilePath", "string"), ("PayloadPath", "string"), ("Fingerprint", "string"),
        ("Adapter", "string"), ("Capability", "string"),
    ]
    source = {name: scalar(cls, value) for (name, cls), value in zip(source_columns, (
        "SRC-SYN", "synthetic_fixture", "1", "SYNTHETIC://record.mat", "values", "SYNTHETIC", "fixture", "direct"
    ))}

    observation_columns = [
        ("ObservationID", "string"), ("RecordID", "string"), ("SubjectID", "string"),
        ("PairObservationID", "string"), ("Group", "string"), ("Condition", "string"),
        ("Session", "string"), ("Timepoint", "string"), ("Include", "logical"),
        ("SourceID", "string"), ("Cov_AgeYears", "double"),
    ]
    observation_rows = []
    for values in (
        ("OBS-42", "REC-42", "SUB-42", "", "control", "baseline", "S1", "T0", "true", "SRC-SYN", "31"),
        ("OBS-8", "REC-8", "SUB-8", "", "case", "followup", "S2", "T1", "true", "SRC-SYN", "45"),
    ):
        observation_rows.append({name: scalar(cls, value) for (name, cls), value in zip(observation_columns, values)})

    feature_columns = [
        ("FeatureID", "string"), ("Metric", "string"), ("Level", "string"),
        ("Hemoglobin", "string"), ("NodeA", "string"), ("NodeB", "string"),
        ("RoleA", "string"), ("RoleB", "string"), ("FrequencyLowHz", "double"),
        ("FrequencyHighHz", "double"), ("WindowStartSeconds", "double"),
        ("WindowEndSeconds", "double"), ("Scale", "double"), ("Unit", "string"),
        ("Transform", "string"), ("Direction", "string"), ("Dimension", "string"),
        ("ParameterFingerprint", "string"), ("MappingFingerprint", "string"),
    ]
    feature_rows = []
    for feature_id, hb, parameter in (("F-O2", "HbO", "SYNTHETIC-PARAM-A"), ("F-HbR", "HbR", "SYNTHETIC-PARAM-B")):
        values = (feature_id, "synthetic_mean", "CH", hb, "N1", "", "", "", "NaN", "NaN", "NaN", "NaN", "1", "a.u.", "none", "scalar", "scalar", parameter, "SYNTHETIC-MAP")
        feature_rows.append({name: scalar(cls, value) for (name, cls), value in zip(feature_columns, values)})

    value_columns = [("ObservationID", "string"), ("FeatureID", "string"), ("Value", "double"), ("IsValid", "logical"), ("MissingReason", "string"), ("SourceID", "string")]
    value_rows = []
    for observation_id, feature_id, number, valid, reason in (
        ("OBS-8", "F-HbR", "NaN", "false", "qc_rejected"),
        ("OBS-42", "F-O2", "1.25", "true", ""),
        ("OBS-8", "F-O2", "2.5", "true", ""),
        ("OBS-42", "F-HbR", "3.75", "true", ""),
    ):
        values = (observation_id, feature_id, number, valid, reason, "SRC-SYN")
        value_rows.append({name: scalar(cls, value) for (name, cls), value in zip(value_columns, values)})

    pair_columns = [("PairObservationID", "string"), ("PairID", "string"), ("RecordIDA", "string"), ("RecordIDB", "string"), ("SubjectIDA", "string"), ("SubjectIDB", "string"), ("RoleA", "string"), ("RoleB", "string"), ("Condition", "string"), ("Session", "string"), ("Timepoint", "string")]
    covariate_columns = [("ColumnName", "string"), ("Level", "string"), ("Origin", "string"), ("DataKey", "string")]
    covariate = {name: scalar(cls, value) for (name, cls), value in zip(covariate_columns, ("Cov_AgeYears", "subject", "synthetic_fixture", "SubjectID"))}
    return {
        "schema": "pyfnirs.matlab-export/1",
        "study_kind": "PYfNIRsDA.Study",
        "study_schema_version": 1,
        "source_file_name": "study_synthetic.mat",
        "matlab_version": "synthetic-test",
        "study_metadata": {},
        "tables": {
            "Sources": table(source_columns, [source]),
            "Observations": table(observation_columns, observation_rows),
            "PairLinks": table(pair_columns, []),
            "FeatureDefinitions": table(feature_columns, feature_rows),
            "Values": table(value_columns, value_rows),
            "CovariateMetadata": table(covariate_columns, [covariate]),
        },
    }


def _study_selection(feature_id: str, **changes: object) -> api.ConversionSelection:
    feature_values: dict[str, object] = dict(
        capability_id=adapters.STUDY_DEFINED_CAPABILITY_ID,
        feature_id=feature_id,
        source_path="study.Values",
        axis_selection={},
        summary_parameters={},
    )
    feature_values.update(changes)
    feature = api.FeatureSelection(**feature_values)
    return api.ConversionSelection(
        source_adapter_id=adapters.STUDY_EXPORT_ADAPTER_ID,
        identity=api.IdentityMapping("study.Observations.ObservationID"),
        feature_selections=(feature,),
        targets=(),
        covariates=(),
        output_format="csv",
        merge_mode="per_file",
        collision_policy="skip",
    )


def _raw_selection() -> api.ConversionSelection:
    features = (
        api.FeatureSelection(
            capability_id="24",
            feature_id="PH-HBO-H0-PERSISTENCE",
            source_path="Results.data.PersistentHomology",
            axis_selection={"hemoglobin": "HbO", "input_semantics": "positive_similarity", "summary": "H0:TotalPersistence"},
            summary_parameters={},
        ),
        api.FeatureSelection(
            capability_id="07",
            feature_id="FC-HBO-ROI-A-ROI-B",
            source_path="Results.data.all",
            axis_selection={"algorithm": "Pearson", "hemoglobin": "HbO", "node_a": "ROI-A", "node_b": "ROI-B"},
            summary_parameters={},
        ),
        api.FeatureSelection(
            capability_id="14",
            feature_id="MVAR-HBO-ROI-A-TO-ROI-B",
            source_path="Results.data.WithinBrainMVARGranger",
            axis_selection={"formula": "conditional_log_residual_variance_ratio_v1", "hemoglobin": "HbO", "source_node": "ROI-A", "target_node": "ROI-B"},
            summary_parameters={},
        ),
        api.FeatureSelection(
            capability_id="24",
            feature_id="PH-HBR-H1-PERSISTENCE-MISSING",
            source_path="Results.data.PersistentHomology",
            axis_selection={"hemoglobin": "HbR", "input_semantics": "positive_similarity", "summary": "H1:TotalPersistence"},
            summary_parameters={},
        ),
    )
    return api.ConversionSelection(
        source_adapter_id=adapters.RAW_RESULTS_ADAPTER_ID,
        identity=api.IdentityMapping("Results.ObservationID"),
        feature_selections=features,
        targets=(),
        covariates=(),
        output_format="csv",
        merge_mode="per_file",
        collision_policy="skip",
    )


class StudyDefinedAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = _base_study_export()

    def test_inspection_exposes_only_explicit_table_defined_candidates(self) -> None:
        inspected = adapters.inspect_document(self.document, Path("synthetic.json"), adapters.STUDY_EXPORT_ADAPTER_ID)
        self.assertEqual(inspected.source_format, "pyfnirs_study_export")
        self.assertEqual([candidate.capability_id for candidate in inspected.feature_candidates], ["study-defined", "study-defined"])
        self.assertEqual([candidate.source_path for candidate in inspected.feature_candidates], ["study.Values", "study.Values"])
        self.assertTrue(all(candidate.status == "supported" for candidate in inspected.feature_candidates))
        self.assertIn("FeatureID=F-O2", inspected.feature_candidates[0].reason)
        self.assertIn("study.Observations.Group", inspected.target_candidates)
        self.assertIn("study.Observations.Cov_AgeYears", inspected.covariate_candidates)

    def test_study_defined_selection_preserves_source_rows_definitions_and_missingness(self) -> None:
        rows, definitions = adapters.select_feature_rows(self.document, _study_selection("F-HbR"))
        self.assertEqual([row["ObservationID"] for row in rows], ["OBS-8", "OBS-42"])
        self.assertEqual([row["FeatureID"] for row in rows], ["F-HbR", "F-HbR"])
        self.assertTrue(math.isnan(float(rows[0]["Value"])))
        self.assertFalse(rows[0]["IsValid"])
        self.assertEqual(rows[0]["MissingReason"], "qc_rejected")
        self.assertEqual(rows[0]["SourceID"], "SRC-SYN")
        self.assertEqual(definitions[0]["Metric"], "synthetic_mean")
        self.assertEqual(definitions[0]["Hemoglobin"], "HbR")
        self.assertEqual(definitions[0]["ParameterFingerprint"], "SYNTHETIC-PARAM-B")

    def test_study_defined_selection_rejects_identity_or_transform_drift(self) -> None:
        with self.assertRaisesRegex(adapters.AdapterError, "not present"):
            adapters.select_feature_rows(self.document, _study_selection("f-hbr"))
        with self.assertRaisesRegex(adapters.AdapterError, "extra axes"):
            adapters.select_feature_rows(self.document, _study_selection("F-HbR", axis_selection={"hemoglobin": "HbR"}))
        with self.assertRaisesRegex(adapters.AdapterError, "study-defined"):
            selection = _study_selection("F-HbR")
            wrong = api.ConversionSelection(
                source_adapter_id=selection.source_adapter_id,
                identity=selection.identity,
                feature_selections=(api.FeatureSelection(
                    capability_id="32", feature_id="F-HbR", source_path="study.Values",
                    axis_selection={}, summary_parameters={}),),
                targets=(), covariates=(), output_format="csv", merge_mode="per_file", collision_policy="skip")
            adapters.select_feature_rows(self.document, wrong)


class RawResultsAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        fixture_tests = {
            "test_matlab_exported_fixture_has_explicit_identity_and_registered_shapes",
            "test_table_column_paths_and_text_rows_decode_without_evaluation",
            "test_matlab_oracle_values_cover_scalar_undirected_and_directed_adapters",
        }
        if HAS_RAW_FIXTURE:
            self.document = _load_raw_fixture()
        elif self._testMethodName in fixture_tests:
            self.skipTest(RAW_FIXTURE_SKIP_REASON)
        else:
            self.document = _raw_document()

    def test_matlab_exported_fixture_has_explicit_identity_and_registered_shapes(self) -> None:
        assert RAW_FIXTURE is not None
        oracle = json.loads((RAW_FIXTURE / "expected.json").read_text(encoding="utf-8"))
        self.assertTrue(str(oracle["matlab_version"]).startswith("9."))
        self.assertEqual(oracle["mat_file_format"], "-v7.3")
        self.assertEqual(oracle["top_level_variables"], ["Results"])
        self.assertEqual(oracle["results_size"], [1, 1])
        self.assertIn("Availability", oracle["results_fields"])
        self.assertTrue((RAW_FIXTURE / oracle["mat_file"]).is_file())
        inspected = adapters.inspect_document(self.document, Path("raw_results_synthetic.mat"))
        candidates = {candidate.capability_id: candidate for candidate in inspected.feature_candidates}
        self.assertTrue({"07", "14", "24"}.issubset(candidates))
        self.assertEqual(candidates["24"].axes["hemoglobin"], ("HbO", "HbR"))
        self.assertEqual(candidates["07"].axes["node_a"], ("ROI-A", "ROI-B"))
        self.assertEqual(candidates["14"].axes["source_node"], ("ROI-A", "ROI-B"))
        self.assertTrue(all(candidates[key].status == "conditionally_supported" for key in ("07", "14", "24")))
        self.assertIn("Results.ObservationID", inspected.identity_candidates)
        self.assertIn("Results.Availability.Group", inspected.target_candidates)
        self.assertNotIn("01", candidates, "A struct-valued FC output must not be advertised as Hurst")

    def test_table_column_paths_and_text_rows_decode_without_evaluation(self) -> None:
        self.assertEqual(adapters.resolve_raw_source_path(self.document, "Results.Availability.Group"), ("synthetic_case",))
        self.assertEqual(adapters.resolve_raw_source_path(self.document, "Results.Availability.Group(1)"), ("synthetic_case",))
        self.assertEqual(adapters.resolve_raw_source_path(self.document, "Results.Metadata.MVARGranger.FormulaVersion"), ("conditional_log_residual_variance_ratio_v1",))
        with self.assertRaises(adapters.AdapterError):
            adapters.resolve_raw_source_path(self.document, "Results.Metadata.FC.ModelIndex+1")

    def test_matlab_oracle_values_cover_scalar_undirected_and_directed_adapters(self) -> None:
        assert RAW_FIXTURE is not None
        oracle = json.loads((RAW_FIXTURE / "expected.json").read_text(encoding="utf-8"))
        self.assertTrue(oracle["label"].startswith("SYNTHETIC"))
        rows, definitions = adapters.select_feature_rows(self.document, _raw_selection())
        expected_feature_ids = [
            "PH-HBO-H0-PERSISTENCE",
            "FC-HBO-ROI-A-ROI-B",
            "MVAR-HBO-ROI-A-TO-ROI-B",
            "PH-HBR-H1-PERSISTENCE-MISSING",
        ]
        self.assertEqual([row["FeatureID"] for row in rows], expected_feature_ids)
        self.assertEqual({row["ObservationID"] for row in rows}, {oracle["observation_id"]})
        self.assertEqual([row["IsValid"] for row in rows], [True, True, True, False])
        self.assertEqual(
            [row["MissingReason"] for row in rows],
            ["", "", "", oracle["persistent_homology_hbr_h1_missing_reason"]],
        )
        by_id = {row["FeatureID"]: row for row in rows}
        self.assertEqual(by_id["PH-HBO-H0-PERSISTENCE"]["Value"], oracle["persistent_homology_hbo_h0_total_persistence"])
        self.assertEqual(by_id["FC-HBO-ROI-A-ROI-B"]["Value"], oracle["static_fc_hbo_roi_a_roi_b"])
        self.assertEqual(by_id["MVAR-HBO-ROI-A-TO-ROI-B"]["Value"], oracle["mvar_hbo_source_roi_a_target_roi_b"])
        missing = by_id["PH-HBR-H1-PERSISTENCE-MISSING"]
        self.assertTrue(math.isnan(float(missing["Value"])))
        self.assertEqual(missing["IsValid"], oracle["persistent_homology_hbr_h1_is_valid"])
        self.assertEqual(missing["MissingReason"], oracle["persistent_homology_hbr_h1_missing_reason"])
        self.assertEqual({definition["Metric"] for definition in definitions}, {
            "PersistentHomology_H0_TotalPersistence", "StaticFC_Pearson", "MVAR_GrangerStrength",
            "PersistentHomology_H1_TotalPersistence",
        })
        self.assertTrue(all(definition["ParameterFingerprint"] for definition in definitions))
        self.assertTrue(all(definition["MappingFingerprint"] for definition in definitions))

    def test_raw_registry_gate_remains_closed_and_ibs_fails_closed(self) -> None:
        incomplete = _raw_document()
        root = incomplete["variables"]["Results"]
        root["fields"]["data"]["fields"]["all"] = _cell(
            [_struct({"HbO": _numeric_array([0.5], (1, 1))})], (1, 1)
        )
        inspected = adapters.inspect_document(incomplete, Path("raw_incomplete_ibs.mat"))
        ibs = next(candidate for candidate in inspected.feature_candidates if candidate.capability_id == "15")
        self.assertEqual(ibs.status, "unverified")
        self.assertIn("Pairing", ibs.reason)

        ibs_feature = api.FeatureSelection(
            capability_id="15", feature_id="IBS-SYNTHETIC", source_path="Results.data.all",
            axis_selection={"hemoglobin": "HbO", "role_a": "A", "role_b": "B", "node_a": "N1", "node_b": "N2"},
            summary_parameters={},
        )
        ibs_selection = api.ConversionSelection(
            source_adapter_id=adapters.RAW_RESULTS_ADAPTER_ID,
            identity=api.IdentityMapping("Results.RecordID"),
            feature_selections=(ibs_feature,), targets=(), covariates=(),
            output_format="csv", merge_mode="per_file", collision_policy="skip",
        )
        self.assertEqual(adapters._REGISTRY["15"]["converterActualStatus"], "unverified")
        with self.assertRaisesRegex(adapters.AdapterError, "not selectable"):
            adapters.select_feature_rows(incomplete, ibs_selection)
        with patch.dict(adapters._REGISTRY, {"15": {**adapters._REGISTRY["15"], "converterActualStatus": "conditionally_supported"}}):
            with self.assertRaisesRegex(adapters.AdapterError, "Pairing"):
                adapters.select_feature_rows(incomplete, ibs_selection)

    def test_hurst_is_detected_only_from_tagged_two_cell_layout(self) -> None:
        document = _raw_document()
        results = document["variables"]["Results"]
        entries = []
        for values in ((1.0, 2.0), (0.9, 0.8)):
            entries.append(_struct({
                "HbO": _numeric_array(list(values), (1, 2)),
                "HbR": _numeric_array(list(values), (1, 2)),
                "HbT": _numeric_array(list(values), (1, 2)),
            }))
        results["fields"]["data"]["fields"]["all"] = _cell(entries, (1, 2))
        results["fields"]["Metadata"] = _struct({
            "MissingnessAudit": _struct({"Algorithm": _typed("char", "Hurst", (1, 5))})
        })
        candidates = adapters.inspect_document(document, Path("hurst_synthetic.mat")).feature_candidates
        self.assertIn("01", {candidate.capability_id for candidate in candidates})

        results["fields"]["Metadata"]["fields"]["MissingnessAudit"]["fields"]["Algorithm"] = _typed("char", "FC", (1, 2))
        candidates = adapters.inspect_document(document, Path("cell_fc.mat")).feature_candidates
        self.assertNotIn("01", {candidate.capability_id for candidate in candidates})


if __name__ == "__main__":
    unittest.main()
