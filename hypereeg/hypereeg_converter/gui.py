"""Chinese independent Qt window; all conversion work stays off the UI thread."""
from __future__ import annotations

import os
import threading
from pathlib import Path

# Load the table stack before PySide's feature-import hook is registered; six's
# synthetic modules have no source files for frozen inspect.getsource to read.
from . import __version__
from .core import Options, batch, preview, scan

from PySide6.QtCore import QThread, Signal, QUrl
from PySide6.QtGui import QDesktopServices, QFont, QFontDatabase
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QProgressBar,
    QPushButton, QTableWidget, QTableWidgetItem, QTabWidget, QTextEdit, QVBoxLayout, QWidget,
)

class Worker(QThread):
    progress = Signal(int, int, object)
    result = Signal(object)
    error = Signal(str)

    def __init__(self, operation, cancel, parent=None):
        super().__init__(parent)
        self.operation, self.cancel = operation, cancel

    def run(self):
        try:
            self.result.emit(self.operation(self.progress.emit))
        except Exception as exc:
            self.error.emit(str(exc))


def fields(value):
    return tuple(part.strip() for part in value.replace("，", ",").split(",") if part.strip())


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"PY-ML 数据转换 · HyperEEG {__version__}")
        self.resize(1080, 800)
        self.setMinimumSize(820, 660)
        self.worker = None
        self.cancel = threading.Event()
        self.last_output = None
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        title = QLabel("HyperEEG 特征数据转换")
        title.setStyleSheet("font-size: 22px; font-weight: 600; color: #17324d; padding: 4px;")
        layout.addWidget(title)
        explanation = QLabel("一行保留一个真实样本；通道、频带等坐标变成特征列。原始数据保持只读。")
        layout.addWidget(explanation)
        settings = QGroupBox("输入与输出")
        form = QFormLayout(settings)
        self.converter = QComboBox()
        self.converter.addItem("HyperEEG — 正式特征表 / MATLAB 原生载荷")
        form.addRow("转换器", self.converter)
        self.input_edit = self.path_row(form, "输入目录", directory=True)
        self.output_edit = self.path_row(form, "输出目录", directory=True)
        self.preview_edit = self.path_row(form, "预览文件（可选）", filter="特征/参考表 (*.csv *.xlsx *.mat)")
        flags = QHBoxLayout()
        self.recursive = QCheckBox("递归扫描子目录")
        self.recursive.setChecked(True)
        self.merge = QCheckBox("同时生成合并数据集（保留逐文件输出）")
        self.merge.setChecked(True)
        self.metadata_only = QCheckBox("只导出参考工作表")
        flags.addWidget(self.recursive)
        flags.addWidget(self.merge)
        flags.addWidget(self.metadata_only)
        form.addRow(flags)
        layout.addWidget(settings)
        self.tabs = QTabWidget()
        mappings = QWidget()
        mapping = QFormLayout(mappings)
        help_text = QLabel("已识别的正式长表和单导 CSV 可自动映射。其它载荷须填写列名，以英文逗号分隔。\n样本列必须表示被试/场次/片段；通道、频带、节点、边放入坐标列。")
        help_text.setWordWrap(True)
        mapping.addRow(help_text)
        self.samples = QLineEdit()
        self.samples.setPlaceholderText("自动；例：file_name,subject_id,session,condition")
        self.coordinates = QLineEdit()
        self.coordinates.setPlaceholderText("自动；例：result_key,measure,cell_key 或 channel_index,band")
        self.values = QLineEdit()
        self.values.setPlaceholderText("自动；例：value 或 rms,std")
        self.table_path = QLineEdit()
        self.table_path.setPlaceholderText("默认 FeatureResult.longData；例：Artifact.payload.data")
        self.sheet = QLineEdit()
        self.sheet.setPlaceholderText("默认读取所有工作表；例：分析长表")
        for label, control in (("样本身份列", self.samples), ("特征坐标列", self.coordinates), ("数值列", self.values), ("MAT table 路径", self.table_path), ("输入工作表", self.sheet)):
            mapping.addRow(label, control)
        self.matlab = self.path_row(mapping, "MATLAB 程序（仅 MAT 需要）", filter="MATLAB (matlab.exe)")
        notice = QLabel("高维矩阵、cell 载荷或跨样本拟合结果需要原项目的明确坐标/拟合边界。此处不会自动展平。")
        notice.setWordWrap(True)
        mapping.addRow(notice)
        self.tabs.addTab(mappings, "字段映射")
        labels = QWidget()
        label_form = QFormLayout(labels)
        note = QLabel("没有真实标签时留空。外部表按完整原值进行多对一连接，不去后缀、不猜测文件对应关系。")
        note.setWordWrap(True)
        label_form.addRow(note)
        self.metadata = self.path_row(label_form, "标签 / 分组表（可选）", filter="表格 (*.csv *.xlsx)")
        self.metadata_sheet = QLineEdit()
        self.metadata_sheet.setPlaceholderText("表中有多个匹配页时必须指定；例：分组设计")
        self.join = QLineEdit()
        self.join.setPlaceholderText("例：file_name,subject_id；输入表和外部表都必须存在")
        self.target = QLineEdit()
        self.target.setPlaceholderText("真实标签列；例：condition。留空则不生成标签")
        label_form.addRow("元数据工作表", self.metadata_sheet)
        label_form.addRow("连接列", self.join)
        label_form.addRow("标签列", self.target)
        label_form.addRow(QLabel("输出：feature__ 为数值特征，meta__ 为索引/分组，target__ 为指定标签。\n导入 PY-ML 时显式选择特征和标签；不要把索引和分组当作 EEG 特征。"))
        self.tabs.addTab(labels, "标签与分组")
        self.preview_table = QTableWidget()
        self.preview_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabs.addTab(self.preview_table, "转换预览")
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("逐文件成功、失败、跳过原因会在这里显示；完整结果保存在输出目录。")
        self.tabs.addTab(self.log, "批处理结果")
        layout.addWidget(self.tabs, 1)
        self.status = QLabel("就绪。CSV / XLSX 不需要 MATLAB；MAT 需已安装且有许可的 MATLAB。")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.bar = QProgressBar()
        self.bar.setValue(0)
        layout.addWidget(self.bar)
        actions = QHBoxLayout()
        self.preview_button = QPushButton("预览转换")
        self.start_button = QPushButton("开始批处理")
        self.cancel_button = QPushButton("取消")
        self.cancel_button.setEnabled(False)
        self.open_button = QPushButton("打开输出目录")
        self.open_button.setEnabled(False)
        self.preview_button.clicked.connect(self.start_preview)
        self.start_button.clicked.connect(self.start_batch)
        self.cancel_button.clicked.connect(self.request_cancel)
        self.open_button.clicked.connect(self.open_output)
        for button in (self.preview_button, self.start_button, self.cancel_button, self.open_button):
            button.setMinimumHeight(34)
            actions.addWidget(button)
        layout.addLayout(actions)
        self.settings_group = settings
        self.mapping_widgets = (mappings, labels)

    def path_row(self, form, label, directory=False, filter="所有文件 (*)"):
        edit = QLineEdit()
        edit.setMinimumHeight(28)
        row = QHBoxLayout()
        row.addWidget(edit)
        button = QPushButton("浏览…")
        def choose():
            if directory:
                selected = QFileDialog.getExistingDirectory(self, label, edit.text())
            else:
                selected, _ = QFileDialog.getOpenFileName(self, label, edit.text(), filter)
            if selected:
                edit.setText(selected)
        button.clicked.connect(choose)
        row.addWidget(button)
        form.addRow(label, row)
        return edit

    def options(self):
        return Options(sample_columns=fields(self.samples.text()), coordinate_columns=fields(self.coordinates.text()), value_columns=fields(self.values.text()), table_path=self.table_path.text().strip(), sheet=self.sheet.text().strip(), matlab=self.matlab.text().strip(), recursive=self.recursive.isChecked(), merge=self.merge.isChecked(), metadata=self.metadata.text().strip(), metadata_sheet=self.metadata_sheet.text().strip(), join_columns=fields(self.join.text()), target=self.target.text().strip(), metadata_only=self.metadata_only.isChecked())

    def start_worker(self, operation, result_slot):
        if self.worker is not None:
            return
        self.cancel.clear()
        self.worker = Worker(operation, self.cancel, self)
        self.worker.progress.connect(self.update_progress)
        self.worker.result.connect(result_slot)
        self.worker.error.connect(self.show_error)
        self.worker.finished.connect(self.worker_finished)
        self.settings_group.setEnabled(False)
        for widget in self.mapping_widgets:
            widget.setEnabled(False)
        self.preview_button.setEnabled(False)
        self.start_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.bar.setRange(0, 0)
        self.status.setText("正在读取数据… 可以取消；MATLAB 首次启动可能需要一些时间。")
        self.worker.start()

    def start_preview(self):
        options = self.options()
        selected = self.preview_edit.text().strip()
        if not selected and (not self.input_edit.text().strip() or not self.output_edit.text().strip()):
            self.show_error("请选择预览文件，或填写输入和输出目录。")
            return
        def operation(progress):
            path = Path(selected) if selected else scan(Path(self.input_edit.text()), Path(self.output_edit.text()), options)[0]
            return preview(path, options, self.cancel)
        self.start_worker(operation, self.preview_ready)

    def start_batch(self):
        source_text, output_text = self.input_edit.text().strip(), self.output_edit.text().strip()
        if not source_text or not output_text:
            self.show_error("必须选择输入与输出目录。")
            return
        source, output, options = Path(source_text), Path(output_text), self.options()
        self.log.clear()
        self.tabs.setCurrentWidget(self.log)
        self.start_worker(lambda progress: batch(source, output, options, self.cancel, progress), self.batch_ready)

    def update_progress(self, number, total, record):
        self.bar.setRange(0, total)
        self.bar.setValue(number)
        message = f"{number}/{total} [{record['status']}] {record['source']}"
        if record.get("reason"):
            message += "\n    " + record["reason"]
        self.log.append(message)
        self.status.setText(f"已处理 {number}/{total} 个文件。")

    def preview_ready(self, result):
        item, frame = result
        self.preview_table.clear()
        self.preview_table.setRowCount(len(frame))
        self.preview_table.setColumnCount(len(frame.columns))
        self.preview_table.setHorizontalHeaderLabels(list(frame.columns))
        for row in range(len(frame)):
            for column in range(len(frame.columns)):
                self.preview_table.setItem(row, column, QTableWidgetItem(str(frame.iloc[row, column])))
        self.preview_table.resizeColumnsToContents()
        self.tabs.setCurrentWidget(self.preview_table)
        self.status.setText(f"转换预览：共 {len(item.samples)} 个样本，{len(item.features)} 个特征；显示前 30 行，尚未写出。")

    def batch_ready(self, summary):
        self.last_output = Path(summary["run_directory"])
        self.open_button.setEnabled(True)
        message = f"{'已取消' if summary['cancelled'] else '处理结束'}：成功 {summary['success']}，失败 {summary['failed']}，跳过 {summary['skipped']}，未处理 {summary['not_processed']}。"
        if summary["merge"]:
            message += f" 合并：{summary['merge']['status']}。"
            if summary["merge"].get("reason"):
                self.log.append(summary["merge"]["reason"])
            if summary["merge"].get("partial"):
                message += " 合并仅含成功文件，请查看失败清单。"
        self.log.append(message + "\n输出：" + str(self.last_output))
        self.status.setText(message)

    def show_error(self, message):
        self.status.setText(message)
        self.log.append("[错误] " + message)
        self.tabs.setCurrentWidget(self.log)

    def worker_finished(self):
        worker = self.worker
        self.worker = None
        worker.deleteLater()
        self.settings_group.setEnabled(True)
        for widget in self.mapping_widgets:
            widget.setEnabled(True)
        self.preview_button.setEnabled(True)
        self.start_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        if self.bar.maximum() == 0:
            self.bar.setRange(0, 1)
            self.bar.setValue(0)

    def request_cancel(self):
        self.cancel.set()
        self.cancel_button.setEnabled(False)
        self.status.setText("正在取消；保留已完成的输出，不发布未完成文件。")

    def open_output(self):
        if self.last_output:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.last_output)))

    def closeEvent(self, event):
        if self.worker is not None:
            self.request_cancel()
            self.status.setText("已请求取消，请等待任务结束后关闭窗口。")
            event.ignore()
        else:
            event.accept()


def create_app():
    if os.name == "nt":
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("hexiovo.PYML.HyperEEGConverter")
    app = QApplication.instance() or QApplication([])
    family = "Microsoft YaHei UI"
    if os.name == "nt":
        for filename in ("msyh.ttc", "msyhbd.ttc", "simhei.ttf"):
            path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / filename
            if path.is_file():
                font_id = QFontDatabase.addApplicationFont(str(path))
                families = QFontDatabase.applicationFontFamilies(font_id)
                if families:
                    family = families[0]
                    break
    app.setFont(QFont(family, 10))
    window = Window()
    return app, window


def main():
    app, window = create_app()
    window.show()
    return app.exec()
