"""Canvas colours. The only canvas module that holds hex values.

``OverlayPalette`` is the same in light and dark chrome and changes only for
high contrast, because it is drawn on the runtime form. ``BackdropPalette``
follows the shell theme. ``qtside`` cannot import ``app.shell``, so
``integration`` builds one from ``ShellThemeTokens``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class OverlayPalette:
    """``#RRGGBBAA``. Only the roles this canvas paints."""

    select: str
    hover: str
    layout: str
    layout_faint: str
    gap: str
    #: Margin bands. The gap colour, faint, so the widgets stay readable under it.
    gap_fill: str
    drop_fill: str
    tab: str
    problem: str
    chip_text: str
    #: Stand-ins (UX-CONT-017): fill, dashed border, and centred text.
    stand_in_fill: str
    stand_in_line: str
    stand_in_text: str
    #: Dock-side drop bands (UX-CONT-012): the fill, with a ``select`` edge.
    dock_band: str
    #: High contrast raises every stroke to 2 px.
    min_stroke: float
    #: "Type here" placeholders on menu bars, menus and toolbars (UX-TOK-006, ``ov.type_here``).
    #: The dashed box is ``layout_faint``; ``menu_drop`` is the ``select`` line.
    type_here_text: str = "#6B6B6BFF"
    #: Widgets the style sheet rule under the drawer's caret styles (UX-STYLE-005, ``ov.style_match``).
    style_match: str = "#0E7490FF"


OVERLAY = OverlayPalette(
    select="#2F5BEAFF",
    hover="#2F5BEA8C",
    layout="#7C3AEDFF",
    layout_faint="#7C3AED47",
    gap="#DB2777FF",
    gap_fill="#DB27771F",
    drop_fill="#2F5BEA1A",
    tab="#B45309FF",
    problem="#C81E1EFF",
    chip_text="#FFFFFFFF",
    stand_in_fill="#F4F4F4FF",
    stand_in_line="#8A8A8AFF",
    stand_in_text="#3C3C3CFF",
    dock_band="#2F5BEA1A",
    min_stroke=1.0,
)

OVERLAY_HIGH_CONTRAST = OverlayPalette(
    select="#0000C0FF",
    hover="#0000C0FF",
    layout="#5B21B6FF",
    layout_faint="#5B21B699",
    gap="#831843FF",
    gap_fill="#83184333",
    drop_fill="#0000C026",
    tab="#7A3E00FF",
    problem="#9C0000FF",
    chip_text="#FFFFFFFF",
    stand_in_fill="#FFFFFFFF",
    stand_in_line="#000000FF",
    stand_in_text="#000000FF",
    dock_band="#0000C026",
    min_stroke=2.0,
    type_here_text="#2A2A2AFF",
    style_match="#00546AFF",
)


def overlay_palette(high_contrast: bool) -> OverlayPalette:
    if high_contrast:
        return OVERLAY_HIGH_CONTRAST
    return OVERLAY


@dataclass(frozen=True)
class BackdropPalette:
    fill: str
    dot: str
    faint: str
    accent: str
    muted: str
    panel: str
    border: str
    text: str


def backdrop_fill(dark: bool, high_contrast: bool) -> Tuple[str, str]:
    """Backdrop and dot colours. High contrast is flat and has no dots."""
    if high_contrast:
        return ("#000000" if dark else "#FFFFFF", "")
    if dark:
        return ("#16191D", "#262B31")
    return ("#E9EBEF", "#D3D8DF")


@dataclass(frozen=True)
class CanvasPalette:
    overlay: OverlayPalette
    backdrop: BackdropPalette
