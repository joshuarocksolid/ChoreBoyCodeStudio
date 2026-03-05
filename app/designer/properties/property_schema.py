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


def default_property_schema_for_class(class_name: str) -> list[PropertyFieldDefinition]:
    """Return baseline D1 property schema for the given widget class."""
    common = [
        PropertyFieldDefinition("objectName", "string", "Metadata", "Object Name"),
        PropertyFieldDefinition("geometry", "rect", "Geometry", "Geometry"),
        PropertyFieldDefinition("enabled", "bool", "Behavior", "Enabled"),
        PropertyFieldDefinition("toolTip", "string", "Behavior", "Tool Tip"),
    ]
    text_like = {"QLabel", "QPushButton", "QCheckBox", "QRadioButton", "QGroupBox"}
    if class_name in text_like:
        common.append(PropertyFieldDefinition("text", "string", "Appearance", "Text"))
    if class_name == "QGroupBox":
        common.append(PropertyFieldDefinition("title", "string", "Appearance", "Title"))
    if class_name == "QLineEdit":
        common.append(PropertyFieldDefinition("placeholderText", "string", "Behavior", "Placeholder Text"))
    if class_name in {"QCheckBox", "QRadioButton"}:
        common.append(PropertyFieldDefinition("checked", "bool", "Behavior", "Checked"))
    return common
