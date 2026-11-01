"""The Logic panel: filter, wrapping chips, and one two-line row per anchor."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

from app.qt.QtCore import QRect, QSize, Qt
from app.qt.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.core.constants import UI_EDITOR_FONT_FAMILY_DEFAULT
from app.features.form_builder.engine.events import PRIORITY_VIEWS
from app.features.form_builder.engine.logic.formula_env import env_for
from app.features.form_builder.engine.logic.uses import (
    WORDS,
    LogicBook,
    PanelQuery,
    PanelRow,
    Use,
    cache_key,
    collect,
    panel_rows,
)
from app.features.form_builder.engine.ui4.defaults import QtClassTable
from app.features.form_builder.qtside.logic_panel.rows import LogicRow, RowFace, paint_roles

_PLAIN = getattr(getattr(Qt, "TextFormat", Qt), "PlainText")
_EMPTY = "This form has no rules, checks, or events yet. Select a widget and open Behavior to add one."
_NOTE = "Read from the window file. This list is best-effort and Code Studio does not run the file."
_CHIPS = (
    ("rules", "Rules", "Show rules"),
    ("checks", "Checks", "Show checks"),
    ("events", "Events", "Show events"),
    ("problems", "Problems", "Show problems"),
)
_ORDER = ("STATE", "CHECKS", "EVENTS", "IN YOUR CODE")
_IDLE = None  # type: ignore[var-annotated]


def set_idle_runner(runner: Any) -> None:
    """Integration registers the shell idle hook. This module cannot import the shell."""
    global _IDLE
    _IDLE = runner


def _policy(name: str) -> object:
    names = getattr(QSizePolicy, "Policy", QSizePolicy)
    return getattr(names, name)


class _Pills(QWidget):
    """One row of chips. A chip wraps onto the next line only when it does not fit."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.logic.chips")
        self.setMinimumWidth(0)
        self._chips: List[QToolButton] = []
        policy = QSizePolicy(_policy("Preferred"), _policy("Minimum"))  # type: ignore[arg-type]
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)

    def add(self, chip: QToolButton) -> None:
        chip.setParent(self)
        self._chips.append(chip)

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        return self._flow(width, place=False)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(0, self.heightForWidth(max(self.width(), 184)))

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(0, self.heightForWidth(184))

    def resizeEvent(self, event: object) -> None:  # noqa: N802
        super().resizeEvent(event)  # type: ignore[arg-type]
        height = self._flow(self.width(), place=True)
        if self.minimumHeight() != height:
            self.setMinimumHeight(height)

    def _flow(self, width: int, place: bool) -> int:
        x = 0
        y = 0
        line = 0
        gap = 4
        limit = max(1, width)
        for chip in self._chips:
            hint = chip.sizeHint()
            wide = hint.width()
            tall = hint.height()
            if x and x + wide > limit:
                x = 0
                y += line + gap
                line = 0
            if place:
                chip.setGeometry(QRect(x, y, wide, tall))
            x += wide + gap
            line = max(line, tall)
        return y + line


