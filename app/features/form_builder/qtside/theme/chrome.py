"""Builder chrome colours and sizes. Hex lives only in this module."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, IntEnum
from typing import Dict, Protocol, Tuple

CHROME_BASE_PX = 12
DOT_STEP_PX = 16
DOT_SIZE_PX = 1
# The 1 px line needs a wider grab. 6 is not a 4 px grid step.
SPLITTER_HIT_PX = 6
SEARCH_GLYPH = "\u2315"
# U+2315 draws in a small part of the em square, so body size stays a speck.
SEARCH_GLYPH_PX = 16
# Level 2 blur is 16% black. It is not the page-card shadow.
_LEVEL2_SHADOW = "rgba(0,0,0,0.16)"

_TEXT = "text"
_UI = "ui"


class ChromeKind(str, Enum):
    LIGHT = "light"
    DARK = "dark"
    HC_LIGHT = "hc_light"
    HC_DARK = "hc_dark"


class Space(IntEnum):
    XS = 4
    S = 8
    M = 12
    L = 16
    XL = 24
    XXL = 32


class Height(IntEnum):
    CONTROL = 24
    BUTTON = 24
    PRIMARY = 28
    OUTLINE_ROW = 24
    INSPECTOR_ROW = 28
    SECTION = 28
    TOOLBAR = 36


class Radius(IntEnum):
    CONTROL = 4
    POPOVER = 6
    PAGE = 6
    START = 8


@dataclass(frozen=True)
class FontRole:
    px: int
    weight: int
    uppercase: bool = False
    letter_spacing_px: float = 0.0


@dataclass(frozen=True)
class TypeScale:
    overline: FontRole
    caption: FontRole
    body: FontRole
    strong: FontRole
    title: FontRole
    screen: FontRole
    hero: FontRole

    def chip(self) -> FontRole:
        return FontRole(self.caption.px, 600, False, 0.0)


def type_scale(base_px: int = CHROME_BASE_PX) -> TypeScale:
    return TypeScale(
        overline=FontRole(base_px - 2, 600, True, 0.5),
        caption=FontRole(base_px - 1, 400, False, 0.0),
        body=FontRole(base_px, 400, False, 0.0),
        strong=FontRole(base_px, 600, False, 0.0),
        title=FontRole(base_px + 1, 600, False, 0.0),
        screen=FontRole(base_px + 6, 600, False, 0.0),
        hero=FontRole(base_px + 10, 600, False, 0.0),
    )


def font_css(role: FontRole, *, lock_weight: bool = False) -> str:
    parts = ["font-size: %dpx" % role.px]
    if lock_weight:
        parts.append("font-weight: %d" % role.weight)
    if role.uppercase:
        parts.append("text-transform: uppercase")
    if role.letter_spacing_px:
        parts.append("letter-spacing: %gpx" % role.letter_spacing_px)
    return "; ".join(parts)


@dataclass(frozen=True)
class TitleBarLook:
    height: int
    fill: str
    glyph: str
    title_px: int
    title_weight: int
    marks: Tuple[str, str, str]


TITLE_BAR = TitleBarLook(
    22,
    "#E4E4E4",
    "#6B6B6B",
    11,
    600,
    ("\u2013", "\u25a1", "\u00d7"),
)


@dataclass(frozen=True)
class Shadow:
    x: int
    y: int
    blur: int
    color: str


@dataclass(frozen=True)
class Elevation:
    shadows: Tuple[Shadow, ...]
    border_px: int
    border_color: str


@dataclass(frozen=True)
class ContrastPair:
    fg: str
    bg: str
    kind: str


# Shell border-on-panel is about 1.3:1 and the dot grid about 1.2:1.
# Those stay unscored aliases: UX-TOK-001 forbids a second border colour.
# Title-bar greys are fixed by UX-ISO-003 and measure 4.19:1, under the text floor.
CONTRAST_PAIRS: Tuple[ContrastPair, ...] = (
    ContrastPair("text", "panel", _TEXT),
    ContrastPair("text", "input", _TEXT),
    ContrastPair("text", "row_hover", _TEXT),
    ContrastPair("text", "row_selected", _TEXT),
    ContrastPair("text", "popup", _TEXT),
    ContrastPair("text", "backdrop", _UI),
    ContrastPair("muted", "panel", _TEXT),
    ContrastPair("muted", "input", _TEXT),
    ContrastPair("muted", "backdrop", _TEXT),
    ContrastPair("faint", "panel", _TEXT),
    ContrastPair("faint", "input", _TEXT),
    ContrastPair("faint", "backdrop", _UI),
    ContrastPair("error", "panel", _TEXT),
    ContrastPair("error", "input", _TEXT),
    ContrastPair("accent", "panel", _UI),
    ContrastPair("accent", "input", _UI),
    ContrastPair("accent", "backdrop", _UI),
    ContrastPair("accent", "popup", _UI),
)

_PAIR_INDEX = {(pair.fg, pair.bg): pair for pair in CONTRAST_PAIRS}


class ShellTokenSource(Protocol):
    """Fields of ``ShellThemeTokens`` the builder reads. qtside does not import the shell."""

    window_bg: str
    panel_bg: str
    tree_hover_bg: str
    tree_selected_bg: str
    border: str
    text_primary: str
    text_muted: str
    gutter_text: str
    accent: str
    input_bg: str
    popup_bg: str
    popup_border: str
    diag_error_color: str
    diag_warning_color: str
    test_passed_color: str
    is_dark: bool
    is_high_contrast: bool
    focus_border_width: int
    ui_font_weight_css: str


@dataclass(frozen=True)
class _BuilderColumn:
    on_accent: str
    backdrop: str
    dots: str
    page_shadow: str
    page_border: str


_COLUMNS: Dict[ChromeKind, _BuilderColumn] = {
    ChromeKind.LIGHT: _BuilderColumn(
        "#FFFFFF",
        "#E9EBEF",
        "#D3D8DF",
        "rgba(16,24,40,0.10)",
        "#DEE2E6",
    ),
    ChromeKind.DARK: _BuilderColumn(
        "#0B1020",
        "#16191D",
        "#262B31",
        "rgba(0,0,0,0.45)",
        "#3C434A",
    ),
    ChromeKind.HC_LIGHT: _BuilderColumn("#FFFFFF", "#FFFFFF", "", "", "#000000"),
    ChromeKind.HC_DARK: _BuilderColumn("#000000", "#000000", "", "", "#FFFFFF"),
}


def backdrop_of(kind: ChromeKind) -> Tuple[str, str]:
    column = _COLUMNS[kind]
    return column.backdrop, column.dots


def _kind_of(is_dark: bool, is_high_contrast: bool) -> ChromeKind:
    if is_high_contrast:
        return ChromeKind.HC_DARK if is_dark else ChromeKind.HC_LIGHT
    return ChromeKind.DARK if is_dark else ChromeKind.LIGHT


@dataclass(frozen=True)
class ChromeTokens:
    window: str
    panel: str
    row_hover: str
    row_selected: str
    border: str
    text: str
    muted: str
    faint: str
    accent: str
    on_accent: str
    input: str
    popup: str
    popup_border: str
    error: str
    warning: str
    ok: str
    backdrop: str
    dots: str
    page_shadow: str
    page_border: str
    focus_width: int
    weight_css: str
    kind: ChromeKind
    scale: TypeScale

    def color(self, role: str) -> str:
        value = getattr(self, role, None)
        if not isinstance(value, str):
            raise KeyError(role)
        return value

    def paint(self, fg: str, bg: str) -> str:
        if (fg, bg) not in _PAIR_INDEX:
            raise KeyError("undeclared chrome pair %s on %s" % (fg, bg))
        return self.color(fg)


def chrome_tokens(shell: ShellTokenSource) -> ChromeTokens:
    kind = _kind_of(shell.is_dark, shell.is_high_contrast)
    column = _COLUMNS[kind]
    return ChromeTokens(
        window=shell.window_bg,
        panel=shell.panel_bg,
        row_hover=shell.tree_hover_bg,
        row_selected=shell.tree_selected_bg,
        border=shell.border,
        text=shell.text_primary,
        muted=shell.text_muted,
        faint=shell.gutter_text,
        accent=shell.accent,
        on_accent=column.on_accent,
        input=shell.input_bg,
        popup=shell.popup_bg,
        popup_border=shell.popup_border,
        error=shell.diag_error_color,
        warning=shell.diag_warning_color,
        ok=shell.test_passed_color,
        backdrop=column.backdrop,
        dots=column.dots,
        page_shadow=column.page_shadow,
        page_border=column.page_border,
        focus_width=shell.focus_border_width,
        weight_css=shell.ui_font_weight_css,
        kind=kind,
        scale=type_scale(),
    )


def elevation(level: int, chrome: ChromeTokens) -> Elevation:
    high_contrast = chrome.kind in (ChromeKind.HC_LIGHT, ChromeKind.HC_DARK)
    if level == 0:
        return Elevation((), 1, chrome.border)
    if level == 1:
        if high_contrast or not chrome.page_shadow:
            return Elevation((), 1, chrome.text)
        return Elevation(
            (
                Shadow(0, 1, 3, chrome.page_shadow),
                Shadow(0, 4, 12, chrome.page_shadow),
            ),
            0,
            "",
        )
    if level == 2:
        if high_contrast:
            return Elevation((), 2, chrome.text)
        return Elevation((Shadow(0, 8, 24, _LEVEL2_SHADOW),), 1, chrome.popup_border)
    raise ValueError("elevation level must be 0, 1, or 2")


__all__ = [
    "CHROME_BASE_PX",
    "CONTRAST_PAIRS",
    "DOT_SIZE_PX",
    "DOT_STEP_PX",
    "SEARCH_GLYPH",
    "SEARCH_GLYPH_PX",
    "SPLITTER_HIT_PX",
    "TITLE_BAR",
    "ChromeKind",
    "ChromeTokens",
    "ContrastPair",
    "Elevation",
    "FontRole",
    "Height",
    "Radius",
    "Shadow",
    "ShellTokenSource",
    "Space",
    "TitleBarLook",
    "TypeScale",
    "backdrop_of",
    "chrome_tokens",
    "elevation",
    "font_css",
    "type_scale",
]
