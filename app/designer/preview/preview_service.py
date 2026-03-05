"""Preview and compatibility checks for Designer `.ui` models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tempfile

from PySide2.QtCore import QFile, QIODevice
from PySide2.QtUiTools import QUiLoader
from PySide2.QtWidgets import QWidget


@dataclass(frozen=True)
class PreviewCompatibilityResult:
    """Compatibility probe result payload."""

    is_compatible: bool
    message: str


def load_widget_from_ui_xml(ui_xml: str) -> QWidget:
    """Load QWidget from ui XML payload using QUiLoader."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".ui", delete=False, encoding="utf-8") as handle:
        handle.write(ui_xml)
        temp_path = Path(handle.name)
    loader = QUiLoader()
    ui_file = QFile(str(temp_path))
    try:
        if not ui_file.open(QIODevice.ReadOnly):
            raise ValueError(f"Failed to open temporary .ui file: {temp_path}")
        widget = loader.load(ui_file, None)
        if widget is None:
            raise ValueError("QUiLoader returned no widget for the provided form.")
        return widget
    finally:
        ui_file.close()
        try:
            temp_path.unlink()
        except OSError:
            pass


def probe_ui_xml_compatibility(ui_xml: str) -> PreviewCompatibilityResult:
    """Return compatibility probe result using QUiLoader parse/load path."""
    try:
        widget = load_widget_from_ui_xml(ui_xml)
    except Exception as exc:
        return PreviewCompatibilityResult(
            is_compatible=False,
            message=f"QUiLoader compatibility failed: {exc}",
        )
    widget.deleteLater()
    return PreviewCompatibilityResult(
        is_compatible=True,
        message="QUiLoader compatibility check passed.",
    )
