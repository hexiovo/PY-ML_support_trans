"""Launch the PYfNIRs conversion GUI and provide build-only checks.

The package smoke switches exercise the frozen public API without MATLAB; they
are used by ``build_pyfnirs.ps1`` before it publishes a plugin manifest.
"""
from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import sys
from typing import Sequence


def _write_report(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _package_gui_smoke(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="PYfNIRs-DataConversion --package-smoke-gui")
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        from pyfnirs_converter.__main__ import run_smoke_test

        payload = run_smoke_test()
        payload["status"] = "qt_window_smoke_passed"
        payload["core_api_checked"] = False
        _write_report(args.report, payload)
        return 0
    except Exception as exc:
        _write_report(args.report, {"status": "failed", "error": f"{type(exc).__name__}: {exc}"})
        return 1


def _package_convert_smoke(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="PYfNIRs-DataConversion --package-smoke-convert")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--selection", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--matlab", type=Path)
    args = parser.parse_args(argv)
    captured_stdout = io.StringIO()
    captured_stderr = io.StringIO()
    try:
        from pyfnirs_converter.cli import main as cli_main

        cli_args = [
            "convert",
            str(args.input),
            "--selection",
            str(args.selection),
            "--output-dir",
            str(args.output_dir),
            "--quiet-progress",
        ]
        if args.matlab is not None:
            cli_args.extend(["--matlab", str(args.matlab)])
        with redirect_stdout(captured_stdout), redirect_stderr(captured_stderr):
            return_code = cli_main(cli_args)
        raw_result = captured_stdout.getvalue().strip()
        try:
            conversion = json.loads(raw_result) if raw_result else None
        except json.JSONDecodeError:
            conversion = {"unparsed_cli_output": raw_result}
        files = conversion.get("files", []) if isinstance(conversion, dict) else []
        passed = (
            return_code == 0
            and isinstance(conversion, dict)
            and not conversion.get("cancelled", True)
            and isinstance(files, list)
            and bool(files)
            and all(isinstance(item, dict) and item.get("status") == "success" for item in files)
        )
        _write_report(
            args.report,
            {
                "status": "conversion_passed" if passed else "failed",
                "return_code": return_code,
                "input": str(args.input.resolve()),
                "selection": str(args.selection.resolve()),
                "output_dir": str(args.output_dir.resolve()),
                "conversion_result": conversion,
                "stderr": captured_stderr.getvalue(),
            },
        )
        return 0 if passed else 1
    except Exception as exc:
        _write_report(
            args.report,
            {
                "status": "failed",
                "error": f"{type(exc).__name__}: {exc}",
                "stderr": captured_stderr.getvalue(),
            },
        )
        return 1


def _record_startup_error(exc: Exception) -> None:
    location = Path(os.environ.get("APPDATA", str(Path.home()))) / "PY-ML" / "PYfNIRs" / "startup-error.log"
    try:
        location.parent.mkdir(parents=True, exist_ok=True)
        location.write_text(f"{type(exc).__name__}: {exc}\n", encoding="utf-8")
    except OSError:
        pass
    if sys.stderr is not None:
        print(f"PYfNIRs startup failed: {type(exc).__name__}: {exc}", file=sys.stderr)


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "--package-smoke-gui":
        return _package_gui_smoke(args[1:])
    if args and args[0] == "--package-smoke-convert":
        return _package_convert_smoke(args[1:])
    try:
        from pyfnirs_converter.__main__ import main as gui_main

        return gui_main(args)
    except Exception as exc:
        _record_startup_error(exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
