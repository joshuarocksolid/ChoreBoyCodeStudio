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
        column.setSpacing(4)
        self._column = column
        heading = QLabel("Uses of %s" % shown, self)
        heading.setObjectName("formBuilder.logic.usesHeading")
        heading.setWordWrap(True)
        heading.setMinimumWidth(0)
        column.addWidget(heading)
        self._fill()
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
        for row in self._rows:
            row.apply_colors(
                tokens.text_primary,  # type: ignore[attr-defined]
                chrome.faint,
                chrome.row_hover,
                chrome.selected,
                chrome.warning,
                tokens.panel_bg,  # type: ignore[attr-defined]
                self._family,
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
            heading = QLabel(title, self)
            heading.setObjectName("formBuilder.logic.title")
            heading.setTextFormat(_PLAIN)
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
        aside = "· %s" % use.signal if use.signal else ""
        body = use.summary or use.method
        if body and "\u2192" in body:
            accessible = "%s %s" % (display, body)
            return RowFace(display, body, "", False, False, body, accessible)
        return RowFace(display, aside, body, True, False, body, accessible)
    return RowFace(display, use.signal or use.method, use.summary, True, False, use.widget, accessible)


def displays_for(env: object) -> Dict[str, str]:
    widgets = getattr(env, "widgets", None) or {}
    found = {}
    for name, facts in widgets.items():
        display = getattr(facts, "display", "") or ""
        if isinstance(display, str) and display and display != name:
            found[name] = display.replace("&", "")
    return found
