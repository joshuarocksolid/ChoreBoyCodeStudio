"""Designer canvas package."""

from app.designer.canvas.drop_rules import can_insert_widget, is_parent_drop_target
from app.designer.canvas.form_canvas import FormCanvas
from app.designer.canvas.guides import default_snapped_geometry, snap_to_grid, widget_icon_char
from app.designer.canvas.selection_controller import SelectionController

__all__ = [
    "FormCanvas",
    "SelectionController",
    "can_insert_widget",
    "default_snapped_geometry",
    "is_parent_drop_target",
    "snap_to_grid",
    "widget_icon_char",
]

