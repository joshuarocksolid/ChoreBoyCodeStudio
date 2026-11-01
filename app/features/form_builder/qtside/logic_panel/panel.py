"""The Logic panel: filter, four chips, and one row per rule, check, step and connection."""

from __future__ import annotations

import os
from typing import Any, List, Optional, Tuple

from app.qt.QtCore import Qt, QTimer
from app.qt.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from app.qt.qt_compat import enum_value

from app.features.form_builder.engine.events import PRIORITY_VIEWS
from app.features.form_builder.engine.logic.formula_env import env_for
from app.features.form_builder.engine.logic.uses import (
    LogicBook,
    PanelQuery,
    PanelRow,
    Use,
    cache_key,
    collect,
    panel_rows,
)
from app.features.form_builder.engine.ui4.defaults import QtClassTable
from app.features.form_builder.qtside.logic_panel.uses_view import ElidedLabel

_PLAIN = getattr(getattr(Qt, "TextFormat", Qt), "PlainText")
_FOCUS = getattr(getattr(Qt, "FocusPolicy", Qt), "StrongFocus")
_OFF = getattr(getattr(Qt, "ScrollBarPolicy", Qt), "ScrollBarAlwaysOff")
_EMPTY = "This form has no rules, checks, or events yet. Select a widget and open Behavior to add one."
_NOTE = "Read from the window file. This list is best-effort and Code Studio does not run the file."
_CHIPS = (
    ("rules", "Rules"),
    ("checks", "Checks"),
    ("events", "Events"),
    ("problems", "Problems"),
)
_ORDER = ("STATE", "CHECKS", "EVENTS", "IN YOUR CODE")


def _policy(name: str) -> object:
    names = getattr(QSizePolicy, "Policy", QSizePolicy)
    return getattr(names, name)


class _Row(ElidedLabel):
    def __init__(self, panel: "LogicPanel", row: PanelRow, number: int) -> None:
        full = _row_text(row)
        super().__init__(full, panel._body)
        self.use: Use = row.use
        self._panel = panel
        self.setObjectName("formBuilder.logic.row.%d" % number)
        self.setFocusPolicy(_FOCUS)
        self.setAccessibleName("%s, %s, %s, %s" % (row.section, row.use.widget, row.words, row.summary))
        self.setProperty("logicRow", True)
        if row.problem:
            self.setProperty("problem", True)

    def keyPressEvent(self, event: object) -> None:  # noqa: N802
        key = enum_value(event.key())  # type: ignore[attr-defined]
        if key in (_code(Qt.Key.Key_Return), _code(Qt.Key.Key_Enter)):
            # Opening Behavior reloads this panel, which would delete the row mid-event.
            event.accept()  # type: ignore[attr-defined]
            use = self.use
            panel = self._panel
            QTimer.singleShot(0, lambda: panel.open_row(use))
            return
        super().keyPressEvent(event)  # type: ignore[arg-type]


def _code(key: object) -> int:
    return int(enum_value(key))


def _row_text(row: PanelRow) -> str:
    """Drop a summary that only repeats the words, so a check is not 'Required required'."""
    summary = row.summary.strip()
    if summary and summary.casefold() != row.words.casefold():
        return "%s  %s  %s" % (row.use.widget, row.words, summary)
    return "%s  %s" % (row.use.widget, row.words)


