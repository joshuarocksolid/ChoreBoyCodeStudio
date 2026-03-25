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
