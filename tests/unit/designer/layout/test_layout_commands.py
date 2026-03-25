"""Unit tests for designer layout command helpers."""

from __future__ import annotations

import pytest

from app.designer.layout import apply_layout_to_widget, break_layout
from app.designer.model import WidgetNode

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
