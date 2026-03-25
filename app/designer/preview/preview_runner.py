"""Isolated subprocess runner for custom-widget preview probes."""

from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
import sys

from PySide2.QtCore import QFile, QIODevice
from PySide2.QtUiTools import QUiLoader
from PySide2.QtWidgets import QApplication, QWidget


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Isolated Designer preview runner")
    parser.add_argument("--ui-file", required=True)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--custom-widgets-json", required=True)
    return parser.parse_args(argv)


def _resolve_module_name(header_value: str) -> str:
    normalized = header_value.strip().replace("/", ".")
    if normalized.endswith(".py"):
        normalized = normalized[:-3]
    if normalized.endswith(".h"):
        normalized = normalized[:-2]
    return normalized


def _register_custom_widgets(loader: QUiLoader, custom_widgets_payload: list[dict[str, str]]) -> None:
    for item in custom_widgets_payload:
        class_name = item.get("class_name", "").strip()
        module_header = item.get("header", "").strip()
        if not class_name or not module_header:
            continue
        module_name = _resolve_module_name(module_header)
        if not module_name:
            continue
        module = importlib.import_module(module_name)
        widget_class = getattr(module, class_name)
        if not isinstance(widget_class, type) or not issubclass(widget_class, QWidget):
            raise TypeError(f"Custom widget is not QWidget subclass: {class_name}")
        loader.registerCustomWidget(widget_class)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    project_root = Path(args.project_root).resolve()
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    payload = json.loads(args.custom_widgets_json)
    if not isinstance(payload, list):
        raise ValueError("custom widgets payload must be a JSON list")

    app = QApplication.instance() or QApplication([])
    loader = QUiLoader()
    _register_custom_widgets(loader, payload)

    ui_file = QFile(str(Path(args.ui_file).resolve()))
    if not ui_file.open(QIODevice.ReadOnly):
        raise RuntimeError("Failed to open ui file for isolated preview.")
    try:
        widget = loader.load(ui_file, None)
    finally:
        ui_file.close()
    if widget is None:
        raise RuntimeError("Isolated preview loader returned no widget.")
    widget.deleteLater()
    app.quit()
    print("ISOLATED_PREVIEW_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
