"""Unit tests for designer property editing helpers."""

from __future__ import annotations

import pytest

from app.designer.model import WidgetNode
from app.designer.properties import PropertyEditorController

pytestmark = pytest.mark.unit


def test_set_property_updates_widget_object_name() -> None:
    widget = WidgetNode(class_name="QWidget", object_name="oldName")
    controller = PropertyEditorController()

    controller.set_property(widget, "objectName", "newName")

    assert widget.object_name == "newName"


def test_set_property_coerces_bool_and_rect_values() -> None:
    widget = WidgetNode(class_name="QLineEdit", object_name="lineEdit")
    controller = PropertyEditorController()

    controller.set_property(widget, "enabled", "false")
    controller.set_property(widget, "geometry", {"x": 1, "y": 2, "width": 300, "height": 40})

    assert widget.properties["enabled"].value is False
    assert widget.properties["geometry"].value == {"x": 1, "y": 2, "width": 300, "height": 40}


def test_set_property_rejects_unknown_fields() -> None:
    widget = WidgetNode(class_name="QWidget", object_name="widget")
    controller = PropertyEditorController()

    with pytest.raises(ValueError, match="Unsupported property"):
        controller.set_property(widget, "placeholderText", "Nope")
