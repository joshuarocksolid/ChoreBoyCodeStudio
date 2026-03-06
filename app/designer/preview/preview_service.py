"""Preview and compatibility checks for Designer `.ui` models."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Sequence

from PySide2.QtCore import QFile, QIODevice
from PySide2.QtUiTools import QUiLoader
from PySide2.QtWidgets import QWidget

from app.designer.preview.custom_widget_registry import CustomWidgetPreviewEntry


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


def probe_ui_xml_compatibility_isolated(
    ui_xml: str,
    *,
    project_root: str,
    custom_widgets: Sequence[CustomWidgetPreviewEntry],
    python_executable: str | None = None,
) -> PreviewCompatibilityResult:
    """Probe compatibility in isolated subprocess for custom-widget forms."""
    payload = [
        {
            "class_name": item.class_name,
            "header": item.header,
            "extends": item.extends,
        }
        for item in custom_widgets
    ]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".ui", delete=False, encoding="utf-8") as handle:
        handle.write(ui_xml)
        temp_path = Path(handle.name)
    command = [
        python_executable or sys.executable,
        "-m",
        "app.designer.preview.preview_runner",
        "--ui-file",
        str(temp_path),
        "--project-root",
        project_root,
        "--custom-widgets-json",
        json.dumps(payload),
    ]
    env = os.environ.copy()
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
    finally:
        try:
            temp_path.unlink()
        except OSError:
            pass
    if completed.returncode != 0:
        details = (completed.stderr or completed.stdout or "").strip()
        return PreviewCompatibilityResult(
            is_compatible=False,
            message=f"Isolated preview failed: {details or 'runner exited with non-zero status.'}",
        )
    if "ISOLATED_PREVIEW_OK" not in completed.stdout:
        return PreviewCompatibilityResult(
            is_compatible=False,
            message="Isolated preview failed: success marker missing from runner output.",
        )
    return PreviewCompatibilityResult(
        is_compatible=True,
        message="Isolated preview compatibility check passed.",
    )
