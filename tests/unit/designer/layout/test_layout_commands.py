"""Unit tests for designer layout command helpers."""

from __future__ import annotations

import pytest

from app.designer.layout import (
    adjust_widgets_to_default_size,
    align_widgets,
    apply_layout_to_widget,
    break_layout,
    distribute_widgets,
)
from app.designer.model import PropertyValue, WidgetNode

pytestmark = pytest.mark.unit


def test_apply_layout_moves_children_into_layout_items() -> None:
    root = WidgetNode(
        class_name="QWidget",
        object_name="rootWidget",
        children=[
            WidgetNode(class_name="QLabel", object_name="label"),
            WidgetNode(class_name="QLineEdit", object_name="lineEdit"),
        ],
    )

    apply_layout_to_widget(root, "QVBoxLayout", layout_object_name="verticalLayout")

    assert root.layout is not None
    assert root.layout.class_name == "QVBoxLayout"
    assert root.layout.object_name == "verticalLayout"
    assert len(root.layout.items) == 2
    assert root.children == []


def test_apply_layout_rejects_existing_layout() -> None:
    root = WidgetNode(class_name="QWidget", object_name="rootWidget")
    apply_layout_to_widget(root, "QVBoxLayout", layout_object_name="verticalLayout")

    with pytest.raises(ValueError, match="already has layout"):
        apply_layout_to_widget(root, "QHBoxLayout", layout_object_name="horizontalLayout")


def test_break_layout_restores_child_widgets() -> None:
    root = WidgetNode(
        class_name="QWidget",
        object_name="rootWidget",
        children=[WidgetNode(class_name="QPushButton", object_name="pushButton")],
    )
    apply_layout_to_widget(root, "QVBoxLayout", layout_object_name="verticalLayout")
    assert root.layout is not None

    break_layout(root)

    assert root.layout is None
    assert [child.object_name for child in root.children] == ["pushButton"]


def test_align_widgets_sets_non_reference_widgets_to_left_edge() -> None:
    first = WidgetNode(
        class_name="QPushButton",
        object_name="pushButton",
        properties={"geometry": PropertyValue(value_type="rect", value={"x": 16, "y": 20, "width": 80, "height": 24})},
    )
    second = WidgetNode(
        class_name="QLabel",
        object_name="label",
        properties={"geometry": PropertyValue(value_type="rect", value={"x": 64, "y": 40, "width": 90, "height": 24})},
    )

    assert align_widgets([first, second], "left") is True
    assert second.properties["geometry"].value["x"] == 16


def test_distribute_widgets_requires_three_widgets() -> None:
    first = WidgetNode(
        class_name="QPushButton",
        object_name="pushButton",
        properties={"geometry": PropertyValue(value_type="rect", value={"x": 0, "y": 0, "width": 80, "height": 24})},
    )
    second = WidgetNode(
        class_name="QLabel",
        object_name="label",
        properties={"geometry": PropertyValue(value_type="rect", value={"x": 100, "y": 0, "width": 90, "height": 24})},
    )

    assert distribute_widgets([first, second], "horizontal") is False


def test_distribute_widgets_evenly_adjusts_middle_positions() -> None:
    first = WidgetNode(
        class_name="QPushButton",
        object_name="first",
        properties={"geometry": PropertyValue(value_type="rect", value={"x": 0, "y": 0, "width": 80, "height": 24})},
    )
    middle = WidgetNode(
        class_name="QLabel",
        object_name="middle",
        properties={"geometry": PropertyValue(value_type="rect", value={"x": 10, "y": 0, "width": 90, "height": 24})},
    )
    last = WidgetNode(
        class_name="QLineEdit",
        object_name="last",
        properties={"geometry": PropertyValue(value_type="rect", value={"x": 100, "y": 0, "width": 120, "height": 24})},
    )

    assert distribute_widgets([first, middle, last], "horizontal") is True
    assert middle.properties["geometry"].value["x"] == 50


def test_adjust_widgets_to_default_size_sets_class_defaults() -> None:
    widget = WidgetNode(
        class_name="QPushButton",
        object_name="pushButton",
        properties={"geometry": PropertyValue(value_type="rect", value={"x": 20, "y": 10, "width": 400, "height": 200})},
    )

    assert adjust_widgets_to_default_size([widget]) is True
    assert widget.properties["geometry"].value["width"] == 120
    assert widget.properties["geometry"].value["height"] == 32


def test_adjust_widgets_to_default_size_uses_container_dimensions_for_groupbox() -> None:
    widget = WidgetNode(
        class_name="QGroupBox",
        object_name="groupBox",
        properties={"geometry": PropertyValue(value_type="rect", value={"x": 20, "y": 10, "width": 100, "height": 40})},
    )

    assert adjust_widgets_to_default_size([widget]) is True
    assert widget.properties["geometry"].value["width"] == 220
    assert widget.properties["geometry"].value["height"] == 140