class LogicPanel(QWidget):
    def __init__(self, workbench: Any) -> None:
        super().__init__(workbench)
        self.setObjectName("formBuilder.logic")
        self.setMinimumWidth(0)
        self.setSizePolicy(_policy("Preferred"), _policy("Expanding"))  # type: ignore[arg-type]
        self._workbench = workbench
        self._session = workbench._session
        self._book: Optional[LogicBook] = None
        self._published: Optional[Tuple[int, int, str, str]] = None
        self._filename = ""
        self._tokens: object = None
        self._rows: List[_Row] = []
        self._chips = {}
        column = QVBoxLayout(self)
        column.setContentsMargins(4, 4, 4, 4)
        column.setSpacing(4)
        self._filter = QLineEdit(self)
        self._filter.setObjectName("formBuilder.logic.filter")
        self._filter.setPlaceholderText("Filter")
        self._filter.setAccessibleName("Filter logic")
        self._filter.setMinimumWidth(0)
        self._filter.setSizePolicy(_policy("Ignored"), _policy("Fixed"))  # type: ignore[arg-type]
        self._filter.setClearButtonEnabled(False)
        self._filter.textChanged.connect(self._fill)
        column.addWidget(self._filter)
        chips = QWidget(self)
        chips.setMinimumWidth(0)
        grid = QGridLayout(chips)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(2)
        for index, (key, label) in enumerate(_CHIPS):
            box = QToolButton(chips)
            box.setText(label)
            box.setCheckable(True)
            box.setChecked(True)
            box.setAutoRaise(False)
            box.setObjectName("formBuilder.logic.chip.%s" % key)
            box.setMinimumWidth(0)
            box.setSizePolicy(_policy("Ignored"), _policy("Preferred"))  # type: ignore[arg-type]
            box.toggled.connect(self._fill)
            self._chips[key] = box
            grid.addWidget(box, index // 2, index % 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        column.addWidget(chips)
        self._count = QLabel(self)
        self._count.setObjectName("formBuilder.logic.problemCount")
        self._count.setMinimumWidth(0)
        self._count.hide()
        column.addWidget(self._count)
        self._scroll = QScrollArea(self)
        self._scroll.setObjectName("formBuilder.logic.scroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(_frame())
        self._scroll.setHorizontalScrollBarPolicy(_OFF)  # type: ignore[arg-type]
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

    @property
    def tokens(self) -> object:
        return self._tokens

    def minimumSizeHint(self) -> object:  # noqa: N802
        from app.qt.QtCore import QSize

        return QSize(0, 80)

    def apply_theme(self, tokens: object) -> None:
        self._tokens = tokens
        width = int(tokens.focus_border_width)  # type: ignore[attr-defined]
        self.setStyleSheet(
            "QWidget#formBuilder\\.logic { background: %s; color: %s; }"
            "QWidget#formBuilder\\.logic\\.body { background: %s; color: %s; }"
            "QLabel { color: %s; background: transparent; }"
            "QLabel#formBuilder\\.logic\\.title {"
            " color: %s; background: transparent; border: none;"
            " font-size: 10px; font-weight: 600; letter-spacing: 0.5px; }"
            "QLabel#formBuilder\\.logic\\.note, QLabel#formBuilder\\.logic\\.problemCount { color: %s; }"
            "QLabel[problem=\"true\"] { color: %s; }"
            "QLineEdit#formBuilder\\.logic\\.filter { background: %s; color: %s; border: 1px solid %s; }"
            "QLineEdit#formBuilder\\.logic\\.filter:focus { border: %dpx solid %s; }"
            "QToolButton { color: %s; background: %s; border: 1px solid %s; padding: 2px 6px; }"
            "QToolButton:checked { color: %s; background: %s; border: %dpx solid %s; }"
            "QToolButton:focus { border: %dpx solid %s; }"
            "QLabel[logicRow=\"true\"]:focus { border: %dpx solid %s; }"
            "QScrollArea#formBuilder\\.logic\\.scroll { background: %s; border: none; }"
            % (
                tokens.panel_bg,  # type: ignore[attr-defined]
                tokens.text_primary,  # type: ignore[attr-defined]
                tokens.panel_bg,  # type: ignore[attr-defined]
                tokens.text_primary,  # type: ignore[attr-defined]
                tokens.text_primary,  # type: ignore[attr-defined]
                tokens.text_muted,  # type: ignore[attr-defined]
                tokens.text_muted,  # type: ignore[attr-defined]
                tokens.accent,  # type: ignore[attr-defined]
                tokens.input_bg,  # type: ignore[attr-defined]
                tokens.text_primary,  # type: ignore[attr-defined]
                tokens.border,  # type: ignore[attr-defined]
                width,
                tokens.accent,  # type: ignore[attr-defined]
                tokens.text_primary,  # type: ignore[attr-defined]
                tokens.input_bg,  # type: ignore[attr-defined]
                tokens.border,  # type: ignore[attr-defined]
                tokens.text_primary,  # type: ignore[attr-defined]
                tokens.panel_bg,  # type: ignore[attr-defined]
                width,
                tokens.accent,  # type: ignore[attr-defined]
                width,
                tokens.accent,  # type: ignore[attr-defined]
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
        key = cache_key(document, source, relative)
        book = collect(document, env, source, relative)
        if key != self._published:
            self._session.diagnostics.publish("logic.code", book.diagnostics)
            self._published = key
        self._book = book
        base = os.path.basename(relative) if relative else ""
        self._filename = base
        self._show_count(book)
        self._fill()

    def _on_log(self, _change: object) -> None:
        # A document edit must not parse the window file inside the gesture's
        # processEvents. The list catches up when the loop next goes idle.
        if self._idle or self._session is None:
            return
        self._idle = True
        from app.shell.idle_turn import run_when_idle

        run_when_idle(self._reload_idle)

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

    def _show_count(self, book: LogicBook) -> None:
        count = sum(1 for item in book.diagnostics if item.code == "FB207")
        if count <= 0:
            self._count.hide()
            self._count.setText("")
            return
        self._count.setText("1 problem" if count == 1 else "%d problems" % count)
        self._count.show()

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
        if self._query().text and not rows:
            self._message("Nothing matches \u201c%s\u201d." % self._query().text)
            return
        grouped = {name: [] for name in _ORDER}  # type: ignore[var-annotated]
        for row in rows:
            grouped.setdefault(row.section, []).append(row)
        number = 0
        for section in _ORDER:
            items = grouped.get(section) or []
            if not items:
                continue
            self._heading(section)
            for row in items:
                label = _Row(self, row, number)
                self._body_layout.addWidget(label)
                self._rows.append(label)
                number += 1
        self._body_layout.addStretch(1)

    def _heading(self, section: str) -> None:
        overline = QWidget(self._body)
        overline.setObjectName("formBuilder.logic.overline")
        overline.setMinimumWidth(0)
        heading = QHBoxLayout(overline)
        heading.setContentsMargins(0, 4, 0, 0)
        heading.setSpacing(0)
        if section == "IN YOUR CODE":
            title_text = "IN YOUR CODE (read-only, found in %s)" % (self._filename or "the window file")
        else:
            title_text = section
        title = ElidedLabel(title_text, overline)
        title.setObjectName("formBuilder.logic.title")
        heading.addWidget(title, 1)
        self._body_layout.addWidget(overline)
        if section == "IN YOUR CODE":
            note = QLabel(_NOTE, self._body)
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
    from app.features.form_builder.integration.overlay_ext.connections import window_file

    base = window_file(surface)
    folder = os.path.dirname(str(getattr(surface, "_path", "") or ""))
    if not base or not folder:
        return "", base or ""
    path = os.path.join(folder, base)
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read(), base
    except OSError:
        return "", base
