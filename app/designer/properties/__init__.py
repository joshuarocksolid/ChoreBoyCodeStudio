"""Designer properties package."""

from app.designer.properties.property_editor import PropertyEditorController
from app.designer.properties.property_editor_panel import PropertyEditorPanel
from app.designer.properties.property_schema import PropertyFieldDefinition, default_property_schema_for_class

__all__ = ["PropertyEditorController", "PropertyEditorPanel", "PropertyFieldDefinition", "default_property_schema_for_class"]

