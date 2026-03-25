"""Deterministic `.ui` formatter helpers."""

from __future__ import annotations

from app.designer.io.ui_reader import read_ui_string
from app.designer.io.ui_writer import write_ui_string


def format_ui_xml(source: str) -> str:
    """Normalize `.ui` XML using canonical model reader/writer pipeline."""
    model = read_ui_string(source)
    return write_ui_string(model)
