"""Where inserted or moved content goes (CONTRACTS.md section 3.4).

Placements use visual terms (layout index, grid cell, form row). The planner
turns them into InsertNodeOp/MoveNodeOp indexes. Indexes here are "before the
move": for a move within the same list, ``index`` is the position in the list
as the user saw it before the drag, and the planner adjusts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional, Union

from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.ui4.values import RectValue


@dataclass(frozen=True)
class InBoxLayout:
    """Item position in a box layout (0..count). A form layout treats the index as an insert of one row per item."""

    layout: NodeId
    index: int


@dataclass(frozen=True)
class InGridCell:
    """A QGridLayout cell. ``mode``:
    ``cell``: put the content in (row, column); the cell must be empty or hold
    only the moved node itself; other items never move (pain 21).
    ``insert_row``/``insert_column``: shift every item at or after ``row``/``column``
    down/right by one first, then place.
    """

    layout: NodeId
    row: int
    column: int
    rowspan: int = 1
    colspan: int = 1
    mode: Literal["cell", "insert_row", "insert_column"] = "cell"


@dataclass(frozen=True)
class InFormRow:
    """A QFormLayout row. ``role``: ``label`` (column 0), ``field`` (column 1),
    ``spanning`` (column 0, colspan 2). ``insert_row`` shifts every row at or
    below ``row`` down by one per placed item. Without it, an occupied cell is
    refused."""

    layout: NodeId
    row: int
    role: Literal["label", "field", "spanning"]
    insert_row: bool = False


@dataclass(frozen=True)
class InContainer:
    """A direct child of a widget without a layout, or a page/pane of a
    page container (QTabWidget, QStackedWidget, QToolBox, QSplitter,
    QScrollArea's single child, QWizard pages, QMdiArea subwindows).
    ``index`` 0..count. ``geometry`` is written as the ``geometry`` property for
    free-floating children of a widget without a layout."""

    widget: NodeId
    index: int
    geometry: Optional[RectValue] = None


@dataclass(frozen=True)
class AsMainWindowPart:
    """A QMainWindow part: ``central`` (replaces nothing; only when absent),
    ``menubar``, ``statusbar``, ``toolbar``, ``dock``. ``area`` is the
    ``toolBarArea``/``dockWidgetArea`` enum text; ``break_before`` writes
    ``toolBarBreak``."""

    main_window: NodeId
    part: Literal["central", "menubar", "statusbar", "toolbar", "dock"]
    area: Optional[str] = None
    break_before: bool = False


@dataclass(frozen=True)
class InActionList:
    """An ``<addaction>`` position in a QMenu, QMenuBar or QToolBar (0..count)."""

    widget: NodeId
    index: int


Placement = Union[InBoxLayout, InGridCell, InFormRow, InContainer, AsMainWindowPart, InActionList]
