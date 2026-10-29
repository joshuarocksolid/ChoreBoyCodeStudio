"""Builder chrome colours: dialog/Start roles (FormChrome) and canvas chrome
(UX-TOK-001, UX-TOK-002, UX-ISO-003).

Hex values for the builder live here. Callers fill roles from shell theme
tokens and pass theme flags. This module does not import the shell.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

PAGE_TITLE_HEIGHT = 22
PAGE_TITLE_FILL = "#E4E4E4"
PAGE_TITLE_GLYPH = "#6B6B6B"
PAGE_TITLE_TEXT = "#3C3C3C"
EDITOR_BACKGROUND = "#FFFFFF"
EDITOR_TEXT = "#212529"
FALLBACK_FAINT = "#666F76"
FALLBACK_ACCENT = "#3366FF"
FALLBACK_MUTED = "#5A6168"
FALLBACK_PANEL = "#FFFFFF"
FALLBACK_BORDER = "#DEE2E6"
FALLBACK_TEXT = "#212529"


def editor_field_colors() -> Tuple[str, str]:
    """In-place editor fill and text. Hex for the builder stays in this module."""
    return (EDITOR_BACKGROUND, EDITOR_TEXT)


def fallback_backdrop_roles() -> Tuple[str, str, str, str, str, str]:
    """faint, accent, muted, panel, border, text when no shell theme is applied."""
    return (
        FALLBACK_FAINT,
        FALLBACK_ACCENT,
        FALLBACK_MUTED,
        FALLBACK_PANEL,
        FALLBACK_BORDER,
        FALLBACK_TEXT,
    )


def backdrop_colors(*, is_dark: bool, is_high_contrast: bool) -> Tuple[str, str]:
    """Backdrop fill and 1 px dot colour. High contrast has no dots."""
    if is_high_contrast:
        return ("#000000", "") if is_dark else ("#FFFFFF", "")
    if is_dark:
        return ("#16191D", "#262B31")
    return ("#E9EBEF", "#D3D8DF")


def page_shadow_rgba(*, is_dark: bool, is_high_contrast: bool) -> Optional[Tuple[int, int, int, int]]:
    """Drop shadow for the page card. High contrast uses a border instead."""
    if is_high_contrast:
        return None
    if is_dark:
        return (0, 0, 0, 115)
    return (16, 24, 40, 26)


@dataclass(frozen=True)
class FormChrome:
    """One snapshot of the builder chrome roles."""

    window: str
    panel: str
    text: str
    muted: str
    faint: str
    border: str
    accent: str
    row_hover: str
    input: str
    error: str
    focus_width: int
    on_accent: str = "#FFFFFF"
    search_match_bg: str = ""
    # Background of a chosen item (a checked segment), under ``text``.
    selected: str = ""
    # UX-TOK-001 popup pair and the shell's icon colour (UX-TOK-005 ``fb.glyph``).
    popup: str = ""
    popup_border: str = ""
    glyph: str = ""
    is_dark: bool = False
    is_high_contrast: bool = False
    # ov.layout and ov.gap, as ``#RRGGBB``, for layout and spacer glyphs.
    layout: str = ""
    gap: str = ""

    def __post_init__(self) -> None:
        if not self.search_match_bg:
            object.__setattr__(self, "search_match_bg", self.row_hover)
        if not self.selected:
            object.__setattr__(self, "selected", self.row_hover)
        if not self.popup:
            object.__setattr__(self, "popup", self.panel)
        if not self.popup_border:
            object.__setattr__(self, "popup_border", self.border)
        if not self.glyph:
            object.__setattr__(self, "glyph", self.text)

    @property
    def fb(self) -> "ChromeTokens":
        """The ``fb.*`` tokens of UX-TOK-005 for this chrome."""
        return chrome_tokens(self)


@dataclass(frozen=True)
class ChromeTokens:
    """UX-TOK-005 chrome tokens. Aliases read the chrome; the rest are fixed per mode."""

    popup: str
    popup_border: str
    tile_hover: str
    tile_current: str
    glyph: str
    match: str
    swatch_border: str
    checker_a: str
    checker_b: str
    handle_fill: str
    handle_border: str
    handle_border_px: float
    handle_current_border: str
    handle_current_px: int


# Fixed colours of UX-TOK-005 that are not aliases: (light, dark, HC light, HC dark).
_CHECKER_A = ("#FFFFFF", "#3C434A", "#FFFFFF", "#000000")
_CHECKER_B = ("#D3D8DF", "#262C33", "#000000", "#FFFFFF")
_HANDLE_FILL = ("", "", "#FFFFFF", "#000000")
_HANDLE_BORDER = ("", "", "#000000", "#FFFFFF")
_HANDLE_CURRENT = ("", "", "#0000C0", "#7CB7FF")
_SWATCH_BORDER = ("", "", "#000000", "#FFFFFF")


def _mode_index(chrome: FormChrome) -> int:
    if chrome.is_high_contrast:
        return 3 if chrome.is_dark else 2
    return 1 if chrome.is_dark else 0


def chrome_tokens(chrome: FormChrome) -> ChromeTokens:
    """The UX-TOK-005 chrome tokens for ``chrome``. Form-surface tokens are not here."""
    mode = _mode_index(chrome)
    high_contrast = chrome.is_high_contrast
    return ChromeTokens(
        popup=chrome.popup,
        popup_border=chrome.popup_border,
        tile_hover=chrome.row_hover,
        tile_current=chrome.selected,
        glyph=chrome.glyph,
        match=chrome.search_match_bg,
        swatch_border=_SWATCH_BORDER[mode] if high_contrast else chrome.border,
        checker_a=_CHECKER_A[mode],
        checker_b=_CHECKER_B[mode],
        handle_fill=_HANDLE_FILL[mode] if high_contrast else chrome.panel,
        handle_border=_HANDLE_BORDER[mode] if high_contrast else chrome.text,
        handle_border_px=2.0 if high_contrast else 1.5,
        handle_current_border=_HANDLE_CURRENT[mode] if high_contrast else chrome.accent,
        handle_current_px=2,
    )


def default_chrome() -> FormChrome:
    """The chrome used before a shell theme is applied (light fallback roles)."""
    faint, accent, muted, panel, border, text = fallback_backdrop_roles()
    return chrome_from_values(
        window=panel,
        panel=panel,
        text=text,
        muted=muted,
        faint=faint,
        border=border,
        accent=accent,
        row_hover=border,
        input_bg=panel,
        error=FALLBACK_ACCENT,
        focus_width=1,
    )


LAYOUT_CONFIRM_NAME = "formBuilder.layoutConfirm"


def menu_style(chrome: FormChrome) -> str:
    """Context menu and its submenus. A submenu is its own window, so it does not inherit."""
    return (
        "QMenu { background: %(panel)s; color: %(text)s; border: 1px solid %(border)s; }"
        "QMenu::item { background: transparent; color: %(text)s; padding: 4px 28px 4px 12px; }"
        "QMenu::item:selected { background: %(hover)s; color: %(text)s; }"
        "QMenu::item:disabled { color: %(muted)s; }"
    ) % {
        "panel": chrome.panel,
        "text": chrome.text,
        "muted": chrome.muted,
        "border": chrome.border,
        "hover": chrome.row_hover,
    }


def popover_style(object_name: str, chrome: FormChrome) -> str:
    """Frame, text, and buttons of the builder popover named ``object_name``."""
    frame = "QFrame#%s" % object_name.replace(".", "\\.")
    return (
        "%(f)s { background: %(panel)s; color: %(text)s; border: 1px solid %(border)s; border-radius: 6px; }"
        "%(f)s QLabel { color: %(text)s; background: transparent; border: none; }"
        "%(f)s QLabel[note=\"true\"] { color: %(muted)s; }"
        "%(f)s QPushButton, %(f)s QToolButton {"
        " color: %(text)s; background: %(input)s; border: 1px solid %(border)s;"
        " border-radius: 4px; padding: 6px 10px; }"
        "%(f)s QPushButton:hover, %(f)s QToolButton:hover { background: %(hover)s; }"
        "%(f)s QPushButton:focus, %(f)s QToolButton:focus {"
        " border: %(focus)dpx solid %(accent)s; }"
        "%(f)s QPushButton:disabled, %(f)s QToolButton:disabled { color: %(muted)s; background: %(panel)s; }"
    ) % {
        "f": frame,
        "panel": chrome.panel,
        "text": chrome.text,
        "muted": chrome.muted,
        "border": chrome.border,
        "input": chrome.input,
        "hover": chrome.row_hover,
        "accent": chrome.accent,
        "focus": chrome.focus_width,
    }


def on_accent_for(accent: str) -> str:
    """Text on an accent fill: white, or near-black when white is under 4.5 : 1."""
    if _contrast(accent, "#FFFFFF") >= 4.5:
        return "#FFFFFF"
    return "#0B1020"


def _contrast(first: str, second: str) -> float:
    lighter, darker = sorted((_luminance(first), _luminance(second)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def _luminance(color: str) -> float:
    value = color.lstrip("#")
    if len(value) != 6:
        return 0.0
    channels = []
    for index in (0, 2, 4):
        channel = int(value[index:index + 2], 16) / 255.0
        channels.append(channel / 12.92 if channel <= 0.03928 else ((channel + 0.055) / 1.055) ** 2.4)
    red, green, blue = channels
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def edge_on(chrome: FormChrome, background: str) -> str:
    """A 1 px edge that clears 3:1 on ``background``.

    High contrast borders already do. A pale border on a near-same fill does not,
    so the control uses the text colour, which the theme already keeps readable.
    """
    if _contrast(chrome.border, background) >= 3.0:
        return chrome.border
    return chrome.text


def link_ink(chrome: FormChrome) -> str:
    """Disclosure text. Accent when it clears the text floor, otherwise body text."""
    floor = 7.0 if chrome.is_high_contrast else 4.5
    if _contrast(chrome.accent, chrome.panel) >= floor:
        return chrome.accent
    return chrome.text


def _check_image(chrome: FormChrome) -> str:
    name = "check-light.svg" if chrome.on_accent == "#FFFFFF" else "check-dark.svg"
    return Path(__file__).resolve().with_name(name).as_posix()


def _under(ancestor: str, selector: str) -> str:
    """Prefix each comma-separated selector when a sheet is scoped to one frame."""
    if not ancestor:
        return selector
    return ", ".join("%s %s" % (ancestor, part.strip()) for part in selector.split(","))


def _state(selector: str, pseudo: str) -> str:
    """Append ``pseudo`` to every comma-separated selector.

    ``"A, B" + ":focus"`` leaves A without the pseudo, so A is painted in
    that state all the time. Translation's permanent blue box was that bug.
    """
    return ", ".join("%s%s" % (part.strip(), pseudo) for part in selector.split(",") if part.strip())


# Disclosures and flat adds. A generic push-button rule must not box these.
_LINK_BUTTONS = (
    "QToolButton#formBuilder\\.translationToggle",
    "QToolButton#formBuilder\\.itemMore",
    "QToolButton#formBuilder\\.iconOtherStates",
    "QToolButton#formBuilder\\.pagesAdd",
    "QPushButton#formBuilder\\.addCustomProperty",
)


def disabled_field_declaration(chrome: FormChrome) -> str:
    """Disabled field text. High contrast also dashes the border, so the state is not colour alone."""
    if chrome.is_high_contrast:
        return "color: %s; border: 1px dashed %s;" % (chrome.muted, chrome.muted)
    return "color: %s;" % chrome.muted


def control_qss(chrome: FormChrome, ancestor: str = "") -> str:
    """Summary buttons, empty check boxes, and disclosure links.

    A stylesheet rule on ``QCheckBox`` or ``QPushButton`` drops the native
    frame. These rules paint the frame from the chrome tokens. ``ancestor``
    scopes them under one frame so a broader child rule cannot win.
    """
    edge = edge_on(chrome, chrome.panel)
    fill = chrome.panel
    disabled = chrome.muted if _contrast(chrome.muted, fill) >= 3.0 else edge
    check = _check_image(chrome)
    focus = chrome.focus_width if chrome.focus_width > 0 else 1
    ink = link_ink(chrome)
    summary = _under(ancestor, "QPushButton#formBuilder\\.summary")
    box = _under(ancestor, "QCheckBox")
    links = _under(ancestor, ", ".join(_LINK_BUTTONS))
    underline = "underline" if chrome.is_high_contrast else "none"
    return (
        "%(summary)s {"
        " color: %(text)s; background: %(input)s; border: 1px solid %(edge)s;"
        " border-radius: 4px; padding: 2px 8px; text-align: left; }"
        "%(summary_focus)s { border: %(focus)dpx solid %(accent)s; }"
        "%(summary)s[fbIssue=\"missing\"] { color: %(error)s; }"
        "%(summary)s[fbState=\"set\"] { font-weight: 600; }"
        "%(summary)s[fbState=\"unset\"], %(summary)s[fbState=\"mixed\"] { font-weight: 400; }"
        "%(box)s { spacing: 6px; background: transparent; }"
        "%(box)s::indicator {"
        " width: 13px; height: 13px; border: 1px solid %(edge)s; background: %(fill)s; image: none; }"
        "%(box)s::indicator:checked {"
        " background: %(accent)s; border: 1px solid %(edge)s; image: url(%(check)s); }"
        "%(box)s::indicator:disabled {"
        " border: 1px solid %(disabled)s; background: %(fill)s; image: none; }"
        "%(box)s::indicator:checked:disabled {"
        " background: %(accent)s; border: 1px solid %(disabled)s; image: url(%(check)s); }"
        "%(links)s {"
        " color: %(ink)s; background: transparent; border: none; padding: 0px;"
        " text-align: left; text-decoration: %(underline)s; }"
        "%(links_focus)s { border: %(focus)dpx solid %(accent)s; background: transparent; }"
        % {
            "summary": summary,
            "summary_focus": _state(summary, ":focus"),
            "box": box,
            "links": links,
            "links_focus": _state(links, ":focus"),
            "underline": underline,
            "text": chrome.text,
            "input": chrome.input,
            "edge": edge,
            "focus": focus,
            "accent": chrome.accent,
            "error": chrome.error,
            "fill": fill,
            "disabled": disabled,
            "check": check,
            "ink": ink,
        }
    )


def field_qss(chrome: FormChrome, ancestor: str = "") -> str:
    """Line edits and combos outside the inspector sheet (the item editor)."""
    background = chrome.input or chrome.panel
    edge = edge_on(chrome, background)
    focus = chrome.focus_width if chrome.focus_width > 0 else 1
    kinds = _under(
        ancestor,
        "QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QFontComboBox",
    )
    line = _under(ancestor, "QLineEdit")
    return (
        "%(kinds)s { background: %(input)s; color: %(text)s; border: 1px solid %(edge)s; }"
        "%(disabled)s { %(disabled_decl)s }"
        "%(line)s { padding: 1px 4px; }"
        "%(focused)s { border: %(focus)dpx solid %(accent)s; }"
        % {
            "kinds": kinds,
            "disabled": _state(kinds, ":disabled"),
            "disabled_decl": disabled_field_declaration(chrome),
            "line": line,
            "focused": _state(kinds, ":focus"),
            "input": background,
            "text": chrome.text,
            "muted": chrome.muted,
            "edge": edge,
            "focus": focus,
            "accent": chrome.accent,
        }
    )


def item_editor_qss(chrome: FormChrome) -> str:
    """Level-2 popover frame for the item editor (UX-ITEM-002, UX-ELEV-001)."""
    frame_px = 2 if chrome.is_high_contrast else 1
    edge = chrome.text if chrome.is_high_contrast else (chrome.popup_border or chrome.border)
    fill = chrome.popup or chrome.panel
    name = "QFrame#formBuilder\\.itemEditor"
    frame = (
        "%(name)s { background: %(fill)s; color: %(text)s;"
        " border: %(frame_px)dpx solid %(edge)s; border-radius: 6px; }"
        "%(name)s QWidget { background: transparent; color: %(text)s; }"
        "%(name)s QLabel { color: %(text)s; background: transparent; border: none; }"
        "%(name)s QAbstractScrollArea { background: transparent; border: none; }"
        "%(name)s QPushButton#formBuilder\\.itemEditorDone {"
        " color: %(on_accent)s; background: %(accent)s; border: none;"
        " border-radius: 4px; padding: 6px 10px; font-weight: 600; }"
        % {
            "name": name,
            "fill": fill,
            "text": chrome.text,
            "frame_px": frame_px,
            "edge": edge,
            "on_accent": chrome.on_accent,
            "accent": chrome.accent,
        }
    )
    return frame + field_qss(chrome, name) + control_qss(chrome, name)


def apply_level2_shadow(widget: object, chrome: FormChrome) -> None:
    """UX-ELEV-001 level 2. High contrast uses the 2 px border and no shadow."""
    from app.qt.QtGui import QColor
    from app.qt.QtWidgets import QGraphicsDropShadowEffect

    if chrome.is_high_contrast:
        widget.setGraphicsEffect(None)  # type: ignore[attr-defined]
        return
    shadow = QGraphicsDropShadowEffect(widget)  # type: ignore[arg-type]
    shadow.setBlurRadius(24)
    shadow.setOffset(0, 8)
    shadow.setColor(QColor(0, 0, 0, 41))
    widget.setGraphicsEffect(shadow)  # type: ignore[attr-defined]


def chrome_from_values(
    *,
    window: str,
    panel: str,
    text: str,
    muted: str,
    faint: str,
    border: str,
    accent: str,
    row_hover: str,
    input_bg: str,
    error: str,
    focus_width: int,
    search_match_bg: str = "",
    selected: str = "",
    popup: str = "",
    popup_border: str = "",
    glyph: str = "",
    is_dark: bool = False,
    is_high_contrast: bool = False,
    layout: str = "",
    gap: str = "",
) -> FormChrome:
    return FormChrome(
        window=window,
        panel=panel or window,
        text=text,
        muted=muted or text,
        faint=faint or muted or text,
        border=border,
        accent=accent,
        row_hover=row_hover or panel or window,
        input=input_bg or panel or window,
        error=error or accent,
        focus_width=focus_width if focus_width > 0 else 1,
        on_accent=on_accent_for(accent),
        search_match_bg=search_match_bg,
        selected=selected,
        popup=popup,
        popup_border=popup_border,
        glyph=glyph,
        is_dark=is_dark,
        is_high_contrast=is_high_contrast,
        layout=layout,
        gap=gap,
    )
