"""Designer property schema definitions."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PropertyFieldDefinition:
    """Defines one editable property field."""

    name: str
    value_type: str
    group: str
    display_label: str
    enum_values: tuple[str, ...] = ()
    default_value: object | None = None


def default_property_schema_for_class(class_name: str) -> list[PropertyFieldDefinition]:
    """Return baseline D1 property schema for the given widget class."""
    common = [
        PropertyFieldDefinition("objectName", "string", "Metadata", "Object Name"),
        PropertyFieldDefinition(
            "geometry",
            "rect",
            "Geometry",
            "Geometry",
            default_value={"x": 0, "y": 0, "width": 640, "height": 480},
        ),
        PropertyFieldDefinition(
            "minimumSize",
            "size",
            "Geometry",
            "Minimum Size",
            default_value={"width": 0, "height": 0},
        ),
        PropertyFieldDefinition(
            "maximumSize",
            "size",
            "Geometry",
            "Maximum Size",
            default_value={"width": 16777215, "height": 16777215},
        ),
        PropertyFieldDefinition(
            "sizePolicy",
            "sizepolicy",
            "Layout",
            "Size Policy",
            default_value={"hsizetype": "Preferred", "vsizetype": "Preferred", "horstretch": 0, "verstretch": 0},
        ),
        PropertyFieldDefinition("layoutSpacing", "int", "Layout", "Layout Spacing", default_value=6),
        PropertyFieldDefinition(
            "contentsMargins",
            "margins",
            "Layout",
            "Contents Margins",
            default_value={"left": 9, "top": 9, "right": 9, "bottom": 9},
        ),
        PropertyFieldDefinition("windowTitle", "string", "Appearance", "Window Title", default_value=""),
        PropertyFieldDefinition("styleSheet", "string", "Appearance", "Style Sheet", default_value=""),
        PropertyFieldDefinition("cursor", "cursor", "Appearance", "Cursor", default_value="ArrowCursor"),
        PropertyFieldDefinition(
            "font",
            "font",
            "Appearance",
            "Font",
            default_value={"family": "", "pointsize": 10, "bold": False, "italic": False},
        ),
        PropertyFieldDefinition(
            "palette",
            "palette",
            "Appearance",
            "Palette",
            default_value={},
        ),
        PropertyFieldDefinition("windowIcon", "iconset", "Appearance", "Window Icon", default_value=""),
        PropertyFieldDefinition("enabled", "bool", "Behavior", "Enabled", default_value=True),
        PropertyFieldDefinition("toolTip", "string", "Behavior", "Tool Tip", default_value=""),
    ]
    text_like = {"QLabel", "QPushButton", "QCheckBox", "QRadioButton", "QGroupBox"}
    if class_name in text_like:
        common.append(PropertyFieldDefinition("text", "string", "Appearance", "Text", default_value=""))
    if class_name == "QLabel":
        common.append(PropertyFieldDefinition("buddy", "cstring", "Behavior", "Buddy", default_value=""))
    if class_name in {"QPushButton", "QToolButton"}:
        common.append(PropertyFieldDefinition("icon", "iconset", "Appearance", "Icon", default_value=""))
    if class_name == "QGroupBox":
        common.append(PropertyFieldDefinition("title", "string", "Appearance", "Title", default_value=""))
    if class_name == "QLineEdit":
        common.append(
            PropertyFieldDefinition("placeholderText", "string", "Behavior", "Placeholder Text", default_value="")
        )
    if class_name in {"QCheckBox", "QRadioButton"}:
        common.append(PropertyFieldDefinition("checked", "bool", "Behavior", "Checked", default_value=False))
    return common
