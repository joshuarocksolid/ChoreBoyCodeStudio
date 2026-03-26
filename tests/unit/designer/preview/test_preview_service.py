"""Unit tests for designer preview service contracts."""

from __future__ import annotations

import subprocess

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)
pytest.importorskip("PySide2.QtUiTools", exc_type=ImportError)

from PySide2.QtWidgets import QApplication

from app.designer.preview import (
    CustomWidgetPreviewEntry,
    load_widget_from_ui_xml,
    probe_ui_xml_compatibility,
    probe_ui_xml_compatibility_isolated,
)
from app.designer.preview.preview_service import (
    ISOLATED_PREVIEW_TIMEOUT_SECONDS,
    _build_isolated_preview_command,
)

pytestmark = pytest.mark.unit

_VALID_UI = (
    "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
    "<ui version=\"4.0\"><class>PreviewForm</class>"
    "<widget class=\"QWidget\" name=\"PreviewForm\"/>"
    "<resources/><connections/></ui>\n"
)


@pytest.fixture(scope="module", autouse=True)
def _ensure_qapp():  # type: ignore[no-untyped-def]
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_probe_ui_xml_compatibility_passes_for_valid_ui() -> None:
    result = probe_ui_xml_compatibility(_VALID_UI)
    assert result.is_compatible is True


def test_probe_ui_xml_compatibility_fails_for_invalid_ui() -> None:
    result = probe_ui_xml_compatibility("<ui><broken></ui>")
    assert result.is_compatible is False


def test_load_widget_from_ui_xml_returns_qwidget_instance() -> None:
    widget = load_widget_from_ui_xml(_VALID_UI)
    assert widget.objectName() == "PreviewForm"
    widget.deleteLater()


def test_probe_ui_xml_compatibility_isolated_reports_success(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="ISOLATED_PREVIEW_OK", stderr="")

    monkeypatch.setattr("app.designer.preview.preview_service.subprocess.run", _fake_run)
    result = probe_ui_xml_compatibility_isolated(
        _VALID_UI,
        project_root="/tmp/project",
        custom_widgets=[CustomWidgetPreviewEntry(class_name="FancyWidget", header="fancy_widget", extends="QWidget")],
        python_executable="python3",
    )
    assert result.is_compatible is True


def test_probe_ui_xml_compatibility_isolated_reports_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        return subprocess.CompletedProcess(args=args, returncode=1, stdout="", stderr="import failure")

    monkeypatch.setattr("app.designer.preview.preview_service.subprocess.run", _fake_run)
    result = probe_ui_xml_compatibility_isolated(
        _VALID_UI,
        project_root="/tmp/project",
        custom_widgets=[CustomWidgetPreviewEntry(class_name="FancyWidget", header="fancy_widget", extends="QWidget")],
    )
    assert result.is_compatible is False
    assert "import failure" in result.message


def test_probe_ui_xml_compatibility_isolated_passes_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    seen_timeout: list[float | None] = []

    def _fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        seen_timeout.append(kwargs.get("timeout"))
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="ISOLATED_PREVIEW_OK", stderr="")

    monkeypatch.setattr("app.designer.preview.preview_service.subprocess.run", _fake_run)
    result = probe_ui_xml_compatibility_isolated(
        _VALID_UI,
        project_root="/tmp/project",
        custom_widgets=[],
    )
    assert result.is_compatible is True
    assert seen_timeout == [ISOLATED_PREVIEW_TIMEOUT_SECONDS]


def test_probe_ui_xml_compatibility_isolated_reports_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=kwargs.get("timeout", 0))

    monkeypatch.setattr("app.designer.preview.preview_service.subprocess.run", _fake_run)
    result = probe_ui_xml_compatibility_isolated(
        _VALID_UI,
        project_root="/tmp/project",
        custom_widgets=[],
    )
    assert result.is_compatible is False
    assert "timed out" in result.message.lower()


def test_build_isolated_preview_command_uses_runpy_for_freecad_runtime() -> None:
    command = _build_isolated_preview_command(
        runtime_executable="/opt/freecad/AppRun",
        ui_file_path="/tmp/form.ui",
        project_root="/tmp/project",
        custom_widgets_json="[]",
    )
    assert command[0] == "/opt/freecad/AppRun"
    assert command[1] == "-c"
    assert "runpy.run_module('app.designer.preview.preview_runner'" in command[2]


def test_build_isolated_preview_command_uses_module_flag_for_python_runtime() -> None:
    command = _build_isolated_preview_command(
        runtime_executable="/usr/bin/python3",
        ui_file_path="/tmp/form.ui",
        project_root="/tmp/project",
        custom_widgets_json="[]",
    )
    assert command[:3] == ["/usr/bin/python3", "-m", "app.designer.preview.preview_runner"]
