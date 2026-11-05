"""The Logic panel: filter, wrapping chips, and one two-line row per anchor."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

from app.qt.QtCore import QEvent, QSize, Qt
from app.qt.QtGui import QIcon
from app.qt.qt_compat import enum_value
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
from app.features.form_builder.qtside.canvas.layers.logic_badges import set_logic_tab
from app.features.form_builder.qtside.icons.glyphs import paint_glyph
from app.features.form_builder.qtside.logic_panel.rows import LogicRow, RowFace, paint_roles
from app.features.form_builder.qtside.theme.chrome import FormChrome, chrome_from_values
from app.features.form_builder.qtside.theme.metrics import CONTROL, ICON_BUTTON_HEADER, R_CONTROL, S4
from app.features.form_builder.qtside.theme.section_header import SectionHeader
from app.features.form_builder.qtside.theme.segmented import SegmentedControl

_PLAIN = getattr(getattr(Qt, "TextFormat", Qt), "PlainText")
_NO_FOCUS = getattr(getattr(Qt, "FocusPolicy", Qt), "NoFocus")
_KEY_PRESS = getattr(getattr(QEvent, "Type", QEvent), "KeyPress")
_KEY_DOWN = enum_value(getattr(getattr(Qt, "Key", Qt), "Key_Down"))
_KEY_UP = enum_value(getattr(getattr(Qt, "Key", Qt), "Key_Up"))
_EMPTY = "This form has no rules, checks, or events yet. Select a widget and open Behavior to add one."
_NOTE = "Read from the window file. This list is best-effort and Code Studio does not run the file."
_ORDER = ("STATE", "CHECKS", "EVENTS", "IN YOUR CODE")
_SEGMENTS = ("All", "Rules", "Checks", "Events")
_IDLE = None  # type: ignore[var-annotated]
_SPEAK = {
    "cbcsEnabledWhen": "condition",
    "cbcsVisibleWhen": "condition",
    "cbcsReadOnlyWhen": "condition",
    "cbcsValue": "value",
    "cbcsDefault": "value",
}


def set_idle_runner(runner: Any) -> None:
    """Integration registers the shell idle hook. This module cannot import the shell."""
    global _IDLE
    _IDLE = runner


def _policy(name: str) -> object:
    names = getattr(QSizePolicy, "Policy", QSizePolicy)
    return getattr(names, name)


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
        self._form_chrome: Optional[FormChrome] = None
        self._rows: List[LogicRow] = []
        column = QVBoxLayout(self)
        column.setContentsMargins(4, 4, 4, 4)
        column.setSpacing(4)
        link_row = QHBoxLayout()
        link_row.setContentsMargins(0, 0, 0, 0)
        column.addLayout(link_row)
        link_row.addStretch(1)
        self._read = QToolButton(self)
        self._read.setObjectName("formBuilder.logic.readAsText")
        self._read.setText("")
        self._read.setToolTip("Read as text")
        self._read.setAccessibleName("Read as text")
        self._read.setAutoRaise(True)
        self._read.setFixedSize(ICON_BUTTON_HEADER, ICON_BUTTON_HEADER)
        self._read.clicked.connect(self._open_behavior_text)
        link_row.addWidget(self._read)
        self._filter = QLineEdit(self)
        self._filter.setObjectName("formBuilder.logic.filter")
        self._filter.setPlaceholderText("Filter")
        self._filter.setAccessibleName("Filter logic")
        self._filter.setMinimumWidth(0)
        self._filter.setFixedHeight(CONTROL)
        self._filter.setSizePolicy(_policy("Ignored"), _policy("Fixed"))  # type: ignore[arg-type]
        self._filter.setClearButtonEnabled(False)
        self._filter.textChanged.connect(self._fill)
        column.addWidget(self._filter)
        self._segments = SegmentedControl(self)
        self._segments.setObjectName("formBuilder.logic.segments")
        self._segments.setAccessibleName("Logic filter")
        self._segments.set_items(
            _SEGMENTS,
            tooltips=("Show all", "Show rules", "Show checks", "Show events"),
            names=("All logic", "Show rules", "Show checks", "Show events"),
        )
        self._segments.current_changed.connect(self._fill)
        column.addWidget(self._segments)
        self._scroll = QScrollArea(self)
        self._scroll.setObjectName("formBuilder.logic.scroll")
        self._scroll.setAccessibleName("Logic list")
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
        self._scroll.setFocusPolicy(_NO_FOCUS)
        viewport = self._scroll.viewport()
        if viewport is not None:
            viewport.setFocusPolicy(_NO_FOCUS)
        self._filter.installEventFilter(self)
        column.addWidget(self._scroll, 1)
        self._idle = False
        self._row_key: Optional[Tuple[object, ...]] = None
        self._sub = self._session.log.subscribe(self._on_log, priority=PRIORITY_VIEWS)
        self.destroyed.connect(lambda *_args: self._sub.close())
        self.reload()

    def book(self) -> Optional[LogicBook]:
        return self._book

    def showEvent(self, event: QEvent) -> None:  # noqa: N802
        super().showEvent(event)
        set_logic_tab(True)

    def hideEvent(self, event: QEvent) -> None:  # noqa: N802
        super().hideEvent(event)
        set_logic_tab(False)

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
        return QSize(0, self.section_need())

    def section_need(self) -> int:
        """Chrome plus the empty sentence. A long list keeps a window and scrolls inside."""

        width = max(self.width(), 184)
        content = 0
        for index in range(self._body_layout.count()):
            item = self._body_layout.itemAt(index)
            widget = item.widget() if item is not None else None
            if widget is None or not widget.isVisible():
                continue
            if widget.hasHeightForWidth():
                content += widget.heightForWidth(width)
            else:
                content += widget.sizeHint().height()
            content += 2
        if content > 160:
            content = 120
        return (
            self._read.sizeHint().height()
            + self._filter.sizeHint().height()
            + self._segments.sizeHint().height()
            + content
            + 20
        )

    def resizeEvent(self, event: object) -> None:  # noqa: N802
        super().resizeEvent(event)  # type: ignore[arg-type]
        self._ask_arrange()

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
            "QLineEdit#formBuilder\\.logic\\.filter { background: %s; color: %s; border: 1px solid %s;"
            " border-radius: %dpx; }"
            "QLineEdit#formBuilder\\.logic\\.filter:focus { border: %dpx solid %s; }"
            "QToolButton#formBuilder\\.logic\\.readAsText { color: %s; background: transparent;"
            " border: none; border-radius: 0; padding: 0; }"
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
                R_CONTROL,
                width,
                tokens.accent,  # type: ignore[attr-defined]
                tokens.text_muted,  # type: ignore[attr-defined]
                width,
                tokens.accent,  # type: ignore[attr-defined]
                tokens.panel_bg,  # type: ignore[attr-defined]
            )
        )
        self._form_chrome = _form_chrome(tokens)
        self._segments.apply_chrome(self._form_chrome)
        self._paint_search(self._form_chrome.icon_muted or chrome.faint)
        self._paint_read(self._form_chrome.icon_muted or chrome.faint)
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

    def eventFilter(self, watched: QWidget, event: QEvent) -> bool:  # noqa: N802
        # Down in the filter only moves the text caret. The list treats it as "first row".
        if int(event.type()) != int(_KEY_PRESS):
            return False
        key = enum_value(event.key())  # type: ignore[attr-defined]
        if watched is self._filter and key == _KEY_DOWN and self._rows:
            self._focus_row(self._rows[0])
            return True
        try:
            index = self._rows.index(watched)  # type: ignore[arg-type]
        except ValueError:
            return False
        if key == _KEY_DOWN and index + 1 < len(self._rows):
            self._focus_row(self._rows[index + 1])
            return True
        if key == _KEY_UP:
            if index == 0:
                self._filter.setFocus()
            else:
                self._focus_row(self._rows[index - 1])
            return True
        return False

    def _focus_row(self, row: QWidget) -> None:
        self._scroll.ensureWidgetVisible(row)
        row.setFocus()

    def _chain_focus(self) -> None:
        previous: QWidget = self._filter
        QWidget.setTabOrder(previous, self._segments)
        previous = self._segments
        for row in self._rows:
            QWidget.setTabOrder(previous, row)
            previous = row

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
        index = self._segments.current_index()
        return PanelQuery(
            text=self._filter.text(),
            rules=index in (0, 1),
            checks=index in (0, 2),
            events=index in (0, 3),
            problems=True,
        )

    def _fill(self, *_args: object) -> None:
        book = self._book
        if book is None:
            self._clear_body()
            self._ask_arrange()
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
            tuple(
                (
                    row.section,
                    self._shown(row.use.widget),
                    row.words,
                    row.summary,
                    _spoken_rule(row.summary, row.use.property_key, self._env),
                    row.problem,
                )
                for row in rows
            ),
        )
        if key == self._row_key and self._body_layout.count():
            return
        self._row_key = key
        self._clear_body()
        if not panel_rows(book, PanelQuery()) and not rows:
            self._message(_EMPTY)
            self._ask_arrange()
            return
        if query.text and not rows:
            self._message("Nothing matches \u201c%s\u201d." % query.text)
            self._ask_arrange()
            return
        grouped: Dict[str, List[PanelRow]] = {name: [] for name in _ORDER}
        for row in rows:
            grouped.setdefault(row.section, []).append(row)
        number = 0
        for section in _ORDER:
            items = grouped.get(section) or []
            if not items:
                continue
            problems = sum(1 for row in items if row.problem)
            self._heading(section, problems)
            for row in items:
                number = self._add_row(row, number)
        self._body_layout.addStretch(1)
        self._paint_rows()
        self._chain_focus()
        self._ask_arrange()

    def _ask_arrange(self) -> None:
        if self.minimumHeight() >= self.section_need():
            return
        workbench = self._workbench
        if getattr(workbench, "_arranging_left", False):
            return
        arrange = getattr(workbench, "_arrange_left", None)
        if callable(arrange):
            arrange()

    def _add_row(self, row: PanelRow, number: int, section: str = "") -> int:
        use = row.use
        face = _face(row, self._shown(use.widget), section, self._env)
        label = LogicRow(face, self._body, lambda use=use: self.open_row(use))  # type: ignore[misc]
        label.use = use  # type: ignore[attr-defined]
        label.setObjectName("formBuilder.logic.row.%d" % number)
        label.installEventFilter(self)
        self._body_layout.addWidget(label)
        self._rows.append(label)
        return number + 1

    def _heading(self, section: str, problems: int = 0) -> None:
        title = SectionHeader(self._body, section)
        title.setObjectName("formBuilder.logic.title")
        if problems:
            title.set_count(problems)
            title.setProperty("formBuilderProblemCount", problems)
        self._style_header(title)
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
        from app.features.form_builder.engine.logic.read_as_text import widget_name

        document = self._session.document if self._session is not None else None
        return widget_name(document, name, self._env)

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
                str(getattr(tokens, "accent", "") or ""),
                int(getattr(tokens, "focus_border_width", 2) or 2),
            )
        for index in range(self._body_layout.count()):
            item = self._body_layout.itemAt(index)
            widget = item.widget() if item is not None else None
            if isinstance(widget, SectionHeader):
                self._style_header(widget)

    def _style_header(self, header: SectionHeader) -> None:
        chrome = self._form_chrome
        if chrome is None:
            return
        header.apply_chrome(chrome)
        count = header.property("formBuilderProblemCount")
        if not count:
            return
        label = header.findChild(QLabel, "formBuilder.sectionCount")
        if label is None:
            return
        color = chrome.error or chrome.warning
        if color:
            label.setStyleSheet("QLabel#formBuilder.sectionCount { color: %s; }" % color)

    def _paint_search(self, color: str) -> None:
        actions = getattr(self._filter, "actions", None)
        if callable(actions):
            for action in list(actions()):
                self._filter.removeAction(action)
        if not color:
            return
        ratio = float(getattr(self, "devicePixelRatioF", lambda: 1.0)())
        icon = QIcon(paint_glyph("search", color, 16, ratio))
        position = getattr(getattr(QLineEdit, "ActionPosition", QLineEdit), "LeadingPosition")
        self._filter.addAction(icon, position)

    def _paint_read(self, color: str) -> None:
        if not color:
            return
        ratio = float(getattr(self, "devicePixelRatioF", lambda: 1.0)())
        self._read.setIcon(QIcon(paint_glyph("behavior", color, 16, ratio)))
        self._read.setIconSize(QSize(16, 16))

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


def _form_chrome(tokens: object) -> FormChrome:
    text = str(getattr(tokens, "text_primary", "") or "")
    return chrome_from_values(
        window=str(getattr(tokens, "window_bg", "") or getattr(tokens, "panel_bg", "") or ""),
        panel=str(getattr(tokens, "panel_bg", "") or ""),
        text=text,
        muted=str(getattr(tokens, "text_muted", "") or text),
        faint=str(getattr(tokens, "gutter_text", "") or ""),
        border=str(getattr(tokens, "border", "") or ""),
        accent=str(getattr(tokens, "accent", "") or ""),
        row_hover=str(getattr(tokens, "tree_hover_bg", "") or ""),
        input_bg=str(getattr(tokens, "input_bg", "") or ""),
        error=str(getattr(tokens, "diag_error_color", "") or ""),
        focus_width=int(getattr(tokens, "focus_border_width", 1) or 1),
        selected=str(getattr(tokens, "tree_selected_bg", "") or ""),
        glyph=str(getattr(tokens, "icon_primary", "") or text),
        icon_muted=str(getattr(tokens, "icon_muted", "") or ""),
        is_dark=bool(getattr(tokens, "is_dark", False)),
        is_high_contrast=bool(getattr(tokens, "is_high_contrast", False)),
        warning=str(getattr(tokens, "diag_warning_color", "") or ""),
    )


def _spoken_rule(summary: str, key: str, env: object) -> str:
    """The engine speaker, or "" when the builder cannot say this formula."""
    kind = _SPEAK.get(key, "")
    text = summary.strip()
    if not kind or env is None or not text:
        return ""
    from app.features.form_builder.engine.logic.formula.speak import speak_text

    try:
        return speak_text(text, env, kind)  # type: ignore[arg-type]
    except Exception:
        return ""


def _face(row: PanelRow, display: str, section: str = "", env: object = None) -> RowFace:
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
        aside = "· %s" % row.words.strip() if row.words and row.words.strip() else ""
        indent = S4 if row.section == "EVENTS" else 0
        return RowFace(display, aside, body, True, False, tooltip, accessible, indent)
    if row.section == "STATE":
        raw = row.summary.strip()
        spoken = _spoken_rule(raw, use.property_key, env)
        tip = raw or tooltip
        if spoken:
            aside = "%s · %s" % (row.words, spoken) if row.words else spoken
            heard = "%s, %s, %s, %s" % (where, use.widget, row.words, spoken)
            return RowFace(display, aside, "", False, False, tip, heard)
        heard = "%s, %s, %s, %s" % (where, use.widget, row.words, raw)
        return RowFace(display, row.words, raw, True, False, tip, heard)
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
