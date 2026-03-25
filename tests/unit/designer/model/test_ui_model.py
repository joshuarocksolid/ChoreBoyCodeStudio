"""Unit tests for Designer UI model contracts."""

from __future__ import annotations

import pytest

from app.designer.model import LayoutItem, LayoutNode, PropertyValue, UIModel, WidgetNode

pytestmark = pytest.mark.unit


def test_collect_object_names_includes_widget_and_layout_children() -> None:
    model = UIModel(
        form_class_name="SampleForm",
        root_widget=WidgetNode(
            class_name="QWidget",
            object_name="rootWidget",
            children=[WidgetNode(class_name="QLabel", object_name="headerLabel")],
            layout=LayoutNode(
                class_name="QVBoxLayout",
                object_name="rootLayout",
                items=[LayoutItem(widget=WidgetNode(class_name="QPushButton", object_name="submitButton"))],
            ),
        ),
    )

    assert model.collect_object_names() == ["rootWidget", "headerLabel", "submitButton"]


def test_duplicate_object_names_detected_deterministically() -> None:
    model = UIModel(
        form_class_name="DuplicateForm",
        root_widget=WidgetNode(
            class_name="QWidget",
            object_name="duplicateName",
            children=[
                WidgetNode(class_name="QLabel", object_name="duplicateName"),
                WidgetNode(class_name="QLineEdit", object_name="uniqueName"),
            ],
            properties={"windowTitle": PropertyValue(value_type="string", value="Duplicates")},
        ),
    )

    assert model.duplicate_object_names() == ["duplicateName"]


def test_widget_find_by_object_name_searches_subtree() -> None:
    root = WidgetNode(
        class_name="QWidget",
        object_name="rootWidget",
        children=[
            WidgetNode(class_name="QGroupBox", object_name="groupBox", children=[WidgetNode(class_name="QLabel", object_name="innerLabel")])
        ],
    )

    assert root.find_by_object_name("innerLabel") is not None
    assert root.find_by_object_name("missingName") is None
