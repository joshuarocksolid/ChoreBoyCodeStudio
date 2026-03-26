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

ISOLATED_PREVIEW_TIMEOUT_SECONDS = 20.0
_FREECAD_EXECUTABLE_NAMES = {"AppRun", "freecad", "FreeCAD"}


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
    runtime_executable = python_executable or sys.executable
    command = _build_isolated_preview_command(
        runtime_executable=runtime_executable,
        ui_file_path=str(temp_path),
        project_root=project_root,
        custom_widgets_json=json.dumps(payload),
    )
    env = os.environ.copy()
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    completed: subprocess.CompletedProcess[str] | None = None
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            env=env,
            timeout=ISOLATED_PREVIEW_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return PreviewCompatibilityResult(
            is_compatible=False,
            message=(
                "Isolated preview failed: runner timed out after "
                f"{ISOLATED_PREVIEW_TIMEOUT_SECONDS:.0f}s using runtime "
                f"'{Path(runtime_executable).name or runtime_executable}'."
            ),
        )
    except OSError as exc:
        return PreviewCompatibilityResult(
            is_compatible=False,
            message=f"Isolated preview failed: unable to launch runner ({exc}).",
        )
    finally:
        try:
            temp_path.unlink()
        except OSError:
            pass
    assert completed is not None
    if completed.returncode != 0:
        details = (completed.stderr or completed.stdout or "").strip()
        return PreviewCompatibilityResult(
            is_compatible=False,
            message=f"Isolated preview failed: {details or 'runner exited with non-zero status.'}",
        )
    marker_present = "ISOLATED_PREVIEW_OK" in completed.stdout
    freecad_runtime = _is_freecad_runtime(runtime_executable)
    if not marker_present and not freecad_runtime:
        return PreviewCompatibilityResult(
            is_compatible=False,
            message="Isolated preview failed: success marker missing from runner output.",
        )
    return PreviewCompatibilityResult(
        is_compatible=True,
        message="Isolated preview compatibility check passed.",
    )


def _build_isolated_preview_command(
    *,
    runtime_executable: str,
    ui_file_path: str,
    project_root: str,
    custom_widgets_json: str,
) -> list[str]:
    args = [
        "preview_runner",
        "--ui-file",
        ui_file_path,
        "--project-root",
        project_root,
        "--custom-widgets-json",
        custom_widgets_json,
    ]
    if _is_freecad_runtime(runtime_executable):
        app_root = str(Path(__file__).resolve().parents[3])
        payload = (
            "import runpy, sys;"
            f"sys.path.insert(0, {app_root!r});"
            f"sys.argv={args!r};"
            "runpy.run_module('app.designer.preview.preview_runner', run_name='__main__')"
        )
        return [runtime_executable, "-c", payload]
    return [
        runtime_executable,
        "-m",
        "app.designer.preview.preview_runner",
        "--ui-file",
        ui_file_path,
        "--project-root",
        project_root,
        "--custom-widgets-json",
        custom_widgets_json,
    ]


def _is_freecad_runtime(runtime_executable: str) -> bool:
    runtime_path = Path(runtime_executable)
    return runtime_path.name in _FREECAD_EXECUTABLE_NAMES or runtime_path.suffix == ".AppImage"
