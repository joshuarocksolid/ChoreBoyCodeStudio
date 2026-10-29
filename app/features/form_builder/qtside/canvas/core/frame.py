"""What the overlay paints, and what a press can hit above the form."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional, Tuple, Union

from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.query.direct import Axis, Knob
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
    "gap_fill",
    "drop_fill",
    "dock_band",
    "tab",
    "problem",
    "backdrop_faint",
    "backdrop_accent",
]
GlyphName = Literal["plus", "error", "grip"]


@dataclass(frozen=True)
class Stroke:
    rect: CanvasRect
    role: Role
    width: float
    style: Literal["solid", "dashed", "dotted"]
    alpha: float = 1.0
    caps: bool = False
    node: Optional[NodeId] = None


@dataclass(frozen=True)
class Fill:
    rect: CanvasRect
    role: Role
    alpha: float = 1.0


@dataclass(frozen=True)
class Spring:
    rect: CanvasRect
    axis: Literal["horizontal", "vertical"]
    node: Optional[NodeId] = None


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
    #: In the dock strip. The view paints it as chrome above the page caption.
    docked: bool = False
    tip: str = ""


@dataclass(frozen=True)
class Badge:
    rect: CanvasRect
    glyph: GlyphName
    role: Role
    leader: Optional[Leader]
    #: Hover text. Also the accessible description. Empty for a badge with no sentence.
    tip: str = ""


@dataclass(frozen=True)
class Caption:
    rect: CanvasRect
    lines: Tuple[str, ...]
    role: Role = "layout"
    #: Under a mode overlay (tab order, buddies) "Drop widgets here" fades with the layout frames (UX-OVL-003).
    alpha: float = 1.0


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


@dataclass(frozen=True)
class AddPage:
    container: NodeId


@dataclass(frozen=True)
class ShowStacked:
    """``delta`` is -1 or 1. Zero means the click position picks the arrow."""

    container: NodeId
    delta: int = 0


@dataclass(frozen=True)
class FocusShare:
    """Select ``node`` and focus its share spin for ``axis`` in the inspector."""

    node: NodeId
    axis: Axis


ChipAction = Union[OpenLayoutPopover, OpenProblem, AddPage, ShowStacked, FocusShare]


@dataclass(frozen=True)
class OnHandle:
    """A handle on a layout or spacer. Their container gives them their size."""

    node: NodeId
    at: Compass


@dataclass(frozen=True)
class OnKnob:
    knob: Knob


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


Target = Union[OnKnob, OnHandle, OnPageEdge, OnChip, OnWidget, OnSpace]


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
    #: The dock strip this frame was solved against. Docked chips sit at a
    #: fixed offset inside it while the view scrolls.
    dock: Optional[CanvasRect] = None
