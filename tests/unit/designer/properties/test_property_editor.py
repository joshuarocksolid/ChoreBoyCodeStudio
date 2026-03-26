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


def test_reset_property_applies_schema_default() -> None:
    widget = WidgetNode(class_name="QCheckBox", object_name="checkBox")
    controller = PropertyEditorController()
    controller.set_property(widget, "checked", True)
    assert widget.properties["checked"].value is True

    controller.reset_property(widget, "checked")

    assert widget.properties["checked"].value is False


def test_set_property_supports_iconset_field() -> None:
    widget = WidgetNode(class_name="QPushButton", object_name="pushButton")
    controller = PropertyEditorController()

    controller.set_property(widget, "icon", "icons/run.png")

    assert widget.properties["icon"].value_type == "iconset"
    assert widget.properties["icon"].value == "icons/run.png"


def test_set_property_supports_layout_and_sizing_fields() -> None:
    widget = WidgetNode(class_name="QWidget", object_name="widget")
    controller = PropertyEditorController()

    controller.set_property(widget, "minimumSize", {"x": 12, "y": 18, "width": 120, "height": 48})
    controller.set_property(widget, "maximumSize", {"x": 0, "y": 0, "width": 640, "height": 480})
    controller.set_property(widget, "sizePolicy", "Preferred, Expanding")
    controller.set_property(widget, "layoutSpacing", 14)

    assert widget.properties["minimumSize"].value_type == "size"
    assert widget.properties["minimumSize"].value["width"] == 120
    assert widget.properties["maximumSize"].value_type == "size"
    assert widget.properties["maximumSize"].value["height"] == 480
    assert widget.properties["sizePolicy"].value_type == "sizepolicy"
    assert widget.properties["sizePolicy"].value == {
        "hsizetype": "Preferred",
        "vsizetype": "Expanding",
        "horstretch": 0,
        "verstretch": 0,
    }
    assert widget.properties["layoutSpacing"].value_type == "int"
    assert widget.properties["layoutSpacing"].value == 14


def test_reset_property_restores_layout_and_sizing_defaults() -> None:
    widget = WidgetNode(class_name="QWidget", object_name="widget")
    controller = PropertyEditorController()

    controller.set_property(widget, "layoutSpacing", 20)
    controller.reset_property(widget, "layoutSpacing")

    assert widget.properties["layoutSpacing"].value == 6


def test_set_property_rejects_invalid_rect_shape() -> None:
    widget = WidgetNode(class_name="QWidget", object_name="widget")
    controller = PropertyEditorController()

    with pytest.raises(ValueError, match="Size property value must be a dict"):
        controller.set_property(widget, "minimumSize", "128x64")
