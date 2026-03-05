"""Designer preview package."""

from app.designer.preview.preview_service import PreviewCompatibilityResult, load_widget_from_ui_xml, probe_ui_xml_compatibility
from app.designer.preview.preview_window import configure_preview_widget

__all__ = [
    "PreviewCompatibilityResult",
    "configure_preview_widget",
    "load_widget_from_ui_xml",
    "probe_ui_xml_compatibility",
]

