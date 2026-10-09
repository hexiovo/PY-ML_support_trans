"""Standalone Chinese Qt interface for PYfNIRs batch conversion.

The window is deliberately a client of :mod:`pyfnirs_converter.api`: source
inspection, previews, validation, conversion, output handling, and cancellation
remain owned by the converter core.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import api
from .gui_worker import ApiWorker


_PLACEHOLDER = "— 请选择 —"
_ROLE_NONE = "不映射"
_ROLE_TARGET = "目标"
_ROLE_COVARIATE = "协变量"
_SELECTABLE_STATUSES = {"supported", "conditionally_supported"}
_CANDIDATE_STATUS_LABELS = {
    "supported": "已支持",
    "conditionally_supported": "条件支持",
    "unverified": "未验证",
    "unsupported": "不支持",
}
_INPUT_SUFFIXES = {".mat", ".json"}
_REGISTERED_FONT_IDS: list[int] = []


def _apply_chinese_font() -> None:
    """Register a process-local CJK font when the Qt platform has no fallback."""
    application = QApplication.instance()
    if application is None:
        return

    preferred = (
        "microsoft yahei ui",
        "microsoft yahei",
        "noto sans sc",
        "simhei",
        "simsun",
    )
    available = {family.casefold(): family for family in QFontDatabase.families()}
    selected = next((available[name] for name in preferred if name in available), None)
    if selected is None:
        fonts_dir = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
        candidates = (
            fonts_dir / "msyh.ttc",
            fonts_dir / "NotoSansSC-VF.ttf",
            fonts_dir / "simhei.ttf",
            fonts_dir / "simsun.ttc",
        )
        for font_path in candidates:
            if not font_path.is_file():
                continue
            font_id = QFontDatabase.addApplicationFont(str(font_path))
            if font_id < 0:
                continue
            _REGISTERED_FONT_IDS.append(font_id)
            families = QFontDatabase.applicationFontFamilies(font_id)
            selected = next(
                (family for family in families if family.casefold() in preferred),
                families[0] if families else None,
            )
            if selected is not None:
                break
    if selected is not None:
        font = QFont(selected)
        font.setPointSize(9)
        application.setFont(font)


def _normal_path(path: Path) -> Path:
    """Resolve a path without requiring that it already exists."""
    return path.expanduser().resolve(strict=False)


def _is_within(path: Path, parent: Path) -> bool:
    try:
        _normal_path(path).relative_to(_normal_path(parent))
        return True
    except ValueError:
        return False


def _axis_options(raw: Any) -> tuple[str | int, ...]:
    if isinstance(raw, (tuple, list)):
        return tuple(value for value in raw if isinstance(value, (str, int)))
    if isinstance(raw, (str, int)):
        return (raw,)
    return ()


def _json_parameters(text: str) -> dict[str, float | int | str]:
    if not text.strip():
        return {}
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("汇总参数必须是 JSON 对象，例如 {\"ddof\": 1}。")
    result: dict[str, float | int | str] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not isinstance(item, (str, int, float)):
            raise ValueError("汇总参数只接受字符串键，以及字符串、整数或数值。")
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueError("汇总参数不能包含 NaN 或无穷值。")
        result[key] = item
    return result


class FeatureSelectionDialog(QDialog):
    """Collect explicit parameters for one registry-reported candidate."""

    def __init__(self, candidate: api.FeatureCandidate, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.candidate = candidate
        self.setWindowTitle("配置特征选择")
        self.setMinimumWidth(560)
        self._axis_controls: dict[str, QComboBox] = {}

        layout = QVBoxLayout(self)
        help_label = QLabel(
            "仅显示来源检查返回的轴、投影和汇总方法。FeatureID 由你明确填写。"
            "频带和时间窗由核心预览按来源注册规则校验；不合规项会列入拒绝原因。"
        )
        help_label.setWordWrap(True)
        layout.addWidget(help_label)

        form = QFormLayout()
        self.feature_id_edit = QLineEdit()
        self.feature_id_edit.setPlaceholderText("必填，例如由你定义的稳定特征 ID")
        form.addRow("输出 FeatureID：", self.feature_id_edit)

        axes = getattr(candidate, "axes", {}) or {}
        for axis_name, raw_allowed in axes.items():
            combo = QComboBox()
            combo.addItem(_PLACEHOLDER, None)
            for value in _axis_options(raw_allowed):
                combo.addItem(str(value), value)
            if combo.count() == 1:
                combo.setEnabled(False)
            self._axis_controls[str(axis_name)] = combo
            form.addRow(f"轴 {axis_name}（选一个登记值）：", combo)

        self.band_enabled = QCheckBox("指定频带")
        self.band_edit = QLineEdit()
        self.band_edit.setPlaceholderText("下限, 上限（Hz），例如 0.01, 0.1")
        self.band_edit.setEnabled(False)
        self.band_enabled.toggled.connect(self.band_edit.setEnabled)
        band_row = QWidget()
        band_layout = QHBoxLayout(band_row)
        band_layout.setContentsMargins(0, 0, 0, 0)
        band_layout.addWidget(self.band_enabled)
        band_layout.addWidget(self.band_edit, 1)
        form.addRow("频带选择：", band_row)

        self.window_enabled = QCheckBox("指定时间窗")
        self.window_edit = QLineEdit()
        self.window_edit.setPlaceholderText("起始秒, 结束秒")
        self.window_edit.setEnabled(False)
        self.window_enabled.toggled.connect(self.window_edit.setEnabled)
        window_row = QWidget()
        window_layout = QHBoxLayout(window_row)
        window_layout.setContentsMargins(0, 0, 0, 0)
        window_layout.addWidget(self.window_enabled)
        window_layout.addWidget(self.window_edit, 1)
        form.addRow("时间窗选择：", window_row)

        self.projection_combo = self._choice_combo(
            getattr(candidate, "allowed_complex_projections", ()) or ()
        )
        form.addRow("复数投影（可选）：", self.projection_combo)
        self.summary_combo = self._choice_combo(getattr(candidate, "allowed_summaries", ()) or ())
        form.addRow("汇总方法（可选）：", self.summary_combo)

        self.parameters_edit = QPlainTextEdit()
        self.parameters_edit.setPlaceholderText("仅当所选方法需要参数时填写 JSON 对象")
        self.parameters_edit.setMaximumHeight(82)
        form.addRow("汇总参数 JSON：", self.parameters_edit)
        layout.addLayout(form)

        self.error_label = QLabel()
        self.error_label.setStyleSheet("color: #a12622;")
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _choice_combo(values: tuple[Any, ...] | list[Any]) -> QComboBox:
        combo = QComboBox()
        combo.addItem(_PLACEHOLDER, None)
        for value in values:
            combo.addItem(str(value), value)
        return combo

    @staticmethod
    def _range_value(enabled: bool, text: str, label: str) -> tuple[float, float] | None:
        if not enabled:
            return None
        parts = [part.strip() for part in text.split(",")]
        if len(parts) != 2:
            raise ValueError(f"{label}需要填写两个逗号分隔的数值。")
        try:
            low, high = (float(part) for part in parts)
        except ValueError as exc:
            raise ValueError(f"{label}必须是两个数值。") from exc
        if not math.isfinite(low) or not math.isfinite(high) or low >= high:
            raise ValueError(f"{label}必须有限，且下限小于上限。")
        return (low, high)

    def _make_selection(self) -> api.FeatureSelection:
        feature_id = self.feature_id_edit.text().strip()
        if not feature_id:
            raise ValueError("请填写 FeatureID；程序不会替你生成或复用能力 ID。")

        axis_selection: dict[str, str | int] = {}
        for axis, combo in self._axis_controls.items():
            value = combo.currentData()
            if value is None:
                raise ValueError(f"请为轴 {axis} 显式选择一个登记值。")
            axis_selection[axis] = value

        return api.FeatureSelection(
            capability_id=self.candidate.capability_id,
            feature_id=feature_id,
            source_path=self.candidate.source_path,
            axis_selection=axis_selection,
            frequency_band_hz=self._range_value(
                self.band_enabled.isChecked(), self.band_edit.text(), "频带"
            ),
            time_window_seconds=self._range_value(
                self.window_enabled.isChecked(), self.window_edit.text(), "时间窗"
            ),
            complex_projection=self.projection_combo.currentData(),
            summary_method=self.summary_combo.currentData(),
            summary_parameters=_json_parameters(self.parameters_edit.toPlainText()),
        )

    def _validate_and_accept(self) -> None:
        try:
            self._make_selection()
        except (ValueError, json.JSONDecodeError) as exc:
            self.error_label.setText(str(exc))
            return
        self.accept()

    def selection(self) -> api.FeatureSelection:
        return self._make_selection()


class ConversionWindow(QMainWindow):
    """Chinese standalone batch converter window backed by the public API."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        _apply_chinese_font()
        self.setWindowTitle("PYfNIRs → PY-ML 批量转换")
        self.resize(1180, 900)
        self._worker: ApiWorker | None = None
        self._active_action: str | None = None
        self._inspection: api.SourceInspection | None = None
        self._source_files: list[Path] = []
        self._feature_selections: dict[int, api.FeatureSelection] = {}
        self._feature_candidates: list[api.FeatureCandidate] = []

        self._build_ui()

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)

        title = QLabel("PYfNIRs 中文批量转换")
        title.setStyleSheet("font-size: 20px; font-weight: 600;")
        outer.addWidget(title)
        intro = QLabel(
            "先检查一个来源文件，再明确选择适配器、身份、标签和特征。预览与实际转换采用相同规则。"
        )
        intro.setWordWrap(True)
        outer.addWidget(intro)

        io_group = QGroupBox("输入、输出与来源类型")
        io_grid = QGridLayout(io_group)
        self.input_edit = QLineEdit()
        self.input_edit.setObjectName("inputDirectory")
        self.input_edit.setPlaceholderText("选择包含 .mat 或 study_export.json 的目录")
        self.input_browse = QPushButton("选择…")
        self.input_browse.clicked.connect(self._browse_input)
        io_grid.addWidget(QLabel("输入目录："), 0, 0)
        io_grid.addWidget(self.input_edit, 0, 1)
        io_grid.addWidget(self.input_browse, 0, 2)

        self.output_edit = QLineEdit()
        self.output_edit.setObjectName("outputDirectory")
        self.output_edit.setPlaceholderText("转换结果保存到此目录")
        self.output_browse = QPushButton("选择…")
        self.output_browse.clicked.connect(self._browse_output)
        io_grid.addWidget(QLabel("输出目录："), 1, 0)
        io_grid.addWidget(self.output_edit, 1, 1)
        io_grid.addWidget(self.output_browse, 1, 2)

        self.matlab_edit = QLineEdit()
        self.matlab_edit.setPlaceholderText("可选；原生 MAT 需要 MATLAB 时填写 matlab.exe")
        self.matlab_browse = QPushButton("选择…")
        self.matlab_browse.clicked.connect(self._browse_matlab)
        io_grid.addWidget(QLabel("MATLAB 路径："), 2, 0)
        io_grid.addWidget(self.matlab_edit, 2, 1)
        io_grid.addWidget(self.matlab_browse, 2, 2)

        self.recursive_check = QCheckBox("递归扫描子目录")
        self.recursive_check.setObjectName("recursiveScan")
        self.adapter_combo = QComboBox()
        self.adapter_combo.setObjectName("sourceAdapter")
        self.adapter_combo.addItem(_PLACEHOLDER, None)
        self.sample_combo = QComboBox()
        self.sample_combo.setObjectName("sampleFile")
        self.scan_button = QPushButton("检查输入")
        self.scan_button.setObjectName("inspectSources")
        self.scan_button.clicked.connect(self._scan_and_inspect)
        io_grid.addWidget(self.recursive_check, 3, 0)
        io_grid.addWidget(QLabel("转换类型："), 3, 1)
        io_grid.addWidget(self.adapter_combo, 3, 2)
        io_grid.addWidget(QLabel("检查样本文件："), 4, 0)
        io_grid.addWidget(self.sample_combo, 4, 1)
        io_grid.addWidget(self.scan_button, 4, 2)
        outer.addWidget(io_group)

        self.adapter_combo.currentIndexChanged.connect(self._adapter_changed)
        self.sample_combo.currentIndexChanged.connect(self._sample_changed)

        self.inspection_label = QLabel("尚未检查来源文件。")
        self.inspection_label.setWordWrap(True)
        outer.addWidget(self.inspection_label)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self._build_mapping_panel())
        splitter.addWidget(self._build_feature_panel())
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        outer.addWidget(splitter, 1)

        output_group = QGroupBox("输出与批处理")
        output_layout = QGridLayout(output_group)
        self.format_combo = QComboBox()
        self.format_combo.addItem("CSV 文件组", "csv")
        self.format_combo.addItem("Excel 工作簿", "xlsx")
        self.merge_combo = QComboBox()
        self.merge_combo.addItem("每个来源分别输出", "per_file")
        self.merge_combo.addItem("兼容来源合并输出", "merge")
        self.collision_combo = QComboBox()
        self.collision_combo.addItem("重名时跳过", "skip")
        self.collision_combo.addItem("重名时改名", "rename")
        output_layout.addWidget(QLabel("格式："), 0, 0)
        output_layout.addWidget(self.format_combo, 0, 1)
        output_layout.addWidget(QLabel("合并："), 0, 2)
        output_layout.addWidget(self.merge_combo, 0, 3)
        output_layout.addWidget(QLabel("输出冲突："), 0, 4)
        output_layout.addWidget(self.collision_combo, 0, 5)

        self.preview_button = QPushButton("预览转换")
        self.preview_button.setObjectName("previewConversion")
        self.preview_button.clicked.connect(self._preview)
        self.start_button = QPushButton("开始批量转换")
        self.start_button.setObjectName("startBatch")
        self.start_button.clicked.connect(self._start_batch)
        self.cancel_button = QPushButton("取消批处理")
        self.cancel_button.setObjectName("cancelBatch")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self._cancel_batch)
        output_layout.addWidget(self.preview_button, 1, 0, 1, 2)
        output_layout.addWidget(self.start_button, 1, 2, 1, 2)
        output_layout.addWidget(self.cancel_button, 1, 4, 1, 2)
        outer.addWidget(output_group)

        progress_row = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("batchProgress")
        self.progress_bar.setRange(0, 100)
        self.progress_message = QLabel("等待操作。")
        self.progress_message.setWordWrap(True)
        progress_row.addWidget(self.progress_bar, 1)
        progress_row.addWidget(self.progress_message, 2)
        outer.addLayout(progress_row)

        result_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.preview_table = QTableWidget(0, 2)
        self.preview_table.setObjectName("previewSummary")
        self.preview_table.setHorizontalHeaderLabels(["预览项目", "结果"])
        self.preview_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.preview_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.result_table = QTableWidget(0, 6)
        self.result_table.setObjectName("fileResults")
        self.result_table.setHorizontalHeaderLabels(
            ["来源文件", "状态", "样本数", "特征数", "输出路径", "错误或说明"]
        )
        self.result_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.result_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.result_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        result_splitter.addWidget(self.preview_table)
        result_splitter.addWidget(self.result_table)
        result_splitter.setStretchFactor(0, 1)
        result_splitter.setStretchFactor(1, 2)
        outer.addWidget(result_splitter, 1)

        self.summary_label = QLabel("批处理汇总：尚无结果。")
        self.summary_label.setWordWrap(True)
        outer.addWidget(self.summary_label)

        self._set_data_controls_enabled(False)

    def _build_mapping_panel(self) -> QWidget:
        panel = QGroupBox("身份、目标和协变量映射")
        layout = QVBoxLayout(panel)
        identity_grid = QGridLayout()
        self.identity_combos: dict[str, QComboBox] = {}
        identity_fields = (
            ("observation_id_source_path", "观察 ID（必填）"),
            ("record_id_source_path", "记录 ID（可选）"),
            ("subject_id_source_path", "主体 ID（可选）"),
            ("pair_observation_id_source_path", "配对观察 ID（可选）"),
            ("pair_id_source_path", "配对 ID（可选）"),
            ("source_id_source_path", "来源 ID（可选）"),
        )
        for index, (key, label) in enumerate(identity_fields):
            row, column = divmod(index, 3)
            identity_grid.addWidget(QLabel(label + ":"), row, column * 2)
            combo = QComboBox()
            combo.setObjectName(key)
            combo.addItem(_PLACEHOLDER, None)
            combo.currentTextChanged.connect(
                lambda text, target=combo: target.setToolTip(text)
            )
            self.identity_combos[key] = combo
            identity_grid.addWidget(combo, row, column * 2 + 1)
        layout.addLayout(identity_grid)
        note = QLabel(
            "身份字段必须从检查结果中明确选择。Group/Condition、文件名和行序不会自动成为目标或观察 ID。"
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        self.field_table = QTableWidget(0, 4)
        self.field_table.setObjectName("fieldMappings")
        self.field_table.setHorizontalHeaderLabels(["来源字段", "形状 / 类型 / 粒度", "映射角色", "输出列名"])
        self.field_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.field_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.field_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.field_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.field_table, 1)
        return panel

    def _build_feature_panel(self) -> QWidget:
        panel = QGroupBox("特征选择（由注册能力决定）")
        layout = QVBoxLayout(panel)
        note = QLabel(
            "不支持或未验证的项目会显示来源检查返回的原因。仅已支持或条件支持的项目可配置；"
            "条件参数还要通过预览验证。"
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        self.feature_table = QTableWidget(0, 7)
        self.feature_table.setObjectName("featureCandidates")
        self.feature_table.setHorizontalHeaderLabels(
            ["选择", "能力 ID", "来源字段", "形状 / 单位", "状态", "拒绝原因 / 许可选项", "参数"]
        )
        self.feature_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.feature_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.feature_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.feature_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.feature_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.feature_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.feature_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.feature_table)
        return panel

    def _set_data_controls_enabled(self, enabled: bool) -> None:
        for combo in self.identity_combos.values():
            combo.setEnabled(enabled)
        self.field_table.setEnabled(enabled)
        self.feature_table.setEnabled(enabled)
        self.preview_button.setEnabled(enabled)
        self.start_button.setEnabled(enabled)

    def _browse_input(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "选择输入目录", self.input_edit.text())
        if directory:
            self.input_edit.setText(directory)

    def _browse_output(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "选择输出目录", self.output_edit.text())
        if directory:
            self.output_edit.setText(directory)

    def _browse_matlab(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, "选择 MATLAB 可执行文件", self.matlab_edit.text(), "MATLAB (matlab.exe);;所有文件 (*)"
        )
        if filename:
            self.matlab_edit.setText(filename)

    def _input_paths(self) -> tuple[Path, Path]:
        source_dir_text = self.input_edit.text().strip()
        output_dir_text = self.output_edit.text().strip()
        if not source_dir_text:
            raise ValueError("请先选择输入目录。")
        source_dir = _normal_path(Path(source_dir_text))
        if not source_dir.is_dir():
            raise ValueError(f"输入目录不存在：{source_dir}")
        if not output_dir_text:
            raise ValueError("请先选择输出目录。")
        output_dir = _normal_path(Path(output_dir_text))
        return source_dir, output_dir

    def _scan_source_files(self) -> list[Path]:
        source_dir, output_dir = self._input_paths()
        iterator = source_dir.rglob("*") if self.recursive_check.isChecked() else source_dir.iterdir()
        found = [
            path.resolve(strict=False)
            for path in iterator
            if path.is_file()
            and path.suffix.casefold() in _INPUT_SUFFIXES
            and not _is_within(path, output_dir)
        ]
        return sorted(found, key=lambda path: str(path).casefold())

    def _scan_and_inspect(self) -> None:
        try:
            self._source_files = self._scan_source_files()
        except (OSError, ValueError) as exc:
            self._show_error(str(exc))
            return
        if not self._source_files:
            self._clear_inspection("输入目录中没有可检查的 .mat 或 .json 来源文件（输出目录已排除）。")
            return
        self.adapter_combo.blockSignals(True)
        if self.adapter_combo.count():
            self.adapter_combo.setCurrentIndex(0)
        self.adapter_combo.blockSignals(False)
        self.sample_combo.blockSignals(True)
        self.sample_combo.clear()
        for path in self._source_files:
            self.sample_combo.addItem(str(path), path)
        if self.sample_combo.count():
            self.sample_combo.setCurrentIndex(0)
        self.sample_combo.blockSignals(False)
        self._inspect_selected_sample(None)

    def _adapter_changed(self, index: int) -> None:
        if index < 0 or self.sample_combo.count() == 0 or self._worker is not None:
            return
        adapter = self.adapter_combo.currentData()
        if adapter is None:
            if self._inspection is not None:
                self._clear_inspection("请选择一个来源转换类型以加载对应字段。", preserve_adapter=True)
                self.adapter_combo.setEnabled(bool(self._source_files))
            return
        self._inspect_selected_sample(str(adapter))

    def _sample_changed(self, index: int) -> None:
        if index < 0 or self._worker is not None:
            return
        if self._source_files:
            adapter = self.adapter_combo.currentData()
            self._inspect_selected_sample(str(adapter) if adapter is not None else None)

    def _inspect_selected_sample(self, adapter_id: str | None) -> None:
        path = self.sample_combo.currentData()
        if path is None:
            return
        self._clear_inspection(f"正在检查来源：{path}", preserve_adapter=True)
        self._launch_worker(
            ApiWorker(
                "inspect",
                path=Path(path),
                source_adapter_id=adapter_id,
                matlab_executable=self._matlab_path(),
                parent=self,
            )
        )

    def _clear_inspection(self, message: str, *, preserve_adapter: bool = False) -> None:
        self._inspection = None
        self.inspection_label.setText(message)
        self._set_data_controls_enabled(False)
        self.field_table.setRowCount(0)
        self.feature_table.setRowCount(0)
        self._feature_candidates.clear()
        self._feature_selections.clear()
        for combo in self.identity_combos.values():
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(_PLACEHOLDER, None)
            combo.blockSignals(False)
        if not preserve_adapter:
            self.adapter_combo.blockSignals(True)
            self.adapter_combo.clear()
            self.adapter_combo.addItem(_PLACEHOLDER, None)
            self.adapter_combo.blockSignals(False)

    def _matlab_path(self) -> Path | None:
        text = self.matlab_edit.text().strip()
        return _normal_path(Path(text)) if text else None

    def _on_worker_completed(self, action: str, result: Any) -> None:
        if action == "inspect":
            self._inspection_ready(result)
        elif action == "preview":
            self._show_preview(result)
        elif action == "batch":
            self._show_batch_result(result)

    def _on_worker_failed(self, action: str, message: str) -> None:
        if action == "inspect":
            self._clear_inspection(f"来源检查失败：{message}", preserve_adapter=True)
        elif action == "preview":
            self._add_preview_row("预览错误", message)
            self.progress_message.setText("预览失败；详情由核心 API 返回。")
        else:
            self.progress_message.setText(f"批处理调用失败：{message}")
            self.summary_label.setText(f"批处理汇总：调用失败；{message}")

    def _on_worker_finished(self) -> None:
        worker = self.sender()
        if worker is self._worker:
            self._worker = None
        self._active_action = None
        if isinstance(worker, ApiWorker):
            worker.deleteLater()
        self.scan_button.setEnabled(True)
        self.adapter_combo.setEnabled(bool(self._source_files))
        self.sample_combo.setEnabled(bool(self._source_files))
        self.input_browse.setEnabled(True)
        self.output_browse.setEnabled(True)
        self.matlab_browse.setEnabled(True)
        self.recursive_check.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.cancel_button.setText("取消批处理")
        has_inspection = self._inspection is not None
        self._set_data_controls_enabled(has_inspection)

    def _launch_worker(self, worker: ApiWorker) -> None:
        if self._worker is not None:
            return
        self._worker = worker
        self._active_action = worker.action
        worker.completed.connect(self._on_worker_completed)
        worker.failed.connect(self._on_worker_failed)
        worker.progress.connect(self._on_progress)
        worker.finished.connect(self._on_worker_finished)
        self.scan_button.setEnabled(False)
        self.adapter_combo.setEnabled(False)
        self.sample_combo.setEnabled(False)
        self.input_browse.setEnabled(False)
        self.output_browse.setEnabled(False)
        self.matlab_browse.setEnabled(False)
        self.recursive_check.setEnabled(False)
        self.preview_button.setEnabled(False)
        self.start_button.setEnabled(False)
        self.cancel_button.setEnabled(worker.action == "batch")
        worker.start()

    def _inspection_ready(self, inspection: api.SourceInspection) -> None:
        self._inspection = inspection
        previous_adapter = self.adapter_combo.currentData()
        self.adapter_combo.blockSignals(True)
        self.adapter_combo.clear()
        self.adapter_combo.addItem(_PLACEHOLDER, None)
        for adapter_id in inspection.available_adapters:
            self.adapter_combo.addItem(adapter_id, adapter_id)
        selected_index = self.adapter_combo.findData(previous_adapter) if previous_adapter else -1
        if selected_index > 0:
            self.adapter_combo.setCurrentIndex(selected_index)
        self.adapter_combo.blockSignals(False)

        parts = [
            f"格式：{inspection.source_format}",
            f"来源字段：{len(inspection.fields)}",
            f"特征候选：{len(inspection.feature_candidates)}",
            f"可用转换类型：{len(inspection.available_adapters)}",
        ]
        if inspection.warnings:
            parts.append("检查提示：" + "；".join(inspection.warnings))
        self.inspection_label.setText(" | ".join(parts))

        choices = tuple(dict.fromkeys(str(path) for path in inspection.identity_candidates))
        for combo in self.identity_combos.values():
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(_PLACEHOLDER, None)
            for field_path in choices:
                combo.addItem(field_path, field_path)
                combo.setItemData(combo.count() - 1, field_path, Qt.ItemDataRole.ToolTipRole)
            combo.blockSignals(False)
            combo.setToolTip(str(combo.currentData() or combo.currentText()))

        self._populate_field_table(inspection)
        self._populate_feature_table(inspection)
        self._set_data_controls_enabled(bool(inspection.available_adapters))
        self.adapter_combo.setEnabled(True)
        self.sample_combo.setEnabled(True)
        self.progress_message.setText("来源检查完成；请明确选择转换类型和映射。")

    def _populate_field_table(self, inspection: api.SourceInspection) -> None:
        self.field_table.setRowCount(len(inspection.fields))
        target_paths = set(inspection.target_candidates)
        covariate_paths = set(inspection.covariate_candidates)
        for row, field in enumerate(inspection.fields):
            field_path = str(field.path)
            path_item = QTableWidgetItem(field_path)
            path_item.setToolTip(field_path)
            self.field_table.setItem(row, 0, path_item)
            details = f"{tuple(field.shape)} / {field.matlab_class} / {field.sample_grain or '粒度未报告'}"
            details_item = QTableWidgetItem(details)
            details_item.setToolTip(details)
            self.field_table.setItem(row, 1, details_item)
            role_combo = QComboBox()
            role_combo.addItem(_ROLE_NONE, None)
            if field_path in target_paths:
                role_combo.addItem(_ROLE_TARGET, "target")
            if field_path in covariate_paths:
                role_combo.addItem(_ROLE_COVARIATE, "covariate")
            output_name = QLineEdit()
            output_name.setPlaceholderText("显式填写输出列名")
            output_name.setEnabled(False)
            role_combo.currentIndexChanged.connect(
                lambda index, name_edit=output_name, combo=role_combo: name_edit.setEnabled(
                    combo.currentData() is not None
                )
            )
            self.field_table.setCellWidget(row, 2, role_combo)
            self.field_table.setCellWidget(row, 3, output_name)

    @staticmethod
    def _candidate_status(candidate: api.FeatureCandidate) -> str:
        return str(candidate.status).strip().casefold()

    @staticmethod
    def _localized_candidate_status(status: str) -> str:
        normalized = str(status).strip().casefold()
        return _CANDIDATE_STATUS_LABELS.get(normalized, str(status))

    @classmethod
    def _candidate_selectable(cls, candidate: api.FeatureCandidate) -> bool:
        if cls._candidate_status(candidate) not in _SELECTABLE_STATUSES:
            return False
        axes = getattr(candidate, "axes", {}) or {}
        return all(_axis_options(values) for values in axes.values())

    def _populate_feature_table(self, inspection: api.SourceInspection) -> None:
        self._feature_candidates = list(inspection.feature_candidates)
        self._feature_selections.clear()
        self.feature_table.setRowCount(len(self._feature_candidates))
        for row, candidate in enumerate(self._feature_candidates):
            enabled = self._candidate_selectable(candidate)
            check = QCheckBox()
            check.setEnabled(enabled)
            check.setToolTip(
                candidate.reason
                or ("可配置该能力。" if enabled else "该能力当前不能安全选择；请查看状态与原因。")
            )
            check.stateChanged.connect(lambda state, row_index=row: self._feature_toggled(row_index, state))
            self.feature_table.setCellWidget(row, 0, check)
            self.feature_table.setItem(row, 1, QTableWidgetItem(str(candidate.capability_id)))
            path_item = QTableWidgetItem(str(candidate.source_path))
            path_item.setToolTip(str(candidate.source_path))
            self.feature_table.setItem(row, 2, path_item)
            shape_unit = f"{tuple(candidate.shape)} / {candidate.unit or '单位未报告'}"
            shape_item = QTableWidgetItem(shape_unit)
            shape_item.setToolTip(shape_unit)
            self.feature_table.setItem(row, 3, shape_item)
            status_item = QTableWidgetItem(self._localized_candidate_status(str(candidate.status)))
            status_item.setToolTip(str(candidate.status))
            self.feature_table.setItem(row, 4, status_item)
            allowances = []
            if candidate.allowed_summaries:
                allowances.append("汇总：" + ", ".join(candidate.allowed_summaries))
            if candidate.allowed_complex_projections:
                allowances.append("复数投影：" + ", ".join(candidate.allowed_complex_projections))
            reason = candidate.reason or "未提供额外原因。"
            detail = reason
            if allowances:
                detail += "\n登记允许的选择：" + "；".join(allowances)
            detail_item = QTableWidgetItem(detail)
            detail_item.setToolTip(detail)
            self.feature_table.setItem(row, 5, detail_item)
            config_button = QPushButton("配置…")
            config_button.setEnabled(False)
            config_button.clicked.connect(lambda _checked=False, row_index=row: self._configure_feature(row_index))
            self.feature_table.setCellWidget(row, 6, config_button)

    def _feature_toggled(self, row: int, state: int) -> None:
        is_checked = state == Qt.CheckState.Checked or state == Qt.CheckState.Checked.value
        if not is_checked:
            self._feature_selections.pop(row, None)
            config = self.feature_table.cellWidget(row, 6)
            if isinstance(config, QPushButton):
                config.setEnabled(False)
            return
        if not self._configure_feature(row):
            check = self.feature_table.cellWidget(row, 0)
            if isinstance(check, QCheckBox):
                check.blockSignals(True)
                check.setChecked(False)
                check.blockSignals(False)

    def _configure_feature(self, row: int) -> bool:
        candidate = self._feature_candidates[row]
        dialog = FeatureSelectionDialog(candidate, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        selection = dialog.selection()
        if any(
            existing.feature_id == selection.feature_id and existing.source_path != selection.source_path
            for existing in self._feature_selections.values()
        ):
            self._show_error("FeatureID 必须唯一；请为不同来源字段填写不同的 FeatureID。")
            return False
        self._feature_selections[row] = selection
        config = self.feature_table.cellWidget(row, 6)
        if isinstance(config, QPushButton):
            config.setEnabled(True)
            config.setText("已配置")
        return True

    def _collect_mappings(self) -> tuple[api.IdentityMapping, tuple[api.FieldMapping, ...], tuple[api.FieldMapping, ...]]:
        observation_id = self.identity_combos["observation_id_source_path"].currentData()
        if not observation_id:
            raise ValueError("请显式选择观察 ID 来源字段。")
        identity_kwargs: dict[str, str | None] = {}
        for key, combo in self.identity_combos.items():
            identity_kwargs[key] = combo.currentData()
        identity = api.IdentityMapping(**identity_kwargs)

        targets: list[api.FieldMapping] = []
        covariates: list[api.FieldMapping] = []
        output_names: set[str] = set()
        for row in range(self.field_table.rowCount()):
            source_item = self.field_table.item(row, 0)
            role_combo = self.field_table.cellWidget(row, 2)
            output_edit = self.field_table.cellWidget(row, 3)
            if source_item is None or not isinstance(role_combo, QComboBox) or not isinstance(output_edit, QLineEdit):
                continue
            role = role_combo.currentData()
            if role is None:
                continue
            output_name = output_edit.text().strip()
            if not output_name:
                raise ValueError(f"请为 {source_item.text()} 填写目标或协变量输出列名。")
            if output_name in output_names:
                raise ValueError(f"输出列名重复：{output_name}")
            output_names.add(output_name)
            mapping = api.FieldMapping(source_item.text(), output_name, role)
            (targets if role == "target" else covariates).append(mapping)
        return identity, tuple(targets), tuple(covariates)

    def _selection(self) -> api.ConversionSelection:
        if self._inspection is None:
            raise ValueError("请先检查来源文件。")
        adapter_id = self.adapter_combo.currentData()
        if not adapter_id:
            raise ValueError("请明确选择来源转换类型。")
        identity, targets, covariates = self._collect_mappings()
        feature_selections = tuple(self._feature_selections[row] for row in sorted(self._feature_selections))
        feature_ids = [selection.feature_id for selection in feature_selections]
        if len(feature_ids) != len(set(feature_ids)):
            raise ValueError("所选 FeatureID 必须唯一。")
        return api.ConversionSelection(
            source_adapter_id=str(adapter_id),
            identity=identity,
            feature_selections=feature_selections,
            targets=targets,
            covariates=covariates,
            output_format=self.format_combo.currentData(),
            merge_mode=self.merge_combo.currentData(),
            collision_policy=self.collision_combo.currentData(),
        )

    def _preview(self) -> None:
        sample_path = self.sample_combo.currentData()
        if sample_path is None:
            self._show_error("请先检查输入并选择一个样本来源文件。")
            return
        try:
            selection = self._selection()
        except (TypeError, ValueError) as exc:
            self._show_error(str(exc))
            return
        self.preview_table.setRowCount(0)
        self._launch_worker(
            ApiWorker(
                "preview",
                path=Path(sample_path),
                selection=selection,
                matlab_executable=self._matlab_path(),
                parent=self,
            )
        )

    def _start_batch(self) -> None:
        try:
            input_dir, output_dir = self._input_paths()
            selection = self._selection()
        except (TypeError, ValueError) as exc:
            self._show_error(str(exc))
            return
        if not self._source_files:
            try:
                self._source_files = self._scan_source_files()
            except (OSError, ValueError) as exc:
                self._show_error(str(exc))
                return
        if not self._source_files:
            self._show_error("输入目录中没有可转换的 .mat 或 .json 文件。")
            return
        request = api.BatchRequest(
            input_paths=(input_dir,),
            output_dir=output_dir,
            selection=selection,
            matlab_executable=self._matlab_path(),
            recursive=self.recursive_check.isChecked(),
        )
        self.result_table.setRowCount(0)
        self.progress_bar.setValue(0)
        self.summary_label.setText("批处理汇总：运行中。")
        self._launch_worker(ApiWorker("batch", request=request, parent=self))

    def _cancel_batch(self) -> None:
        if self._worker is not None and self._active_action == "batch":
            self._worker.cancel()
            self.cancel_button.setEnabled(False)
            self.cancel_button.setText("已请求取消…")
            self.progress_message.setText("已向核心发送协作式取消请求；正在等待当前文件安全结束。")

    def _on_progress(self, event: api.ProgressEvent) -> None:
        percent = max(0, min(100, int(event.percent)))
        self.progress_bar.setValue(percent)
        self.progress_message.setText(
            f"{event.index}/{event.total} · {event.phase} · {event.message} · {event.source_path}"
        )

    def _add_preview_row(self, label: str, value: str) -> None:
        row = self.preview_table.rowCount()
        self.preview_table.insertRow(row)
        label_item = QTableWidgetItem(label)
        label_item.setToolTip(label)
        self.preview_table.setItem(row, 0, label_item)
        value_item = QTableWidgetItem(value)
        value_item.setToolTip(value)
        self.preview_table.setItem(row, 1, value_item)

    def _show_preview(self, preview: api.ConversionPreview) -> None:
        self.preview_table.setRowCount(0)
        self._add_preview_row("样本数", str(preview.sample_count))
        self._add_preview_row("特征数", str(len(preview.selected_feature_ids)))
        self._add_preview_row("FeatureID", "、".join(preview.selected_feature_ids) or "无")
        self._add_preview_row("输出列", "、".join(preview.output_columns) or "无")
        self._add_preview_row("目标映射", "、".join(f"{m.source_path} → {m.output_name}" for m in preview.targets) or "无")
        self._add_preview_row("协变量映射", "、".join(f"{m.source_path} → {m.output_name}" for m in preview.covariates) or "无")
        self._add_preview_row("缺失单元数", str(preview.missing_count))
        self._add_preview_row("拒绝特征", "；".join(preview.rejected_features) or "无")
        self._add_preview_row("合并冲突", "；".join(preview.merge_conflicts) or "无")
        self._add_preview_row("提示", "；".join(preview.warnings) or "无")
        self.progress_message.setText("预览已完成；核心 API 未写出文件。")

    @staticmethod
    def _localized_status(status: str) -> str:
        known = {
            "success": "成功",
            "succeeded": "成功",
            "converted": "成功",
            "failed": "失败",
            "error": "失败",
            "skipped": "跳过",
            "cancelled": "已取消",
            "canceled": "已取消",
            "not_processed": "未处理",
            "pending": "未处理",
        }
        return known.get(status.strip().casefold(), status)

    def _show_batch_result(self, result: api.BatchResult) -> None:
        self.result_table.setRowCount(len(result.files))
        counts = {
            "success": 0,
            "failed": 0,
            "skipped": 0,
            "cancelled": 0,
            "not_processed": 0,
            "other": 0,
        }
        for row, file_result in enumerate(result.files):
            status = str(file_result.status)
            lowered = status.strip().casefold()
            if lowered in {"success", "succeeded", "converted"}:
                counts["success"] += 1
            elif lowered in {"failed", "error"}:
                counts["failed"] += 1
            elif lowered == "skipped":
                counts["skipped"] += 1
            elif lowered == "cancelled":
                counts["cancelled"] += 1
            elif lowered == "not_processed":
                counts["not_processed"] += 1
            else:
                counts["other"] += 1
            values = (
                str(file_result.source_path),
                self._localized_status(status),
                "" if file_result.sample_count is None else str(file_result.sample_count),
                str(len(file_result.feature_ids)),
                "\n".join(str(path) for path in file_result.output_paths),
                file_result.error or "",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column in (0, 4, 5):
                    item.setToolTip(value)
                self.result_table.setItem(row, column, item)
        cancelled = "，批次已取消" if result.cancelled else ""
        self.summary_label.setText(
            f"批处理汇总：成功 {counts['success']}，失败 {counts['failed']}，跳过 {counts['skipped']}，"
            f"当前取消文件 {counts['cancelled']}，未处理 {counts['not_processed']}，"
            f"其他状态 {counts['other']}，总计 {len(result.files)}{cancelled}。"
        )
        self.progress_bar.setValue(100 if not result.cancelled else self.progress_bar.value())
        self.progress_message.setText("核心批处理已返回；逐文件状态如表。")

    def _show_error(self, message: str) -> None:
        QMessageBox.warning(self, "需要补充选择", message)
        self.progress_message.setText(message)

    def smoke_snapshot(self) -> dict[str, Any]:
        """Return observable widget state for the offscreen Qt smoke command."""
        mapped_roles = []
        for row in range(self.field_table.rowCount()):
            combo = self.field_table.cellWidget(row, 2)
            if isinstance(combo, QComboBox) and combo.currentData() is not None:
                mapped_roles.append(str(combo.currentData()))
        checked_features = []
        for row in range(self.feature_table.rowCount()):
            checkbox = self.feature_table.cellWidget(row, 0)
            if isinstance(checkbox, QCheckBox) and checkbox.isChecked():
                checked_features.append(row)
        return {
            "window_title": self.windowTitle(),
            "input_directory": self.input_edit.text(),
            "output_directory": self.output_edit.text(),
            "recursive": self.recursive_check.isChecked(),
            "source_adapter": self.adapter_combo.currentData(),
            "observation_id_source_path": self.identity_combos[
                "observation_id_source_path"
            ].currentData(),
            "mapped_roles": mapped_roles,
            "checked_features": checked_features,
            "preview_table_columns": self.preview_table.columnCount(),
            "file_result_columns": self.result_table.columnCount(),
            "cancel_enabled": self.cancel_button.isEnabled(),
        }


__all__ = ["ConversionWindow", "FeatureSelectionDialog"]
