"""Start the standalone converter window or run its offscreen Qt smoke check."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Sequence


def _arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PYfNIRs → PY-ML 中文批量转换窗口")
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="在 offscreen Qt 环境中启动并抓取窗口状态，不调用转换核心。",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="--smoke 的别名，供自动化检查窗口启动。",
    )
    return parser.parse_args(argv)


def run_smoke_test() -> dict[str, object]:
    """Exercise a real Qt event loop and capture the constructed window."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from .gui import ConversionWindow

    application = QApplication.instance() or QApplication(["pyfnirs-converter-smoke"])
    window = ConversionWindow()
    window.show()
    captured: dict[str, object] = {}

    def capture_and_quit() -> None:
        application.processEvents()
        image = window.grab().toImage()
        snapshot = window.smoke_snapshot()
        if image.isNull() or image.width() <= 0 or image.height() <= 0:
            captured["error"] = "Qt widget grab did not return a rendered image."
        else:
            captured.update(snapshot)
            captured["rendered_size"] = [image.width(), image.height()]
        application.quit()

    QTimer.singleShot(0, capture_and_quit)
    application.exec()
    window.close()
    if "error" in captured:
        raise RuntimeError(str(captured["error"]))
    return captured


def main(argv: Sequence[str] | None = None) -> int:
    args = _arguments(argv)
    if args.smoke or args.self_test:
        try:
            report = run_smoke_test()
        except Exception as exc:
            print(json.dumps({"status": "failed", "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
            return 1
        report["status"] = "qt_window_smoke_passed"
        report["core_api_checked"] = False
        print(json.dumps(report, ensure_ascii=False))
        return 0

    from PySide6.QtWidgets import QApplication

    from .gui import ConversionWindow

    application = QApplication.instance() or QApplication(sys.argv[:1])
    window = ConversionWindow()
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
