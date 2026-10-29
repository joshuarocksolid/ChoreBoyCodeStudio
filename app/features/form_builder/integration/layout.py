"""Responsive workbench plan (UX-RESP-001..006).

Pure function of the tab's content size and the widths the user last chose.
The widget reads the plan. It does not decide the breakpoint itself.
"""

from __future__ import annotations

from dataclasses import dataclass


LEFT_MIN = 184
LEFT_MAX = 360
LEFT_DEFAULT = 232
INSPECTOR_MIN = 264
INSPECTOR_MAX = 420
INSPECTOR_DEFAULT = 300
COMPACT_LEFT = 200
COMPACT_INSPECTOR = 272
RAIL_WIDTH = 36
DRAWER_WIDTH = 240
INSPECTOR_DRAWER = 288
CANVAS_MIN = 360
GUTTER = 64
TOOLBAR_HEIGHT = 36

WIDE_MIN = 1180
COMPACT_MIN = 900
RAIL_MIN = 720
SHORT_MAX = 560
TOOLBAR_FOLD = 1000


@dataclass(frozen=True)
class WorkbenchMemory:
    """Per-user pane widths and collapsed headers. Not per file."""

    left: int = LEFT_DEFAULT
    inspector: int = INSPECTOR_DEFAULT
    outline_share: int = 45
    outline_collapsed: bool = False
    insert_collapsed: bool = False
    pin_left: bool = False
    pin_inspector: bool = False

    def clamped(self) -> "WorkbenchMemory":
        return WorkbenchMemory(
            left=_clamp(self.left, LEFT_MIN, LEFT_MAX),
            inspector=_clamp(self.inspector, INSPECTOR_MIN, INSPECTOR_MAX),
            outline_share=_clamp(self.outline_share, 15, 85),
            outline_collapsed=bool(self.outline_collapsed),
            insert_collapsed=bool(self.insert_collapsed),
            pin_left=bool(self.pin_left),
            pin_inspector=bool(self.pin_inspector),
        )


@dataclass(frozen=True)
class LayoutPlan:
    """What the tab should show at one content size.

    ``density`` is ``wide``, ``compact``, ``rail`` or ``drawer``.
    ``left_docked`` and ``inspector_docked`` are false when that pane is a rail.
    ``stack_left`` is the H < 560 tabs mode. ``toolbar_compact`` folds labels.
    """

    density: str
    short: bool
    toolbar_compact: bool
    padding: int
    left_width: int
    inspector_width: int
    left_docked: bool
    inspector_docked: bool
    stack_left: bool
    drawer_width: int
    inspector_drawer: int


def plan_workbench(width: int, height: int, memory: WorkbenchMemory) -> LayoutPlan:
    """Breakpoints are on the tab content size, not the window size."""
    remembered = memory.clamped()
    short = height < SHORT_MAX
    toolbar_compact = width < TOOLBAR_FOLD
    if width >= WIDE_MIN:
        density = "wide"
        padding = 12
        left = remembered.left
        inspector = remembered.inspector
        left_docked = True
        inspector_docked = True
    elif width >= COMPACT_MIN:
        density = "compact"
        padding = 8
        left = COMPACT_LEFT
        inspector = COMPACT_INSPECTOR
        left_docked = True
        inspector_docked = True
    elif width >= RAIL_MIN:
        density = "rail"
        padding = 8
        left = remembered.left if remembered.pin_left else RAIL_WIDTH
        inspector = remembered.inspector
        left_docked = remembered.pin_left
        inspector_docked = True
    else:
        density = "drawer"
        padding = 8
        left = remembered.left if remembered.pin_left else RAIL_WIDTH
        inspector = remembered.inspector if remembered.pin_inspector else RAIL_WIDTH
        left_docked = remembered.pin_left
        inspector_docked = remembered.pin_inspector
    left, inspector = _fit_canvas(width, left, inspector, left_docked, inspector_docked)
    return LayoutPlan(
        density=density,
        short=short,
        toolbar_compact=toolbar_compact,
        padding=padding,
        left_width=left,
        inspector_width=inspector,
        left_docked=left_docked,
        inspector_docked=inspector_docked,
        stack_left=short,
        drawer_width=DRAWER_WIDTH,
        inspector_drawer=INSPECTOR_DRAWER,
    )


def _fit_canvas(
    width: int,
    left: int,
    inspector: int,
    left_docked: bool,
    inspector_docked: bool,
) -> tuple[int, int]:
    """Keep a canvas of at least ``CANVAS_MIN`` when the tab is wide enough."""
    spare = width - CANVAS_MIN
    if spare <= 0:
        return left, inspector
    if left + inspector <= spare:
        return left, inspector
    if inspector_docked and inspector > INSPECTOR_MIN:
        inspector = max(INSPECTOR_MIN, spare - left)
    if left_docked and left + inspector > spare and left > LEFT_MIN:
        left = max(LEFT_MIN, spare - inspector)
    return left, inspector


BESIDE_MIN = 300
READABLE_CHARS = 60


@dataclass(frozen=True)
class BesideFit:
    """How a split beside the canvas fits (UX-PREV-004).

    ``beside`` is its width in px; ``rail_left`` and ``rail_right`` say which
    docked panes go to their rails while it is open.
    """

    beside: int
    rail_left: bool = False
    rail_right: bool = False


def fit_beside(
    row: int,
    handle: int,
    *,
    share: float = 0.45,
    min_canvas: int = CANVAS_MIN,
    min_beside: int = BESIDE_MIN,
    left_gain: int = 0,
    right_gain: int = 0,
    readable: int = 0,
) -> "BesideFit | None":
    """Fit a split of ``share`` of the canvas row (at least ``min_beside``), keeping ``min_canvas`` for the canvas.

    When the row is too narrow for both, the
    Outline pane goes to its rail (``left_gain`` px back), then the inspector
    (``right_gain``). None when even that leaves too little room. When ``readable``
    is given, the split also asks for that many px (about 60 characters of code):
    a step that gives it wins over an earlier one that only fits, and when no
    step gives it the most railed one that fits wins.
    """
    steps = [(False, False)]
    if left_gain > 0:
        steps.append((True, False))
    if right_gain > 0:
        steps.append((left_gain > 0, True))
    best = None
    for rail_left, rail_right in steps:
        width = row + (left_gain if rail_left else 0) + (right_gain if rail_right else 0)
        room = width - handle - min_canvas
        if room < min_beside:
            continue
        wanted = max(int(width * share), min(readable, room))
        best = BesideFit(max(min_beside, min(wanted, room)), rail_left, rail_right)
        if best.beside >= readable:
            return best
    return best


def _clamp(value: int, low: int, high: int) -> int:
    if value < low:
        return low
    if value > high:
        return high
    return value


__all__ = [
    "BESIDE_MIN",
    "READABLE_CHARS",
    "BesideFit",
    "CANVAS_MIN",
    "COMPACT_INSPECTOR",
    "COMPACT_LEFT",
    "DRAWER_WIDTH",
    "GUTTER",
    "INSPECTOR_DEFAULT",
    "INSPECTOR_DRAWER",
    "INSPECTOR_MAX",
    "INSPECTOR_MIN",
    "LEFT_DEFAULT",
    "LEFT_MAX",
    "LEFT_MIN",
    "LayoutPlan",
    "RAIL_WIDTH",
    "TOOLBAR_HEIGHT",
    "WorkbenchMemory",
    "fit_beside",
    "plan_workbench",
]