class LogicPanel(QWidget):
    def __init__(self, workbench: Any) -> None:
        super().__init__(workbench)
        self.setObjectName("formBuilder.logic")
        self.setMinimumWidth(0)
        self.setSizePolicy(_policy("Preferred"), _policy("Expanding"))  # type: ignore[arg-type]
        self._workbench = workbench
        self._session = workbench._session
        self._book: Optional[LogicBook] = None
        self._env: Any = None
        self._published: Optional[Tuple[int, int, str, str]] = None
        self._filename = ""
        self._tokens: object = None
        self._rows: List[LogicRow] = []
        self._chips: Dict[str, QToolButton] = {}
        column = QVBoxLayout(self)
        column.setContentsMargins(4, 4, 4, 4)
        column.setSpacing(4)
        link_row = QHBoxLayout()
        link_row.setContentsMargins(0, 0, 0, 0)
        link_row.addStretch(1)
        self._read = QToolButton(self)
        self._read.setObjectName("formBuilder.logic.readAsText")
        self._read.setText("Read as text")
        self._read.setAutoRaise(True)
        self._read.setMinimumWidth(0)
        self._read.clicked.connect(self._open_behavior_text)
        link_row.addWidget(self._read)
        column.addLayout(link_row)
        self._filter = QLineEdit(self)
        self._filter.setObjectName("formBuilder.logic.filter")
        self._filter.setPlaceholderText("Filter")
        self._filter.setAccessibleName("Filter logic")
        self._filter.setMinimumWidth(0)
        self._filter.setSizePolicy(_policy("Ignored"), _policy("Fixed"))  # type: ignore[arg-type]
        self._filter.setClearButtonEnabled(False)
        self._filter.textChanged.connect(self._fill)
        column.addWidget(self._filter)
        self._pills = _Pills(self)
        for key, label, accessible in _CHIPS:
            box = QToolButton(self._pills)
            box.setText(label)
            box.setCheckable(True)
            box.setChecked(True)
            box.setAutoRaise(True)
            box.setObjectName("formBuilder.logic.chip.%s" % key)
            box.setAccessibleName(accessible)
            box.setMinimumWidth(0)
            box.setSizePolicy(_policy("Fixed"), _policy("Fixed"))  # type: ignore[arg-type]
            box.toggled.connect(self._fill)
            self._chips[key] = box
            self._pills.add(box)
        column.addWidget(self._pills)
        self._scroll = QScrollArea(self)
        self._scroll.setObjectName("formBuilder.logic.scroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(_frame())
        off = getattr(getattr(Qt, "ScrollBarPolicy", Qt), "ScrollBarAlwaysOff")
        self._scroll.setHorizontalScrollBarPolicy(off)  # type: ignore[arg-type]
        self._scroll.setMinimumWidth(0)
        self._scroll.setSizePolicy(_policy("Ignored"), _policy("Expanding"))  # type: ignore[arg-type]
        self._body = QWidget()
        self._body.setObjectName("formBuilder.logic.body")
        self._body.setMinimumWidth(0)
        self._body.setSizePolicy(_policy("Ignored"), _policy("Preferred"))  # type: ignore[arg-type]
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(2)
        self._scroll.setWidget(self._body)
        column.addWidget(self._scroll, 1)
        self._idle = False
        self._row_key: Optional[Tuple[object, ...]] = None
        self._sub = self._session.log.subscribe(self._on_log, priority=PRIORITY_VIEWS)
        self.destroyed.connect(lambda *_args: self._sub.close())
        self.reload()

    def book(self) -> Optional[LogicBook]:
        return self._book

    def set_filter_text(self, text: str) -> None:
        """Ctrl+Shift+F on a form tab. The text is the selection, then the filter takes focus."""
        self._filter.setText(text)
        self._filter.setFocus()
        self._filter.selectAll()

    def _open_behavior_text(self) -> None:
        surface = _surface_of(self)
        if surface is None:
            return
        from app.features.form_builder.qtside.logic_panel.read_as_text import show_behavior_text

        show_behavior_text(surface)

    @property
    def tokens(self) -> object:
        return self._tokens

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(0, 80)

    def apply_theme(self, tokens: object) -> None:
        self._tokens = tokens
        chrome = paint_roles(tokens)  # type: ignore[arg-type]
        width = int(tokens.focus_border_width)  # type: ignore[attr-defined]
        # UX-TOK-001 has no fb.divider. An off chip uses fb.border.
        self.setStyleSheet(
            "QWidget#formBuilder\\.logic { background: %s; color: %s; }"
            "QWidget#formBuilder\\.logic\\.body { background: %s; color: %s; }"
            "QLabel { color: %s; background: transparent; }"
            "QLabel#formBuilder\\.logic\\.title {"
            " color: %s; background: transparent; border: none;"
            " font-size: 10px; font-weight: 600; letter-spacing: 0.5px; }"
            "QLabel#formBuilder\\.logic\\.note { color: %s; }"
            "QLineEdit#formBuilder\\.logic\\.filter { background: %s; color: %s; border: 1px solid %s; }"
            "QLineEdit#formBuilder\\.logic\\.filter:focus { border: %dpx solid %s; }"
            "QToolButton { color: %s; background: transparent; border: 1px solid %s;"
            " border-radius: 10px; padding: 2px 8px; font-size: 11px; }"
            "QToolButton:checked { color: %s; background: %s; border: 1px solid %s; }"
            "QToolButton:focus { border: %dpx solid %s; }"
            "QToolButton#formBuilder\\.logic\\.readAsText { color: %s; background: transparent;"
            " border: none; border-radius: 0; padding: 0; font-size: 11px; }"
            "QToolButton#formBuilder\\.logic\\.readAsText:focus { border: %dpx solid %s; }"
            "QScrollArea#formBuilder\\.logic\\.scroll { background: %s; border: none; }"
            % (
                tokens.panel_bg,  # type: ignore[attr-defined]
                tokens.text_primary,  # type: ignore[attr-defined]
                tokens.panel_bg,  # type: ignore[attr-defined]
                tokens.text_primary,  # type: ignore[attr-defined]
                tokens.text_primary,  # type: ignore[attr-defined]
                tokens.text_muted,  # type: ignore[attr-defined]
                chrome.faint,
                tokens.input_bg,  # type: ignore[attr-defined]
                tokens.text_primary,  # type: ignore[attr-defined]
                tokens.border,  # type: ignore[attr-defined]
                width,
                tokens.accent,  # type: ignore[attr-defined]
                tokens.text_primary,  # type: ignore[attr-defined]
                chrome.border,
                chrome.on_accent,
                tokens.accent,  # type: ignore[attr-defined]
                tokens.accent,  # type: ignore[attr-defined]
                width,
                tokens.accent,  # type: ignore[attr-defined]
                tokens.text_muted,  # type: ignore[attr-defined]
                width,
                tokens.accent,  # type: ignore[attr-defined]
                tokens.panel_bg,  # type: ignore[attr-defined]
            )
        )
        viewport = self._scroll.viewport()
        if viewport is not None:
            viewport.setAutoFillBackground(True)
            viewport.setStyleSheet("background: %s;" % tokens.panel_bg)  # type: ignore[attr-defined]
        self._body.setAutoFillBackground(True)
        self._paint_rows()

    def open_row(self, use: Use) -> None:
        surface = _surface_of(self)
        if surface is None:
            return
        from app.features.form_builder.qtside.logic_panel.open import open_use

        open_use(surface, use)

    def reload(self) -> None:
        source, relative = _window_text(_surface_of(self))
        document = self._session.document
        env = env_for(document, None, QtClassTable.shared())
        self._env = env
        key = cache_key(document, source, relative)
        book = collect(document, env, source, relative)
        if key != self._published:
            self._session.diagnostics.publish("logic.code", book.diagnostics)
            self._published = key
        self._book = book
        base = os.path.basename(relative) if relative else ""
        self._filename = base
        self._fill()

    def _on_log(self, _change: object) -> None:
        if self._idle or self._session is None:
            return
        self._idle = True
        if _IDLE is not None:
            _IDLE(self._reload_idle)

    def _reload_idle(self) -> None:
        self._idle = False
        try:
            self.reload()
        except RuntimeError:
            return

    def _query(self) -> PanelQuery:
        return PanelQuery(
            text=self._filter.text(),
            rules=self._chips["rules"].isChecked(),
            checks=self._chips["checks"].isChecked(),
            events=self._chips["events"].isChecked(),
            problems=self._chips["problems"].isChecked(),
        )

    def _fill(self, *_args: object) -> None:
        book = self._book
        if book is None:
            self._clear_body()
            return
        query = self._query()
        rows = panel_rows(book, query)
        key = (
            query.text,
            query.rules,
            query.checks,
            query.events,
            query.problems,
            self._filename,
            tuple((row.section, row.use.widget, row.words, row.summary, row.problem) for row in rows),
        )
        if key == self._row_key and self._body_layout.count():
            return
        self._row_key = key
        self._clear_body()
        if not panel_rows(book, PanelQuery()) and not rows:
            self._message(_EMPTY)
            return
        if query.text and not rows:
            self._message("Nothing matches \u201c%s\u201d." % query.text)
            return
        grouped: Dict[str, List[PanelRow]] = {name: [] for name in _ORDER}
        problems: List[PanelRow] = []
        for row in rows:
            grouped.setdefault(row.section, []).append(row)
            if row.problem:
                problems.append(row)
        number = 0
        for section in _ORDER:
            items = grouped.get(section) or []
            if not items:
                continue
            self._heading(section)
            for row in items:
                number = self._add_row(row, number)
        if query.problems and problems:
            count = len(problems)
            self._heading("PROBLEMS · %d" % count)
            for row in problems:
                number = self._add_row(row, number, section="PROBLEMS")
        self._body_layout.addStretch(1)
        self._paint_rows()

    def _add_row(self, row: PanelRow, number: int, section: str = "") -> int:
        use = row.use
        face = _face(row, self._shown(use.widget), section)
        label = LogicRow(face, self._body, lambda use=use: self.open_row(use))  # type: ignore[misc]
        label.use = use  # type: ignore[attr-defined]
        label.setObjectName("formBuilder.logic.row.%d" % number)
        self._body_layout.addWidget(label)
        self._rows.append(label)
        return number + 1

    def _heading(self, section: str) -> None:
        title = QLabel(section, self._body)
        title.setObjectName("formBuilder.logic.title")
        title.setMinimumWidth(0)
        title.setTextFormat(_PLAIN)
        self._body_layout.addWidget(title)
        if section != "IN YOUR CODE":
            return
        name = self._filename or "the window file"
        note = QLabel("Read-only · from %s. %s" % (name, _NOTE), self._body)
        note.setObjectName("formBuilder.logic.note")
        note.setWordWrap(True)
        note.setMinimumWidth(0)
        note.setTextFormat(_PLAIN)
        self._body_layout.addWidget(note)

    def _message(self, text: str) -> None:
        label = QLabel(text, self._body)
        label.setObjectName("formBuilder.logic.empty")
        label.setWordWrap(True)
        label.setMinimumWidth(0)
        label.setTextFormat(_PLAIN)
        self._body_layout.addWidget(label)
        self._body_layout.addStretch(1)

    def _shown(self, name: str) -> str:
        widgets = getattr(self._env, "widgets", None) or {}
        facts = widgets.get(name)
        display = getattr(facts, "display", "") if facts is not None else ""
        if isinstance(display, str) and display and display != name:
            return display.replace("&", "")
        return name

    def _paint_rows(self) -> None:
        tokens = self._tokens
        if tokens is None:
            return
        chrome = paint_roles(tokens)  # type: ignore[arg-type]
        family = _code_family(_surface_of(self))
        for row in self._rows:
            row.apply_colors(
                tokens.text_primary,  # type: ignore[attr-defined]
                chrome.faint,
                chrome.row_hover,
                chrome.selected,
                chrome.warning,
                tokens.panel_bg,  # type: ignore[attr-defined]
                family,
            )

    def _clear_body(self) -> None:
        self._rows = []
        while self._body_layout.count():
            item = self._body_layout.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.setObjectName("")
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()


def _face(row: PanelRow, display: str, section: str = "") -> RowFace:
    use = row.use
    where = section or row.section
    tooltip = "%s\n%s\n%s" % (use.widget, row.words, row.summary)
    accessible = "%s, %s, %s, %s" % (where, use.widget, row.words, row.summary)
    if row.problem:
        words = WORDS.get(use.property_key, use.property_key)
        sentence = (
            "Your code calls self.ui.%s.%s(...), but an %s rule also controls it. "
            "The rule wins on every refresh."
        ) % (use.widget, use.summary or row.words, words)
        return RowFace(display, row.words, sentence, False, True, tooltip, accessible)
    if row.section == "EVENTS" or (row.section == "IN YOUR CODE" and use.signal and not row.problem):
        body = row.summary if row.summary.casefold() != row.words.casefold() else ""
        aside = "· %s" % row.words if row.words else ""
        return RowFace(display, aside, body, True, False, tooltip, accessible)
    body = row.summary.strip()
    if body.casefold() == row.words.casefold():
        body = ""
    return RowFace(display, row.words, body, True, False, tooltip, accessible)


def _code_family(surface: Any) -> str:
    window = surface.window() if surface is not None and hasattr(surface, "window") else None
    family = getattr(window, "_editor_font_family", "") if window is not None else ""
    if isinstance(family, str) and family.strip():
        return family.strip()
    return UI_EDITOR_FONT_FAMILY_DEFAULT


def _frame() -> object:
    from app.qt.QtWidgets import QFrame

    names = getattr(QFrame, "Shape", QFrame)
    return getattr(names, "NoFrame")


def _surface_of(widget: Optional[QWidget]) -> Any:
    current = widget
    while current is not None:
        if hasattr(current, "session") and hasattr(current, "_path"):
            return current
        current = current.parentWidget()
    return None


def _window_text(surface: Any) -> tuple:
    if surface is None:
        return "", ""
    ask = getattr(surface, "logic_window_file", None)
    base = ask() if callable(ask) else ""
    if not isinstance(base, str):
        base = ""
    folder = os.path.dirname(str(getattr(surface, "_path", "") or ""))
    if not base or not folder:
        return "", base or ""
    path = os.path.join(folder, base)
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read(), base
    except OSError:
        return "", base
