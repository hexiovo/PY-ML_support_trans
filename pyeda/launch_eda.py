"""Standalone entry point for the PYEDA EDA conversion plugin."""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

from pyeda_converter import CORE_VERSION, ConversionError, ConversionOptions, convert_bundle, inspect_bundle


def _options(args: argparse.Namespace) -> ConversionOptions:
    return ConversionOptions(
        source=args.source,
        include_outcomes=args.include_outcomes,
        only_valid_records=args.only_valid_records,
        verify_manifest_hashes=not args.no_verify_hashes,
        max_record_files=args.max_record_files,
    )


def _progress(stage: str, current: int, total: int, detail: str) -> None:
    if sys.stdout is not None:
        print(f"[{stage}] {current}/{total} {detail}", flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PYEDA EDA 结果包转换为 PYML 数据表")
    parser.add_argument("--version", action="version", version=CORE_VERSION)
    parser.add_argument("--input", type=Path, help="PYEDA 结果目录")
    parser.add_argument("--output", type=Path, help="新的输出目录（必须为空）")
    parser.add_argument("--source", choices=("participant_task_role", "participant_exposure", "records"), default="participant_task_role")
    parser.add_argument("--include-outcomes", action=argparse.BooleanOptionalAction, default=False, help="导出 analysis_settings.json 明确列出的结果列")
    parser.add_argument("--only-valid-records", action=argparse.BooleanOptionalAction, default=True, help="records 模式只保留 status=valid 的行")
    parser.add_argument("--no-verify-hashes", action="store_true", help="跳过 manifest.json 中已登记源文件的哈希核对")
    parser.add_argument("--max-record-files", type=int, help="records 模式只读取前 N 个文件（调试用）")
    parser.add_argument("--inspect", action="store_true", help="只检查输入契约并输出 JSON")
    parser.add_argument("--no-open", action="store_true", help="完成后不打开输出目录")
    args = parser.parse_args(argv)
    if args.input is None:
        from pyeda_converter.gui import run_gui
        return run_gui()
    options = _options(args)
    if args.inspect:
        result = inspect_bundle(args.input, options)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "ready" else 1
    if args.output is None:
        parser.error("--input 转换时必须同时提供 --output；不带参数可启动 GUI")
    summary = convert_bundle(args.input, args.output, options, progress_callback=_progress)
    if sys.stdout is not None:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    if not args.no_open and sys.platform == "win32":
        import os
        os.startfile(str(Path(args.output).resolve()))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        location = Path(__file__).resolve().with_name("last-error.log")
        location.write_text(traceback.format_exc(), encoding="utf-8")
        print(traceback.format_exc(), file=sys.stderr)
        raise SystemExit(1)
