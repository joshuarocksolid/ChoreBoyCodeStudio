"""Parent/child drop validation rules for Designer canvas insertions."""

from __future__ import annotations


_CONTAINER_CLASSES = {
    "QWidget",
    "QFrame",
    "QGroupBox",
    "QDialog",
    "QMainWindow",
    "QTabWidget",
    "QScrollArea",
    "QStackedWidget",
    "QSplitter",
}


def is_parent_drop_target(parent_class_name: str) -> bool:
    """Return whether the parent class can accept child widgets."""
    return parent_class_name in _CONTAINER_CLASSES


def can_insert_widget(
    *,
    parent_class_name: str,
    child_class_name: str,
    is_layout_item: bool,
    parent_has_layout: bool,
) -> bool:
    """Return whether a palette item may be inserted under parent widget."""
    if not is_parent_drop_target(parent_class_name):
        return False
    if is_layout_item:
        return parent_has_layout
    if child_class_name == "QMainWindow" and parent_class_name != "QWidget":
        return False
    return True
