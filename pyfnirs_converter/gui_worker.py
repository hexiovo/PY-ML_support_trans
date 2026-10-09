"""Background API calls used by the standalone Qt window."""

from __future__ import annotations

from pathlib import Path
import threading
from typing import Literal

from PySide6.QtCore import QThread, Signal

from . import api


WorkerAction = Literal["inspect", "preview", "batch"]


class ApiWorker(QThread):
    """Run one public converter API call without blocking the UI thread."""

    completed = Signal(str, object)
    failed = Signal(str, str)
    progress = Signal(object)

    def __init__(
        self,
        action: WorkerAction,
        *,
        path: Path | None = None,
        source_adapter_id: str | None = None,
        matlab_executable: Path | None = None,
        selection: api.ConversionSelection | None = None,
        request: api.BatchRequest | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.action = action
        self.path = path
        self.source_adapter_id = source_adapter_id
        self.matlab_executable = matlab_executable
        self.selection = selection
        self.request = request
        self.cancel_event = threading.Event()

    def cancel(self) -> None:
        """Ask a running batch to stop cooperatively."""
        self.cancel_event.set()

    def run(self) -> None:
        try:
            if self.action == "inspect":
                if self.path is None:
                    raise ValueError("检查来源时必须指定文件路径。")
                result = api.inspect_source(
                    self.path,
                    source_adapter_id=self.source_adapter_id,
                    matlab_executable=self.matlab_executable,
                )
            elif self.action == "preview":
                if self.path is None or self.selection is None:
                    raise ValueError("预览转换时必须指定来源文件和映射选择。")
                result = api.preview_conversion(
                    self.path,
                    self.selection,
                    matlab_executable=self.matlab_executable,
                )
            elif self.action == "batch":
                if self.request is None:
                    raise ValueError("批量转换时必须指定批处理请求。")
                result = api.convert_batch(
                    self.request,
                    progress_callback=self.progress.emit,
                    cancel_event=self.cancel_event,
                )
            else:  # pragma: no cover - guarded by the UI and type checker
                raise ValueError(f"未知后台任务：{self.action}")
            self.completed.emit(self.action, result)
        except Exception as exc:  # the API error is reported to the relevant UI panel
            self.failed.emit(self.action, f"{type(exc).__name__}: {exc}")


__all__ = ["ApiWorker", "WorkerAction"]
