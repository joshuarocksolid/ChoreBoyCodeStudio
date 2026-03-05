"""Property edit helpers for Designer model widgets."""

from __future__ import annotations

from app.designer.model import PropertyValue, WidgetNode
from app.designer.properties.property_schema import PropertyFieldDefinition, default_property_schema_for_class


class PropertyEditorController:
    """Applies typed property edits to `WidgetNode` instances."""

    def field_definitions_for_widget(self, widget: WidgetNode) -> list[PropertyFieldDefinition]:
        return default_property_schema_for_class(widget.class_name)

    def set_property(self, widget: WidgetNode, property_name: str, raw_value: object) -> None:
        field = self._field_for_property(widget, property_name)
        if field is None:
            raise ValueError(f"Unsupported property for {widget.class_name}: {property_name}")
        coerced_value = _coerce_value(field.value_type, raw_value)
        if property_name == "objectName":
            widget.object_name = str(coerced_value)
            return
        widget.properties[property_name] = PropertyValue(value_type=field.value_type, value=coerced_value)

    def reset_property(self, widget: WidgetNode, property_name: str) -> None:
        """Reset one property to schema default value."""
        field = self._field_for_property(widget, property_name)
        if field is None:
            raise ValueError(f"Unsupported property for {widget.class_name}: {property_name}")
        if property_name == "objectName":
            return
        if field.default_value is None:
            widget.properties.pop(property_name, None)
            return
        coerced_value = _coerce_value(field.value_type, field.default_value)
        widget.properties[property_name] = PropertyValue(value_type=field.value_type, value=coerced_value)

    def _field_for_property(self, widget: WidgetNode, property_name: str) -> PropertyFieldDefinition | None:
        for field in self.field_definitions_for_widget(widget):
            if field.name == property_name:
                return field
        return None


def _coerce_value(value_type: str, raw_value: object) -> object:
    if value_type == "string":
        return str(raw_value)
    if value_type == "bool":
        if isinstance(raw_value, bool):
            return raw_value
        if isinstance(raw_value, str):
            normalized = raw_value.strip().lower()
            return normalized in {"1", "true", "yes", "on"}
        return bool(raw_value)
    if value_type in {"number", "int"}:
        return int(raw_value)
    if value_type in {"double", "float"}:
        return float(raw_value)
    if value_type == "rect":
        if not isinstance(raw_value, dict):
            raise ValueError("Rect property value must be a dict with x,y,width,height")
        return {
            "x": int(raw_value.get("x", 0)),
            "y": int(raw_value.get("y", 0)),
            "width": int(raw_value.get("width", 0)),
            "height": int(raw_value.get("height", 0)),
        }
    return raw_value
