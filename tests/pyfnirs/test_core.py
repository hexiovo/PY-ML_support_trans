"""Focused checks for explicit study conversion and fail-closed selection."""

from __future__ import annotations

import json
import os
from pathlib import Path
import unittest

from pyfnirs_converter import api
from pyfnirs_converter.core import ConversionError


def _resolve_study_fixture() -> tuple[Path | None, Path | None]:
    configured = os.environ.get("PYFNIRS_STUDY_EXPORT_FIXTURE")
    if not configured:
        return None, None
    path = Path(configured).expanduser().resolve()
    if path.is_dir():
        candidates = (path / "export" / "study_export.json", path / "study_export.json")
    elif path.name.casefold() == "expected.json":
        candidates = (path.parent / "export" / "study_export.json", path.parent / "study_export.json")
    else:
        candidates = (path,)
    for source in candidates:
        if source.is_file() and source.name.casefold() == "study_export.json":
            root = source.parent.parent if source.parent.name.casefold() == "export" else source.parent
            if (root / "expected.json").is_file():
                return root, source
    return None, None


FIXTURE_DIR, STUDY_EXPORT_PATH = _resolve_study_fixture()
HAS_STUDY_FIXTURE = FIXTURE_DIR is not None and STUDY_EXPORT_PATH is not None
STUDY_FIXTURE_SKIP_REASON = (
    "Set PYFNIRS_STUDY_EXPORT_FIXTURE to the approved study fixture directory, "
    "study_export.json, or expected.json."
)


def study_export_path() -> Path:
    if STUDY_EXPORT_PATH is None:
        raise RuntimeError(STUDY_FIXTURE_SKIP_REASON)
    return STUDY_EXPORT_PATH


def fixture_selection(
    *, output_format: str = "csv", merge_mode: str = "per_file", collision_policy: str = "skip"
) -> api.ConversionSelection:
    if FIXTURE_DIR is None:
        raise RuntimeError(STUDY_FIXTURE_SKIP_REASON)
    expected = json.loads((FIXTURE_DIR / "expected.json").read_text(encoding="utf-8"))
    return api.ConversionSelection(
        source_adapter_id="pyfnirs.study_export.v1",
        identity=api.IdentityMapping(
            observation_id_source_path="study.Observations.ObservationID",
            record_id_source_path="study.Observations.RecordID",
            subject_id_source_path="study.Observations.SubjectID",
            pair_observation_id_source_path="study.Observations.PairObservationID",
            source_id_source_path="study.Observations.SourceID",
        ),
        feature_selections=tuple(
            api.FeatureSelection("study-defined", feature_id, "study.Values", {}, {})
            for feature_id in expected["feature_ids"]
        ),
        targets=(api.FieldMapping("study.Observations.Group", "Group", "target"),),
        covariates=(api.FieldMapping("study.Observations.Cov_AgeYears", "AgeYears", "covariate"),),
        output_format=output_format,
        merge_mode=merge_mode,
        collision_policy=collision_policy,
    )


@unittest.skipUnless(HAS_STUDY_FIXTURE, STUDY_FIXTURE_SKIP_REASON)
class ExplicitStudyConversionTest(unittest.TestCase):
    def test_inspect_convert_and_preview_match_independent_fixture_oracle(self) -> None:
        assert FIXTURE_DIR is not None
        source = study_export_path()
        expected = json.loads((FIXTURE_DIR / "expected.json").read_text(encoding="utf-8"))
        inspection = api.inspect_source(source)
        self.assertEqual(inspection.available_adapters[0], "pyfnirs.study_export.v1")
        self.assertEqual(
            [candidate.capability_id for candidate in inspection.feature_candidates],
            ["study-defined"] * len(expected["feature_ids"]),
        )

        selection = fixture_selection()
        preview = api.preview_conversion(source, selection)
        self.assertEqual(preview.sample_count, len(expected["sample_ids"]))
        self.assertEqual(preview.selected_feature_ids, tuple(expected["feature_ids"]))
        self.assertEqual(preview.missing_count, 1)
        self.assertEqual(preview.output_columns, ("ObservationID", "Group", "AgeYears", *expected["feature_ids"]))

        document = json.loads(source.read_text(encoding="utf-8-sig"))
        actual = api.convert_export(document, selection)
        self.assertEqual([sample["ObservationID"]["value"] for sample in actual["Samples"]], expected["sample_ids"])
        self.assertEqual(actual["FeatureIDs"], expected["feature_ids"])
        actual_value_text = [
            ["NaN" if not valid else format(value, ".15g") for value, valid in zip(row, mask)]
            for row, mask in zip(actual["X"], actual["ValidMask"])
        ]
        self.assertEqual(actual_value_text, expected["matrix_value_text"])
        self.assertEqual(actual["Targets"]["Group"], expected["targets"])
        self.assertEqual([str(int(value)) for value in actual["Covariates"]["AgeYears"]], expected["age_years_text"])
        self.assertEqual(actual["ValidMask"], expected["valid_mask"])
        self.assertEqual(actual["MissingReasons"], expected["missing_reasons"])
        self.assertEqual(
            [definition["FeatureID"]["value"] for definition in actual["FeatureDefinitions"]],
            expected["feature_ids"],
        )

    def test_study_values_rejects_redefinition_and_unknown_feature_ids(self) -> None:
        source = study_export_path()
        document = json.loads(source.read_text(encoding="utf-8-sig"))
        selection = fixture_selection()
        first = selection.feature_selections[0]
        with_window = api.FeatureSelection(
            first.capability_id,
            first.feature_id,
            first.source_path,
            first.axis_selection,
            first.summary_parameters,
            time_window_seconds=(0.0, 1.0),
        )
        changed = api.ConversionSelection(
            selection.source_adapter_id,
            selection.identity,
            (with_window, *selection.feature_selections[1:]),
            selection.targets,
            selection.covariates,
            selection.output_format,
            selection.merge_mode,
            selection.collision_policy,
        )
        with self.assertRaises(ConversionError):
            api.convert_export(document, changed)

        unknown = api.FeatureSelection("study-defined", "NOT-IN-STUDY", "study.Values", {}, {})
        changed_unknown = api.ConversionSelection(
            selection.source_adapter_id,
            selection.identity,
            (unknown,),
            selection.targets,
            selection.covariates,
            selection.output_format,
            selection.merge_mode,
            selection.collision_policy,
        )
        with self.assertRaises(ConversionError):
            api.convert_export(document, changed_unknown)


if __name__ == "__main__":
    unittest.main()
