"""Outline panel package."""

from app.shell.outline.outline_icons import clear_icon_caches
from app.shell.outline.outline_header import _OutlineHeaderBar
from app.shell.outline.outline_panel import OutlinePanel
from app.shell.outline.outline_tree import (
    SORT_CATEGORY,
    SORT_NAME,
    SORT_POSITION,
    _OutlineTreeWidget,
)

__all__ = [
    "OutlinePanel",
    "SORT_CATEGORY",
    "SORT_NAME",
    "SORT_POSITION",
    "_OutlineHeaderBar",
    "_OutlineTreeWidget",
    "clear_icon_caches",
]
