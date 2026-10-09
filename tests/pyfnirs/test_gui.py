"""Qt startup smoke test for the standalone PYfNIRs conversion window."""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication, QDialogButtonBox

from pyfnirs_converter import api, batch
from pyfnirs_converter.gui import ConversionWindow, FeatureSelectionDialog


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _resolve_study_export_fixture(configured_path: str | Path) -> Path:
    """Accept the interchange file, its fixture directory, or expected.json."""
    configured = Path(configured_path).expanduser().resolve()
    if configured.is_dir():
        candidates = (configured / "export" / "study_export.json", configured / "study_export.json")
    elif configured.name.casefold() == "expected.json":
        candidates = (configured.parent / "export" / "study_export.json", configured.parent / "study_export.json")
    else:
        candidates = (configured,)
    for candidate in candidates:
        if candidate.is_file() and candidate.name.casefold() == "study_export.json":
            return candidate
    raise AssertionError(
        "PYFNIRS_STUDY_EXPORT_FIXTURE must point to study_export.json, its fixture directory, "
        f"or expected.json; could not resolve from {configured}"
    )


class ConverterResultPresentationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication(["pyfnirs-gui-results"])

    def test_fixture_resolver_accepts_file_root_and_expected_manifest(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pyfnirs-fixture-path-") as temporary:
            root = Path(temporary)
            export_dir = root / "export"
            export_dir.mkdir()
            export_file = export_dir / "study_export.json"
            export_file.write_text("{}", encoding="utf-8")
            expected_file = root / "expected.json"
            expected_file.write_text("{}", encoding="utf-8")

            self.assertEqual(_resolve_study_export_fixture(export_file), export_file.resolve())
            self.assertEqual(_resolve_study_export_fixture(root), export_file.resolve())
            self.assertEqual(_resolve_study_export_fixture(expected_file), export_file.resolve())

    def test_five_file_states_are_localized_and_counted(self) -> None:
        self.assertEqual(
            [
                ConversionWindow._localized_candidate_status(status)
                for status in ("supported", "conditionally_supported", "unverified", "unsupported")
            ],
            ["已支持", "条件支持", "未验证", "不支持"],
        )
        statuses = ("success", "failed", "skipped", "cancelled", "not_processed")
        files = tuple(
            api.FileResult(Path(f"input-{index}.json"), status, (), None, ())
            for index, status in enumerate(statuses)
        )
        window = ConversionWindow()
        try:
            window._show_batch_result(api.BatchResult(files, cancelled=True))

            localized = [window.result_table.item(row, 1).text() for row in range(len(statuses))]
            self.assertEqual(localized, ["成功", "失败", "跳过", "已取消", "未处理"])
            self.assertEqual(
                window.summary_label.text(),
                "批处理汇总：成功 1，失败 1，跳过 1，当前取消文件 1，未处理 1，其他状态 0，总计 5，批次已取消。",
            )
        finally:
            window.close()


class ConverterWindowSmokeTest(unittest.TestCase):
    def test_offscreen_window_renders_without_implicit_mappings(self) -> None:
        environment = os.environ.copy()
        environment["QT_QPA_PLATFORM"] = "offscreen"
        environment["PYTHONIOENCODING"] = "utf-8"
        completed = subprocess.run(
            [sys.executable, "-m", "pyfnirs_converter", "--smoke"],
            cwd=REPOSITORY_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
        report = json.loads(completed.stdout.strip().splitlines()[-1])
        self.assertEqual(report["status"], "qt_window_smoke_passed")
        self.assertEqual(report["window_title"], "PYfNIRs → PY-ML 批量转换")
        self.assertFalse(report["core_api_checked"])
        self.assertGreater(report["rendered_size"][0], 0)
        self.assertGreater(report["rendered_size"][1], 0)
        self.assertFalse(report["recursive"])
        self.assertIsNone(report["source_adapter"])
        self.assertIsNone(report["observation_id_source_path"])
        self.assertEqual(report["mapped_roles"], [])
        self.assertEqual(report["checked_features"], [])
        self.assertEqual(report["preview_table_columns"], 2)
        self.assertEqual(report["file_result_columns"], 6)
        self.assertFalse(report["cancel_enabled"])


class ConverterApiGuiIntegrationTest(unittest.TestCase):
    """Optional real-core integration against the approved stage-one fixture."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication(["pyfnirs-gui-integration"])

    def _wait_for_worker(self, window: ConversionWindow, timeout_ms: int = 60000) -> None:
        worker = window._worker
        if worker is None:
            return
        loop = QEventLoop()
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)
        worker.finished.connect(loop.quit)
        if not worker.isFinished():
            timer.start(timeout_ms)
            loop.exec()
            timer.stop()
        self.application.processEvents()
        self.assertIsNone(window._worker, "Qt worker did not return through its finished signal")

    @staticmethod
    def _choose_identity_path(window: ConversionWindow, key: str, suffix: str) -> None:
        combo = window.identity_combos[key]
        for index in range(combo.count()):
            value = combo.itemData(index)
            if isinstance(value, str) and value.endswith(suffix):
                combo.setCurrentIndex(index)
                return
        raise AssertionError(f"Inspection did not return an identity path ending in {suffix!r}")

    @staticmethod
    def _map_field(window: ConversionWindow, suffix: str, role: str, output_name: str) -> None:
        for row in range(window.field_table.rowCount()):
            path = window.field_table.item(row, 0).text()
            if not path.endswith(suffix):
                continue
            role_combo = window.field_table.cellWidget(row, 2)
            role_index = role_combo.findData(role)
            if role_index < 0:
                raise AssertionError(f"Inspection did not permit {role!r} for {path!r}")
            role_combo.setCurrentIndex(role_index)
            window.field_table.cellWidget(row, 3).setText(output_name)
            return
        raise AssertionError(f"Inspection did not return field {suffix!r}")

    def _configure_feature(self, window: ConversionWindow, feature_id: str) -> None:
        row = next(
            (
                index
                for index, candidate in enumerate(window._feature_candidates)
                if candidate.source_path == "study.Values"
                and candidate.status in {"supported", "conditionally_supported"}
                and feature_id in candidate.reason
            ),
            None,
        )
        self.assertIsNotNone(row, f"Inspection did not expose registry choice {feature_id!r}")
        checkbox = window.feature_table.cellWidget(row, 0)
        self.assertTrue(checkbox.isEnabled(), f"{feature_id} was not selectable")
        dialog_errors: list[str] = []

        def fill_dialog() -> None:
            dialog = QApplication.activeModalWidget()
            if not isinstance(dialog, FeatureSelectionDialog):
                QTimer.singleShot(10, fill_dialog)
                return
            dialog.feature_id_edit.setText(feature_id)
            for combo in dialog._axis_controls.values():
                if combo.count() > 1:
                    combo.setCurrentIndex(1)
            button_box = dialog.findChild(QDialogButtonBox)
            if button_box is None:
                dialog_errors.append("FeatureSelectionDialog has no button box")
                dialog.reject()
                return
            button_box.button(QDialogButtonBox.StandardButton.Ok).click()

        QTimer.singleShot(0, fill_dialog)
        checkbox.setChecked(True)
        self.assertFalse(dialog_errors, "; ".join(dialog_errors))
        self.assertEqual(window._feature_selections[row].feature_id, feature_id)

    def _configure_window(
        self,
        window: ConversionWindow,
        input_dir: Path,
        output_dir: Path,
    ) -> None:
        window.input_edit.setText(str(input_dir))
        window.output_edit.setText(str(output_dir))
        window._scan_and_inspect()
        self._wait_for_worker(window)
        self.assertIsNotNone(window._inspection)
        adapter_index = window.adapter_combo.findData("pyfnirs.study_export.v1")
        self.assertGreater(adapter_index, 0, "JSON inspection did not expose the Study export adapter")
        window.adapter_combo.setCurrentIndex(adapter_index)
        self._wait_for_worker(window)
        self.assertIsNotNone(window._inspection)

        self._choose_identity_path(window, "observation_id_source_path", ".Observations.ObservationID")
        self._choose_identity_path(window, "record_id_source_path", ".Observations.RecordID")
        self._choose_identity_path(window, "subject_id_source_path", ".Observations.SubjectID")
        self._choose_identity_path(
            window, "pair_observation_id_source_path", ".Observations.PairObservationID"
        )
        self._choose_identity_path(window, "source_id_source_path", ".Observations.SourceID")
        self._map_field(window, ".Observations.Group", "target", "Group")
        self._map_field(window, ".Observations.Cov_AgeYears", "covariate", "AgeYears")
        self._configure_feature(window, "F-O2")
        self._configure_feature(window, "F-HbR")

    @unittest.skipUnless(
        os.environ.get("PYFNIRS_STUDY_EXPORT_FIXTURE"),
        "Set PYFNIRS_STUDY_EXPORT_FIXTURE to the approved stage-one study_export.json.",
    )
    def test_real_inspect_preview_batch_and_cooperative_cancel(self) -> None:
        fixture = _resolve_study_export_fixture(os.environ["PYFNIRS_STUDY_EXPORT_FIXTURE"])
        with tempfile.TemporaryDirectory(prefix="pyfnirs-gui-stage2-") as temporary:
            root = Path(temporary)
            input_dir = root / "batch-input"
            input_dir.mkdir()
            isolated_fixture = input_dir / "study_export.json"
            shutil.copyfile(fixture, isolated_fixture)
            output_dir = root / "输出目录 中文"
            window = ConversionWindow()
            window.show()
            try:
                self._configure_window(window, input_dir, output_dir)
                window.preview_button.click()
                self._wait_for_worker(window)
                preview = {
                    window.preview_table.item(row, 0).text(): window.preview_table.item(row, 1).text()
                    for row in range(window.preview_table.rowCount())
                }
                self.assertEqual(preview["样本数"], "2")
                self.assertEqual(preview["特征数"], "2")
                self.assertEqual(preview["缺失单元数"], "1")
                self.assertEqual(preview["FeatureID"], "F-O2、F-HbR")

                window.start_button.click()
                self._wait_for_worker(window)
                self.assertEqual(window.result_table.rowCount(), 1)
                self.assertEqual(window.result_table.item(0, 1).text(), "成功")
                output_paths = [
                    Path(value)
                    for value in window.result_table.item(0, 4).text().splitlines()
                    if value.strip()
                ]
                self.assertEqual(len(output_paths), 4)
                self.assertTrue(all(path.is_file() for path in output_paths))
                matrix_path = next(path for path in output_paths if path.name == "FeatureMatrix.csv")
                with matrix_path.open("r", encoding="utf-8-sig", newline="") as stream:
                    matrix = list(csv.DictReader(stream))
                self.assertEqual([row["ObservationID"] for row in matrix], ["OBS-42", "OBS-8"])
                self.assertEqual([row["Group"] for row in matrix], ["control", "case"])
                self.assertEqual([row["F-O2"] for row in matrix], ["1.25", "2.5"])
                self.assertEqual([row["F-HbR"] for row in matrix][0], "3.75")
                screenshot_path = os.environ.get("PYFNIRS_GUI_EVIDENCE_SCREENSHOT")
                if screenshot_path:
                    destination = Path(screenshot_path)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    self.application.processEvents()
                    self.assertTrue(window.grab().save(str(destination), "PNG"))

                cancel_input = root / "cancel-input"
                cancel_input.mkdir()
                for index in range(32):
                    shutil.copyfile(isolated_fixture, cancel_input / f"fixture-{index:02d}.json")
                cancel_output = root / "cancel-output"
                cancel_window = ConversionWindow()
                cancel_window.show()
                try:
                    self._configure_window(cancel_window, cancel_input, cancel_output)
                    conversion_started = threading.Event()
                    original_convert_one = batch._convert_one

                    def hold_first_conversion(source, request, cancel_event):
                        if not conversion_started.is_set():
                            conversion_started.set()
                            cancel_event.wait(timeout=10)
                        return original_convert_one(source, request, cancel_event)

                    with patch("pyfnirs_converter.batch._convert_one", side_effect=hold_first_conversion):
                        cancel_window.start_button.click()
                        entered_conversion = conversion_started.wait(timeout=5)
                        if entered_conversion and cancel_window.cancel_button.isEnabled():
                            cancel_window.cancel_button.click()
                        elif cancel_window.cancel_button.isEnabled():
                            cancel_window.cancel_button.click()
                        self._wait_for_worker(cancel_window)
                    self.assertTrue(entered_conversion, "Batch did not enter its first source conversion")
                    self.assertIn("批次已取消", cancel_window.summary_label.text())
                    statuses = [
                        cancel_window.result_table.item(row, 1).text()
                        for row in range(cancel_window.result_table.rowCount())
                    ]
                    self.assertEqual(len(statuses), 32)
                    self.assertEqual(statuses.count("已取消"), 1)
                    self.assertEqual(statuses.count("未处理"), 31)
                    self.assertIn("当前取消文件 1，未处理 31", cancel_window.summary_label.text())
                finally:
                    cancel_window.close()
            finally:
                window.close()


if __name__ == "__main__":
    unittest.main()
