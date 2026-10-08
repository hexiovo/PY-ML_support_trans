"""Independent GUI or command-line entry. No host package dependency."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from hypereeg_converter import __version__


def main():
    parser = argparse.ArgumentParser(description="HyperEEG 正式特征表转换器")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--options", type=Path, help="Options 字段组成的 JSON 文件")
    parser.add_argument("--preview", type=Path)
    parser.add_argument("--smoke", type=Path, help="启动真实 Qt 窗口并保存截图后退出（发行验证）")
    args = parser.parse_args()
    if args.smoke:
        from hypereeg_converter.gui import create_app
        app, window = create_app()
        window.show()
        app.processEvents()
        if not window.grab().save(str(args.smoke)):
            raise OSError("无法保存窗口截图")
        window.close()
        return 0
    if args.input or args.preview:
        from hypereeg_converter.core import Options, batch, preview
        payload = json.loads(args.options.read_text(encoding="utf-8-sig")) if args.options else {}
        for key in ("sample_columns", "coordinate_columns", "value_columns", "join_columns"):
            if key in payload:
                payload[key] = tuple(payload[key])
        options = Options(**payload)
        if args.preview:
            item, frame = preview(args.preview, options)
            result = {"rows": len(item.samples), "features": len(item.features), "preview": frame.to_dict("records")}
        else:
            if args.output is None:
                parser.error("--input 必须同时提供 --output")
            result = batch(args.input, args.output, options)
        # Windowed frozen executables have no stdout; always retain batch summaries.
        if sys.stdout is not None:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return int(bool(result.get("failed") or result.get("merge", {}).get("status") == "失败")) if isinstance(result.get("merge"), dict) else int(bool(result.get("failed")))
    from hypereeg_converter.gui import main as gui_main
    return gui_main()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        import os
        import traceback
        location = Path(os.environ.get("APPDATA", str(Path.home()))) / "PY-ML" / "DataConversion" / "startup-error.log"
        if "--smoke" in sys.argv:
            location = Path(sys.argv[sys.argv.index("--smoke") + 1]).with_suffix(".error.log")
        location.parent.mkdir(parents=True, exist_ok=True)
        location.write_text(traceback.format_exc(), encoding="utf-8")
        if sys.stderr is not None:
            print(traceback.format_exc(), file=sys.stderr)
        raise SystemExit(1)
