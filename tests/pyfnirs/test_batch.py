"""Batch isolation, collision, output-exclusion, and cancellation behavior."""

from __future__ import annotations

import csv
import json
import hashlib
from pathlib import Path
import shutil
import tempfile
import threading
import unittest

from pyfnirs_converter import api
from pyfnirs_converter.core import ConversionError

from .test_core import (
    HAS_STUDY_FIXTURE,
    STUDY_FIXTURE_SKIP_REASON,
    fixture_selection,
    study_export_path,
)


@unittest.skipUnless(HAS_STUDY_FIXTURE, STUDY_FIXTURE_SKIP_REASON)
class ConverterBatchTest(unittest.TestCase):
    def test_bad_file_is_isolated_and_nested_output_is_excluded(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pyfnirs-batch 中文 ") as temporary:
            root = Path(temporary)
            inputs = root / "输入 空格"
            output = inputs / "输出"
            output.mkdir(parents=True)
            good = inputs / "01 正常.json"
            bad = inputs / "02 损坏.json"
            shutil.copyfile(study_export_path(), good)
            input_hash = hashlib.sha256(good.read_bytes()).hexdigest()
            bad.write_text("{ this is not json", encoding="utf-8")
            (output / "nested.json").write_text("{}", encoding="utf-8")

            events: list[api.ProgressEvent] = []
            request = api.BatchRequest(
                input_paths=(inputs,),
                output_dir=output,
                selection=fixture_selection(),
                recursive=True,
            )
            result = api.convert_batch(request, progress_callback=events.append)
            self.assertFalse(result.cancelled)
            self.assertEqual(len(result.files), 2)
            self.assertEqual([item.status for item in result.files], ["success", "failed"])
            self.assertEqual(len(result.files[0].output_paths), 4)
            self.assertEqual(result.files[0].sample_count, 2)
            self.assertIn("JSON", result.files[1].error or "")
            self.assertTrue(any(event.phase == "completed" for event in events))
            self.assertEqual(hashlib.sha256(good.read_bytes()).hexdigest(), input_hash)
            self.assertEqual((output / "nested.json").read_text(encoding="utf-8"), "{}")

            skipped = api.convert_batch(request)
            self.assertEqual([item.status for item in skipped.files], ["skipped", "failed"])

    def test_rename_policy_and_merge_conflict_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pyfnirs-batch-merge-") as temporary:
            root = Path(temporary)
            inputs = root / "inputs"
            output = root / "out"
            inputs.mkdir()
            for name in ("a.json", "b.json"):
                shutil.copyfile(study_export_path(), inputs / name)

            renamed_selection = fixture_selection(collision_policy="rename")
            request = api.BatchRequest((inputs,), output, renamed_selection)
            first = api.convert_batch(request)
            second = api.convert_batch(request)
            self.assertEqual([item.status for item in first.files], ["success", "success"])
            self.assertEqual([item.status for item in second.files], ["success", "success"])
            self.assertTrue((output / "a_2").is_dir())
            self.assertTrue((output / "b_2").is_dir())

            merge_selection = fixture_selection(merge_mode="merge")
            merge_output = root / "merged"
            merged = api.convert_batch(api.BatchRequest((inputs,), merge_output, merge_selection))
            self.assertFalse(merged.cancelled)
            self.assertEqual([item.status for item in merged.files], ["failed", "failed"])
            self.assertTrue(all("Duplicate ObservationID" in (item.error or "") for item in merged.files))
            self.assertFalse((merge_output / "merged").exists())

    def test_merge_preserves_feature_and_explicit_file_order(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pyfnirs-compatible-merge-") as temporary:
            root = Path(temporary)
            inputs = root / "inputs"
            inputs.mkdir()
            first_path = inputs / "a.json"
            second_path = inputs / "b.json"
            shutil.copyfile(study_export_path(), first_path)
            document = json.loads(study_export_path().read_text(encoding="utf-8-sig"))

            def replace_scalar(cell: dict[str, object], value: str) -> None:
                cell["value"] = value

            observations = document["tables"]["Observations"]["rows"]
            rename = {
                "OBS-42": ("OBS-42-B", "REC-42-B", "SUB-42-B"),
                "OBS-8": ("OBS-8-B", "REC-8-B", "SUB-8-B"),
            }
            for row in observations:
                current = row["ObservationID"]["value"]
                if current in rename:
                    observation_id, record_id, subject_id = rename[current]
                    replace_scalar(row["ObservationID"], observation_id)
                    replace_scalar(row["RecordID"], record_id)
                    replace_scalar(row["SubjectID"], subject_id)
            for row in document["tables"]["Values"]["rows"]:
                current = row["ObservationID"]["value"]
                if current in rename:
                    replace_scalar(row["ObservationID"], rename[current][0])
            pair_link = document["tables"]["PairLinks"]["rows"][0]
            replace_scalar(pair_link["RecordIDA"], "REC-42-B")
            replace_scalar(pair_link["RecordIDB"], "REC-8-B")
            replace_scalar(pair_link["SubjectIDA"], "SUB-42-B")
            replace_scalar(pair_link["SubjectIDB"], "SUB-8-B")
            second_path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")

            output = root / "out"
            result = api.convert_batch(
                api.BatchRequest((inputs,), output, fixture_selection(merge_mode="merge"))
            )
            self.assertEqual([item.status for item in result.files], ["success", "success"])
            self.assertEqual(result.files[0].output_paths, result.files[1].output_paths)
            matrix_path = output / "merged" / "FeatureMatrix.csv"
            with matrix_path.open(encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual([row["ObservationID"] for row in rows], ["OBS-42", "OBS-8", "OBS-42-B", "OBS-8-B"])
            self.assertEqual([row["Group"] for row in rows], ["control", "case", "control", "case"])
            self.assertEqual(list(rows[0].keys())[-2:], ["F-O2", "F-HbR"])

            explicit_output = root / "explicit-order-out"
            explicit_result = api.convert_batch(
                api.BatchRequest((second_path, first_path), explicit_output, fixture_selection(merge_mode="merge"))
            )
            self.assertEqual([item.status for item in explicit_result.files], ["success", "success"])
            self.assertEqual(
                [item.source_path for item in explicit_result.files],
                [second_path.resolve(), first_path.resolve()],
            )
            explicit_matrix = explicit_output / "merged" / "FeatureMatrix.csv"
            with explicit_matrix.open(encoding="utf-8-sig", newline="") as stream:
                explicit_rows = list(csv.DictReader(stream))
            self.assertEqual(
                [row["ObservationID"] for row in explicit_rows],
                ["OBS-42-B", "OBS-8-B", "OBS-42", "OBS-8"],
            )
            self.assertEqual(
                [row["Group"] for row in explicit_rows],
                ["control", "case", "control", "case"],
            )

    def test_cancelled_file_and_remaining_files_are_reported(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pyfnirs-cancel-") as temporary:
            root = Path(temporary)
            inputs = root / "inputs"
            inputs.mkdir()
            for name in ("a.json", "b.json"):
                shutil.copyfile(study_export_path(), inputs / name)
            cancel = threading.Event()

            def cancel_on_first_event(event: api.ProgressEvent) -> None:
                if event.index == 1 and event.phase == "reading":
                    cancel.set()

            result = api.convert_batch(
                api.BatchRequest((inputs,), root / "out", fixture_selection()),
                progress_callback=cancel_on_first_event,
                cancel_event=cancel,
            )
            self.assertTrue(result.cancelled)
            self.assertEqual([item.status for item in result.files], ["cancelled", "not_processed"])
            self.assertFalse((root / "out" / "a").exists())

    def test_no_supported_input_is_reported(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pyfnirs-empty-") as temporary:
            root = Path(temporary)
            (root / "notes.txt").write_text("ignore", encoding="utf-8")
            request = api.BatchRequest((root,), root / "out", fixture_selection())
            with self.assertRaises(ConversionError):
                api.convert_batch(request)


if __name__ == "__main__":
    unittest.main()
