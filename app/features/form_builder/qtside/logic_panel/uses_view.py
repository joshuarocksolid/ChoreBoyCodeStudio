"""Uses of one name. The same two-line row as the Logic panel, grouped by role."""

from __future__ import annotations

from typing import Dict, Optional, Sequence, Tuple

from app.qt.QtCore import Qt
from app.qt.QtGui import QColor, QPalette
from app.qt.QtWidgets import QDialog, QLabel, QVBoxLayout, QWidget
from app.qt.qt_compat import enum_value

from app.core.constants import UI_EDITOR_FONT_FAMILY_DEFAULT
from app.features.form_builder.engine.logic.uses import WORDS, Use
from app.features.form_builder.qtside.logic_panel.rows import LogicRow, RowFace, paint_roles
from app.features.form_builder.qtside.theme.chrome import chrome_from_values
from app.features.form_builder.qtside.theme.metrics import ROW
from app.features.form_builder.qtside.theme.section_header import SectionHeader

_PLAIN = getattr(getattr(Qt, "TextFormat", Qt), "PlainText")
_GROUPS = (("read", "READS"), ("set", "SETS"), ("call", "CALLS"))


class UsesDialog(QDialog):
    def __init__(
        self,
        name: str,
        display: str,
        uses: Tuple[Use, ...],
        lines: Sequence[str],
        displays: Optional[Dict[str, str]],
        tokens: object,
        parent: Optional[QWidget] = None,
        code_family: str = "",
    ) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.logic.uses")
        shown = display or name
        self.setWindowTitle("Uses of %s" % shown)
        self.setMinimumWidth(0)
        self._name = name
        self._display = shown
        self._uses = uses
        self._lines = tuple(lines)
        self._displays = displays or {}
        self._tokens = tokens
        self._family = code_family or UI_EDITOR_FONT_FAMILY_DEFAULT
        self._rows: list = []
        column = QVBoxLayout(self)
        column.setContentsMargins(8, 8, 8, 8)
        column.setSpacing(8)
        self._column = column
        self._fill()
        self.setFixedWidth(320)
        if tokens is not None:
            self.apply_theme(tokens)
        self.resize(560, 320)

    def keyPressEvent(self, event: object) -> None:  # noqa: N802
        if enum_value(event.key()) == enum_value(Qt.Key.Key_Escape):  # type: ignore[attr-defined]
            self.reject()
            return
        super().keyPressEvent(event)  # type: ignore[arg-type]

    def apply_theme(self, tokens: object) -> None:
        self._tokens = tokens
        chrome = paint_roles(tokens)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAutoFillBackground(True)
        palette = self.palette()
        role = getattr(QPalette, "ColorRole", QPalette)
        palette.setColor(getattr(role, "Window"), QColor(tokens.panel_bg))  # type: ignore[attr-defined]
        palette.setColor(getattr(role, "WindowText"), QColor(tokens.text_primary))  # type: ignore[attr-defined]
        self.setPalette(palette)
        self.setStyleSheet(
            "QDialog#formBuilder\\.logic\\.uses { background: %s; color: %s; }"
            "QLabel { color: %s; background: transparent; }"
            "QLabel#formBuilder\\.logic\\.title {"
            " color: %s; font-size: 10px; font-weight: 600; letter-spacing: 0.5px; }"
            % (
                tokens.panel_bg,  # type: ignore[attr-defined]
                tokens.text_primary,  # type: ignore[attr-defined]
                tokens.text_primary,  # type: ignore[attr-defined]
                tokens.text_muted,  # type: ignore[attr-defined]
            )
        )
        for index in range(self._column.count()):
            item = self._column.itemAt(index)
            widget = item.widget() if item is not None else None
            if isinstance(widget, SectionHeader):
                widget.apply_chrome(_form_chrome(tokens))
        for row in self._rows:
            row.apply_colors(
                tokens.text_primary,  # type: ignore[attr-defined]
                chrome.faint,
                chrome.row_hover,
                chrome.selected,
                chrome.warning,
                tokens.panel_bg,  # type: ignore[attr-defined]
                self._family,
                str(getattr(tokens, "accent", "") or ""),
                int(getattr(tokens, "focus_border_width", 2) or 2),
            )

    def _fill(self) -> None:
        if not self._uses:
            empty = QLabel(
                "Nothing in this form reads, sets, or calls %s." % self._display,
                self,
            )
            empty.setWordWrap(True)
            empty.setMinimumWidth(0)
            self._column.addWidget(empty)
            self._column.addStretch(1)
            return
        number = 0
        for role, title in _GROUPS:
            rows = tuple(use for use in self._uses if use.role == role)
            if not rows:
                continue
            heading = SectionHeader(self, title, object_name="formBuilder.logic.title")
            heading.setFixedHeight(ROW)
            self._column.addWidget(heading)
            for use in rows:
                face = _face(use, self._display_of(use.widget), self._lines)
                label = LogicRow(face, self, takes_focus=False)
                label.setObjectName("formBuilder.logic.uses.row.%d" % number)
                self._column.addWidget(label)
                self._rows.append(label)
                number += 1
        self._column.addStretch(1)

    def _display_of(self, name: str) -> str:
        return self._displays.get(name) or name


