"""The Records picker group. Rows appear only on a form that has a data source."""

from __future__ import annotations

from typing import Any, List

from app.features.form_builder.engine.data.source import has_data_source
from app.features.form_builder.qtside.pickers.flow import Item
from app.features.form_builder.qtside.pickers.groups_ext import PickerGroup

_ROWS = (
    ("new", "New record"),
    ("save", "Save record"),
    ("delete", "Delete record"),
    ("revert", "Undo changes"),
    ("reload", "Reload"),
    ("first", "First"),
    ("previous", "Previous"),
    ("next", "Next"),
    ("last", "Last"),
    ("find", "Find"),
    ("showAll", "Show all"),
    ("refreshLookups", "Reload lookups"),
    ("addRow", "Add a line"),
    ("deleteRow", "Delete the line"),
    ("openRecord", "Open record form"),
)


def _rows(ctx: Any) -> List[Item]:
    doc = getattr(ctx, "doc", None)
    if doc is None or not has_data_source(doc):
        return []
    rows = [Item("header", "", "RECORDS", header=True)]
    rows.extend(Item("verb", verb, label) for verb, label in _ROWS)
    return rows


def register(registry: Any) -> None:
    registry.add(PickerGroup("records", 24, "Records", _rows))
