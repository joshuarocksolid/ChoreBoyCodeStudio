"""Designer preview package."""

from app.designer.preview.preview_service import PreviewCompatibilityResult, load_widget_from_ui_xml, probe_ui_xml_compatibility
from app.designer.preview.preview_window import configure_preview_widget
from app.designer.preview.custom_widget_registry import (
    CustomWidgetPreviewEntry,
    PreviewSafetyDecision,
    build_preview_safety_decision,
    preview_registry_from_model,
    promoted_class_names,
    requires_isolated_preview,
)

__all__ = [
    "PreviewCompatibilityResult",
    "CustomWidgetPreviewEntry",
    "PreviewSafetyDecision",
    "build_preview_safety_decision",
    "configure_preview_widget",
    "load_widget_from_ui_xml",
    "preview_registry_from_model",
    "promoted_class_names",
    "probe_ui_xml_compatibility",
    "requires_isolated_preview",
]

