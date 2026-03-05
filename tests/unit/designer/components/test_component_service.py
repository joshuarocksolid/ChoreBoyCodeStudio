"""Unit tests for reusable component service helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.designer.components import insert_component_widget, list_components, save_component_from_widget
from app.designer.model import WidgetNode

pytestmark = pytest.mark.unit


def test_save_and_list_components_round_trip(tmp_path: Path) -> None:
    ui_file = tmp_path / "form.ui"
    ui_file.write_text(
        (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<ui version=\"4.0\"><class>Form</class><widget class=\"QWidget\" name=\"Form\"/>"
            "<resources/><connections/></ui>\n"
        ),
        encoding="utf-8",
    )
    source_widget = WidgetNode(class_name="QPushButton", object_name="pushButton")
    descriptor = save_component_from_widget(str(ui_file.resolve()), "ButtonPart", source_widget)
    assert descriptor.name == "ButtonPart"

    listed = list_components(str(ui_file.resolve()))
    assert len(listed) == 1
    assert listed[0].name == "ButtonPart"
    assert listed[0].root_class_name == "QPushButton"


def test_insert_component_widget_appends_to_target_children(tmp_path: Path) -> None:
    ui_file = tmp_path / "form.ui"
    ui_file.write_text(
        (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<ui version=\"4.0\"><class>Form</class><widget class=\"QWidget\" name=\"Form\"/>"
            "<resources/><connections/></ui>\n"
        ),
        encoding="utf-8",
    )
    save_component_from_widget(
        str(ui_file.resolve()),
        "ButtonPart",
        WidgetNode(class_name="QPushButton", object_name="pushButton"),
    )
    target_parent = WidgetNode(class_name="QWidget", object_name="targetParent")
    inserted = insert_component_widget(
        ui_file_path=str(ui_file.resolve()),
        component_name="ButtonPart",
        target_parent=target_parent,
    )
    assert inserted.class_name == "QPushButton"
    assert len(target_parent.children) == 1