def _face(use: Use, display: str, lines: Sequence[str]) -> RowFace:
    accessible = "%s, %s" % (use.role, use.widget or use.name)
    if use.kind == "code" and use.line:
        path = use.path or "window file"
        source = lines[use.line - 1].strip() if 0 < use.line <= len(lines) else ""
        return RowFace("", "%s:%d" % (path, use.line), source, True, False, source or path, accessible)
    if use.kind == "rule":
        words = WORDS.get(use.property_key, use.property_key)
        return RowFace(display, words, use.summary, True, False, use.summary, accessible)
    if use.kind == "check":
        return RowFace(display, use.summary, "", False, False, use.summary, accessible)
    if use.kind == "step":
        aside = "· %s" % use.signal.strip() if use.signal and use.signal.strip() else ""
        body = use.summary or use.method
        if body and "\u2192" in body:
            accessible = "%s %s" % (display, body)
            return RowFace(display, body, "", False, False, body, accessible)
        return RowFace(display, aside, body, True, False, body, accessible)
    return RowFace(display, use.signal or use.method, use.summary, True, False, use.widget, accessible)


def _form_chrome(tokens: object):
    return chrome_from_values(
        window=str(getattr(tokens, "window_bg", "") or ""),
        panel=str(getattr(tokens, "panel_bg", "") or ""),
        text=str(getattr(tokens, "text_primary", "") or ""),
        muted=str(getattr(tokens, "text_muted", "") or ""),
        faint=str(getattr(tokens, "gutter_text", "") or ""),
        border=str(getattr(tokens, "border", "") or ""),
        accent=str(getattr(tokens, "accent", "") or ""),
        row_hover=str(getattr(tokens, "tree_hover_bg", "") or ""),
        input_bg=str(getattr(tokens, "input_bg", "") or ""),
        error=str(getattr(tokens, "diag_error_color", "") or ""),
        focus_width=int(getattr(tokens, "focus_border_width", 1) or 1),
        selected=str(getattr(tokens, "tree_selected_bg", "") or ""),
        icon_muted=str(getattr(tokens, "icon_muted", "") or ""),
        is_dark=bool(getattr(tokens, "is_dark", False)),
        is_high_contrast=bool(getattr(tokens, "is_high_contrast", False)),
    )


def displays_for(env: object) -> Dict[str, str]:
    widgets = getattr(env, "widgets", None) or {}
    found = {}
    for name, facts in widgets.items():
        display = getattr(facts, "display", "") or ""
        if isinstance(display, str) and display and display != name:
            found[name] = display.replace("&", "")
    return found
