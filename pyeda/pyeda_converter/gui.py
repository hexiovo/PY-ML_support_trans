"""Small standard-library GUI for interactive PYEDA conversion."""
from __future__ import annotations

import queue
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .core import ConversionCancelled, ConversionError, ConversionOptions, convert_bundle


def run_gui() -> int:
    app = _App()
    app.mainloop()
    return 0


class _App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("PYEDA EDA 数据转换器")
        self.geometry("820x600")
        self.minsize(720, 500)
        self.input_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.source_var = tk.StringVar(value="participant_task_role")
        self.include_outcomes = tk.BooleanVar(value=False)
        self.only_valid_records = tk.BooleanVar(value=True)
        self.verify_hashes = tk.BooleanVar(value=True)
        self.progress_var = tk.DoubleVar(value=0)
        self.stage_var = tk.StringVar(value="等待选择 PYEDA 结果目录")
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.cancel = threading.Event()
        self.worker: threading.Thread | None = None
        self._build()

    def _build(self) -> None:
        root = ttk.Frame(self, padding=14)
        root.pack(fill="both", expand=True)
        ttk.Label(root, text="输入 PYEDA 结果目录").grid(row=0, column=0, sticky="w")
        ttk.Entry(root, textvariable=self.input_var).grid(row=1, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(root, text="浏览…", command=self._choose_input).grid(row=1, column=1)
        ttk.Label(root, text="输出根目录（将创建带时间戳的新目录）").grid(row=2, column=0, sticky="w", pady=(12, 0))
        ttk.Entry(root, textvariable=self.output_var).grid(row=3, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(root, text="浏览…", command=self._choose_output).grid(row=3, column=1)
        options = ttk.LabelFrame(root, text="转换范围", padding=10)
        options.grid(row=4, column=0, columnspan=2, sticky="ew", pady=12)
        ttk.Label(options, text="来源表").grid(row=0, column=0, sticky="w")
        ttk.Combobox(options, textvariable=self.source_var, state="readonly", values=("participant_task_role", "participant_exposure", "records"), width=28).grid(row=0, column=1, sticky="w")
        ttk.Checkbutton(options, text="导出分析设置中明确列出的 outcome", variable=self.include_outcomes).grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Checkbutton(options, text="records 模式只保留 status=valid", variable=self.only_valid_records).grid(row=2, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(options, text="核对 manifest.json 中登记的源文件哈希", variable=self.verify_hashes).grid(row=3, column=0, columnspan=2, sticky="w")
        buttons = ttk.Frame(root)
        buttons.grid(row=5, column=0, columnspan=2, sticky="ew")
        self.start_button = ttk.Button(buttons, text="开始转换", command=self._start)
        self.start_button.pack(side="left")
        self.cancel_button = ttk.Button(buttons, text="取消", command=self._cancel, state="disabled")
        self.cancel_button.pack(side="left", padx=8)
        ttk.Label(root, textvariable=self.stage_var).grid(row=6, column=0, columnspan=2, sticky="w", pady=(12, 3))
        self.progress_bar = ttk.Progressbar(root, variable=self.progress_var, maximum=100)
        self.progress_bar.grid(row=7, column=0, columnspan=2, sticky="ew")
        self.log = tk.Text(root, height=18, wrap="word", state="disabled")
        self.log.grid(row=8, column=0, columnspan=2, sticky="nsew", pady=(10, 0))
        root.columnconfigure(0, weight=1)
        root.rowconfigure(8, weight=1)

    def _choose_input(self) -> None:
        selected = filedialog.askdirectory(title="选择 PYEDA 结果目录")
        if selected:
            self.input_var.set(selected)

    def _choose_output(self) -> None:
        selected = filedialog.askdirectory(title="选择输出根目录")
        if selected:
            self.output_var.set(selected)

    def _append(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _start(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        raw_source = self.input_var.get().strip()
        source = Path(raw_source)
        parent = Path(self.output_var.get().strip()) if self.output_var.get().strip() else source.parent / "converted"
        if not raw_source or not source.is_dir():
            messagebox.showerror("输入无效", "请选择存在的 PYEDA 结果目录。")
            return
        run = parent / f"PYEDA-converted-{__import__('datetime').datetime.now().strftime('%Y%m%d-%H%M%S')}-{__import__('uuid').uuid4().hex[:8]}"
        options = ConversionOptions(
            source=self.source_var.get(), include_outcomes=self.include_outcomes.get(),
            only_valid_records=self.only_valid_records.get(), verify_manifest_hashes=self.verify_hashes.get(),
        )
        self.cancel.clear()
        self.start_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.progress_var.set(0)
        self._append(f"输出目录：{run}")
        self.worker = threading.Thread(target=self._run, args=(source, run, options), daemon=True)
        self.worker.start()
        self.after(100, self._poll)

    def _run(self, source: Path, run: Path, options: ConversionOptions) -> None:
        def callback(stage: str, current: int, total: int, detail: str) -> None:
            self.events.put(("progress", (stage, current, total, detail)))
        try:
            result = convert_bundle(source, run, options, progress_callback=callback, cancel_event=self.cancel)
        except ConversionCancelled as exc:
            self.events.put(("cancelled", str(exc)))
        except Exception as exc:
            self.events.put(("error", exc))
        else:
            self.events.put(("done", result))

    def _poll(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "progress":
                    stage, current, total, detail = payload  # type: ignore[misc]
                    self.stage_var.set(f"{stage}：{detail}")
                    self.progress_var.set(100 * current / max(total, 1))
                    self._append(f"{stage} {current}/{total} {detail}")
                elif kind == "done":
                    self._finish()
                    self.stage_var.set("转换完成")
                    self._append(f"完成：{payload['output']}")
                    messagebox.showinfo("转换完成", f"已写入：\n{payload['output']}")
                elif kind == "cancelled":
                    self._finish()
                    self.stage_var.set("已取消；部分输出已标记为 cancelled")
                    self._append(str(payload))
                elif kind == "error":
                    self._finish()
                    self.stage_var.set("转换失败")
                    self._append(str(payload))
                    messagebox.showerror("转换失败", str(payload))
        except queue.Empty:
            pass
        if str(self.start_button.cget("state")) == "disabled":
            self.after(100, self._poll)

    def _cancel(self) -> None:
        self.cancel.set()
        self.stage_var.set("正在请求取消；等待当前文件收尾")

    def _finish(self) -> None:
        self.start_button.configure(state="normal")
        self.cancel_button.configure(state="disabled")
