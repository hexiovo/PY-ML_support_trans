from __future__ import annotations

import csv
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / name) for name in ("hypereeg", "pyfnirs", "pyeda")]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from hypereeg_converter import core as eeg
from pyeda_converter import core as eda
from pyfnirs_converter import api
from pyfnirs_converter.gui import ConversionWindow
from pyfnirs_converter.gui_worker import ApiWorker
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication


class PyedaTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.input = self.root / "data"
        self.records = self.input / "features/records"
        self.records.mkdir(parents=True)
        self.intake = self.input / "intake"
        self.intake.mkdir()
        (self.input / "summary.json").write_text("{}", encoding="utf-8")
        (self.intake / "analysis_settings.json").write_text('{"features":["x"]}', encoding="utf-8")
        (self.intake / "feature_definitions.csv").write_text("feature,unit\nx,arb\n", encoding="utf-8")
        for index in range(3):
            with gzip.open(self.records / f"{index}.csv.gz", "wt", newline="") as stream:
                writer = csv.writer(stream)
                ids = eda.IDENTITY_COLUMNS["records"]
                writer.writerow([*ids, "status", "x"])
                writer.writerow([str(index), *map(str, range(1, len(ids))), "valid", "inf" if index == 2 else index])
        self.write_manifest()
        self.options = eda.ConversionOptions(source="records")

    def write_manifest(self):
        manifest = self.input / "manifest.json"
        entries = [{"path": p.relative_to(self.input).as_posix(), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                   for p in self.input.rglob("*") if p.is_file() and p != manifest]
        manifest.write_text(json.dumps({"artifacts": entries}), encoding="utf-8")

    def test_manifest_and_dictionary_required(self):
        manifest = self.input / "manifest.json"
        manifest.write_text('{"artifacts":[]}', encoding="utf-8")
        with self.assertRaisesRegex(eda.ConversionError, "清单哈希"):
            eda.convert_bundle(self.input, self.root / "missing-hash", self.options)
        (self.intake / "feature_definitions.csv").write_text("feature\ny\n", encoding="utf-8")
        self.write_manifest()
        with self.assertRaisesRegex(eda.ConversionError, "缺少已登记特征"):
            eda.convert_bundle(self.input, self.root / "missing-feature", self.options)

    def test_streams_aligned_data_and_mask_and_cancels_without_publication(self):
        out = self.root / "valid"
        result = eda.convert_bundle(self.input, out, self.options)
        self.assertEqual(result["rows"], 3)
        def load(path):
            with path.open(encoding="utf-8-sig", newline="") as stream:
                return list(csv.DictReader(stream))
        data = load(out / "dataset.csv")
        mask = load(out / "valid_mask.csv")
        self.assertEqual([row["sample_id"] for row in data], [row["sample_id"] for row in mask])
        self.assertEqual([row["feature__x"] for row in mask], ["1", "1", "0"])
        cancel = threading.Event()
        def progress(stage, current, total, detail):
            if stage == "复核来源未变更":
                cancel.set()
        out = self.root / "cancelled"
        with self.assertRaises(eda.ConversionCancelled):
            eda.convert_bundle(self.input, out, self.options, cancel_event=cancel, progress_callback=progress)
        self.assertFalse((out / "dataset.csv").exists())
        self.assertFalse((out / "valid_mask.csv").exists())
        self.assertEqual(json.loads((out / "batch_summary.json").read_text(encoding="utf-8"))["status"], "cancelled")


class HyperEegTests(unittest.TestCase):
    def test_source_path_and_hash_match_loaded_data_and_change_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source#v1.csv"
            source.write_text("subject,x\ns1,1\ns2,2\n", encoding="utf-8")
            opts = eeg.Options(sample_columns=("subject",), value_columns=("x",))
            item = eeg.convert_tables(eeg.load_tables(source, opts), opts)
            eeg.write_package(item, root / "out", opts, source)
            manifest = json.loads((root / "out/provenance.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["tables"][0]["source_path"], str(source))
            self.assertEqual(manifest["tables"][0]["source_sha256"], hashlib.sha256(source.read_bytes()).hexdigest())
            source.write_text("subject,x\ns1,31\ns2,2\n", encoding="utf-8")
            with self.assertRaisesRegex(eeg.ConversionError, "发生变化"):
                eeg.write_package(item, root / "refuse", opts, source)


class PyfnirsTests(unittest.TestCase):
    def test_ranges_are_enforced_at_inspection_and_export(self):
        def struct(**values):
            return dict(matlab_class="struct", shape=[1, 1], fields=values)
        def cell(value, kind="char"):
            return dict(matlab_class=kind, shape=[1, 1], value=str(value))
        def array(values, shape, kind):
            return dict(matlab_class=kind, shape=shape, elements=[cell(value, kind) for value in values])
        def record(coefficient):
            metadata = struct(FC=struct(ModelIndex=cell(1, "double"), Kind=cell("static"),
                                        ParameterFingerprint=cell("a" * 64), NodeOrder=array(["a", "b"], [1, 2], "string")))
            data = struct(all=struct(HbO=array([1, coefficient, coefficient, 1], [2, 2], "double")))
            return {"schema": "pyfnirs.raw-mat-export/1", "source_adapter_id": "pyfnirs.raw_results.v1",
                    "variables": {"Results": struct(ObservationID=cell("demo"), Metadata=metadata, data=data)}}
        selection = api.ConversionSelection(
            "pyfnirs.raw_results.v1", api.IdentityMapping("Results.ObservationID"),
            (api.FeatureSelection("07", "edge", "Results.data.all", {
                "algorithm": "Pearson", "hemoglobin": "HbO", "node_a": "a", "node_b": "b",
            }, {}),), (), (), "csv", "per_file", "skip",
        )
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            src = root / "input.json"
            src.write_text(json.dumps(record(1.2)), encoding="utf-8")
            view = api.inspect_source(src)
            self.assertEqual(next(x.status for x in view.feature_candidates if x.capability_id == "07"), "unverified")
            run = api.convert_batch(api.BatchRequest((src,), root / "bad", selection))
            self.assertEqual(run.files[0].status, "failed")
            src.write_text(json.dumps(record(-0.5)), encoding="utf-8")
            run = api.convert_batch(api.BatchRequest((src,), root / "good", selection))
            self.assertEqual(run.files[0].status, "success")

    def test_close_waits_for_worker_and_cancels_inspection(self):
        app = QApplication.instance() or QApplication([])
        app.setQuitOnLastWindowClosed(False)
        window = ConversionWindow()
        window.show()
        worker = ApiWorker("inspect", path=Path("synthetic.json"), parent=window)
        loop = QEventLoop()
        worker.finished.connect(loop.quit)
        with patch.object(api, "inspect_source", side_effect=lambda *a, cancel_event, **kw: cancel_event.wait(2)):
            window._launch_worker(worker)
            self.assertFalse(window.close())
            self.assertTrue(window.isVisible())
            QTimer.singleShot(4000, loop.quit)
            loop.exec()
        self.assertIsNone(window._worker)
        self.assertFalse(window.isVisible())
