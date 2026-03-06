"""Integration tests for isolated custom-widget preview runner."""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.designer.preview import CustomWidgetPreviewEntry, probe_ui_xml_compatibility_isolated

pytestmark = pytest.mark.integration


def test_isolated_preview_runner_loads_promoted_custom_widget(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    (project_root / "fancy_widget.py").write_text(
        (
            "from PySide2.QtWidgets import QWidget\n"
            "class FancyWidget(QWidget):\n"
            "    pass\n"
        ),
        encoding="utf-8",
    )
    ui_xml = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
        "<ui version=\"4.0\">"
        "<class>Form</class>"
        "<widget class=\"QWidget\" name=\"Form\">"
        "<widget class=\"FancyWidget\" name=\"fancyWidget\"/>"
        "</widget>"
        "<customwidgets><customwidget><class>FancyWidget</class><extends>QWidget</extends>"
        "<header>fancy_widget</header></customwidget></customwidgets>"
        "<resources/><connections/>"
        "</ui>\n"
    )
    result = probe_ui_xml_compatibility_isolated(
        ui_xml,
        project_root=str(project_root.resolve()),
        custom_widgets=[CustomWidgetPreviewEntry(class_name="FancyWidget", header="fancy_widget", extends="QWidget")],
        python_executable=sys.executable,
    )
    assert result.is_compatible is True


def test_isolated_preview_runner_reports_missing_custom_widget_module(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    ui_xml = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
        "<ui version=\"4.0\">"
        "<class>Form</class>"
        "<widget class=\"QWidget\" name=\"Form\">"
        "<widget class=\"FancyWidget\" name=\"fancyWidget\"/>"
        "</widget>"
        "<customwidgets><customwidget><class>FancyWidget</class><extends>QWidget</extends>"
        "<header>missing_module</header></customwidget></customwidgets>"
        "<resources/><connections/>"
        "</ui>\n"
    )
    result = probe_ui_xml_compatibility_isolated(
        ui_xml,
        project_root=str(project_root.resolve()),
        custom_widgets=[CustomWidgetPreviewEntry(class_name="FancyWidget", header="missing_module", extends="QWidget")],
        python_executable=sys.executable,
    )
    assert result.is_compatible is False
    assert "missing_module" in result.message
