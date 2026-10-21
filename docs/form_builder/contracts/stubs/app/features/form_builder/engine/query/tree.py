"""Read-only query helpers and layout math (CONTRACTS.md section 2.8).

Pure functions of a document. None mutates. Each states its complexity.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.ui4.document import UiDocument


@dataclass(frozen=True)
class GridCell:
    item: NodeId
    row: int
    column: int
    rowspan: int
    colspan: int


@dataclass(frozen=True)
class GridShape:
    """Occupancy of a QGridLayout or QFormLayout. ``rows``/``columns`` are the
    extents (max row+span). ``empty`` lists unoccupied (row, column) cells inside
    the extents, row-major."""

    rows: int
    columns: int
    cells: Tuple[GridCell, ...]
    empty: Tuple[Tuple[int, int], ...]
    overlaps: Tuple[Tuple[NodeId, NodeId], ...]


def grid_shape(doc: UiDocument, layout_id: NodeId) -> GridShape:
    """O(items)."""
    ...


def next_free_cell(doc: UiDocument, layout_id: NodeId, *, columns_hint: int = 2) -> Tuple[int, int, str]:
    """Where "the next drop fills the next cell" goes: for a form layout the next
    row's free role (label first); for a grid the first empty cell in row-major
    order, else a new row at column 0 when the last row is full. Returns
    (row, column, role) with role "label"/"field"/"cell". O(items)."""
    ...


def form_rows(doc: UiDocument, layout_id: NodeId) -> Tuple[Tuple[Optional[NodeId], Optional[NodeId], Optional[NodeId]], ...]:
    """QFormLayout rows as (label item, field item, spanning item). O(items)."""
    ...


def visual_children(doc: UiDocument, widget_id: NodeId) -> Tuple[NodeId, ...]:
    """Layout contents in layout order (widgets, spacers, nested layouts), or the
    direct child widgets when there is no layout. O(children)."""
    ...


def reading_order(doc: UiDocument) -> Tuple[str, ...]:
    """Focusable input widget names in visual reading order (what Qt's default
    tab order follows for a laid-out form). O(form)."""
    ...


def effective_tab_order(doc: UiDocument) -> Tuple[str, ...]:
    """``<tabstops>`` when present (names that no longer exist are skipped),
    else ``reading_order``. O(form)."""
    ...


def splice_tab_order(order: Tuple[str, ...], reading: Tuple[str, ...], new_names: Tuple[str, ...]) -> Tuple[str, ...]:
    """Insert newly added inputs into a saved order where they sit in reading
    order (spike rule, kept). Pure. O(n)."""
    ...


def child_stack_order(doc: UiDocument, parent_id: NodeId) -> Tuple[str, ...]:
    """Bottom-to-top stacking of a parent's direct child widgets: the ``zorder``
    field filtered to existing children, followed by children it does not list,
    in document order (pain 24: built from the real child list). O(children)."""
    ...


def references_to(doc: UiDocument, name: str) -> Tuple[Tuple[NodeId, str], ...]:
    """Native references to ``name``: (owner id, where) with where one of
    ``buddy``, ``tabstop``, ``zorder``, ``addaction``, ``connection.sender``,
    ``connection.receiver``, ``action.menu``, ``buttonGroup``. Logic references
    come from RenameParticipants. O(form) scan; budget 3 ms at 1000 widgets."""
    ...


def page_children(doc: UiDocument, widget_id: NodeId) -> Tuple[NodeId, ...]:
    """Pages of a page container in page order. O(children)."""
    ...


def is_container(doc: UiDocument, widget_id: NodeId) -> bool:
    """Can hold dropped widgets: has a layout, or its class (or custom widget
    ``extends``) is flagged ``container`` in the class table, or a custom widget
    declares ``<container>1</container>``. O(1)."""
    ...


def form_kind(doc: UiDocument) -> str:
    """"main_window", "dialog", "wizard", "widget" or "other" from the root's
    effective class. O(1)."""
    ...
