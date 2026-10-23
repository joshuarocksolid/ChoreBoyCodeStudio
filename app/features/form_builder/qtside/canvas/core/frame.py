"""What the overlay paints, and what a press can hit above the form."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional, Tuple, Union

from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.query.selection import SelectionState
from app.features.form_builder.qtside.canvas.core.chips import Leader
from app.features.form_builder.qtside.canvas.core.space import CanvasRect, Compass, ViewMap
from app.features.form_builder.qtside.canvas.core.structure import Positioning

Role = Literal[
    "select",
    "hover",
    "layout",
    "layout_faint",
    "gap",
    "drop_fill",
    "tab",
    "problem",
    "backdrop_faint",
    "backdrop_accent",
]
GlyphName = Literal["plus", "error"]


@dataclass(frozen=True)
class Stroke:
    rect: CanvasRect
    role: Role
    width: float
    style: Literal["solid", "dashed", "dotted"]
    alpha: float = 1.0


@dataclass(frozen=True)
class Fill:
    rect: CanvasRect
    role: Role


@dataclass(frozen=True)
class Spring:
    rect: CanvasRect
    axis: Literal["horizontal", "vertical"]


@dataclass(frozen=True)
class Handle:
    rect: CanvasRect
    at: Compass


@dataclass(frozen=True)
class Pill:
    rect: CanvasRect
    at: Compass
    hot: bool


@dataclass(frozen=True)
class Chip:
    rect: CanvasRect
    text: str
    role: Role
    leader: Optional[Leader]


@dataclass(frozen=True)
class Badge:
    rect: CanvasRect
    glyph: GlyphName
    role: Role
    leader: Optional[Leader]


@dataclass(frozen=True)
class Caption:
    rect: CanvasRect
    lines: Tuple[str, ...]


@dataclass(frozen=True)
class Glyph:
    rect: CanvasRect
    name: GlyphName
    role: Role


Item = Union[Stroke, Fill, Spring, Handle, Pill, Chip, Badge, Caption, Glyph]


@dataclass(frozen=True)
class OpenLayoutPopover:
    node: NodeId


@dataclass(frozen=True)
class OpenProblem:
    node: NodeId
    message: str


ChipAction = Union[OpenLayoutPopover, OpenProblem]


@dataclass(frozen=True)
class OnHandle:
    node: NodeId
    at: Compass
    writes: bool


@dataclass(frozen=True)
class OnPageEdge:
    at: Compass


@dataclass(frozen=True)
class OnChip:
    action: ChipAction


@dataclass(frozen=True)
class OnWidget:
    node: NodeId
    positioning: Positioning
    site: Literal["widget", "page_tab", "menu_title"]


@dataclass(frozen=True)
class OnSpace:
    select: NodeId
    band_owner: NodeId


Target = Union[OnHandle, OnPageEdge, OnChip, OnWidget, OnSpace]


@dataclass(frozen=True)
class FrameBasis:
    epoch: int
    view: ViewMap
    selection: SelectionState
    problems_revision: int


@dataclass(frozen=True)
class OverlayFrame:
    basis: FrameBasis
    items: Tuple[Item, ...]
    targets: Tuple[Tuple[CanvasRect, Target], ...]
    chips: Tuple[Tuple[CanvasRect, NodeId], ...]
