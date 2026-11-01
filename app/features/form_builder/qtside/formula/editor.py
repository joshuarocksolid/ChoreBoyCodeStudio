"""The formula field (UX-FX-001 .. 003). One QPlainTextEdit, no gutter."""

from __future__ import annotations

import io
import tokenize
from typing import Optional, Sequence, Tuple

from app.qt.QtCore import QEvent, QPoint, QTimer, Qt
from app.qt.QtGui import QColor, QSyntaxHighlighter, QTextCharFormat, QTextCursor
from app.qt.QtWidgets import QListWidget, QListWidgetItem, QPlainTextEdit, QTextEdit, QWidget
from app.qt.qt_compat import enum_value

from app.features.form_builder.engine.diagnostics import CODES, Severity
from app.features.form_builder.engine.logic.formula import analyze, apply_fix, normalize
from app.features.form_builder.engine.logic.formula.env import FormulaEnv, SlotKind
from app.features.form_builder.engine.logic.formula.library import FUNCTIONS
from app.features.form_builder.engine.logic.formula.nodes import Analysis, Fix
from app.features.form_builder.engine.logic.formula.types import FKind, type_phrase
from app.features.form_builder.qtside.formula.complete import Completion, completions
from app.features.form_builder.qtside.formula.now import as_words, now_text
from app.features.form_builder.qtside.theme.chrome import FormChrome, default_chrome

_ENTER = frozenset({enum_value(Qt.Key.Key_Return), enum_value(Qt.Key.Key_Enter)})
_ESC = enum_value(Qt.Key.Key_Escape)
_TAB = enum_value(Qt.Key.Key_Tab)
_SPACE = enum_value(Qt.Key.Key_Space)
_PERIOD = enum_value(Qt.Key.Key_Period)
_UP = enum_value(Qt.Key.Key_Up)
_DOWN = enum_value(Qt.Key.Key_Down)
_CTRL = enum_value(Qt.KeyboardModifier.ControlModifier)
_SHIFT = enum_value(Qt.KeyboardModifier.ShiftModifier)
_KEYWORDS = frozenset({"and", "or", "not", "if", "else", "in"})
_MAX_LINES = 6
_KEY_PRESS = enum_value(getattr(getattr(QEvent, "Type", QEvent), "KeyPress"))
_KEEP = getattr(getattr(QTextCursor, "MoveMode", QTextCursor), "KeepAnchor")
_END = getattr(getattr(QTextCursor, "MoveOperation", QTextCursor), "End")
_UNDERLINE = getattr(QTextCharFormat, "UnderlineStyle", QTextCharFormat)
# WaveUnderline and SpellCheckUnderline keep the color on the format but this
# Qt build does not paint them. SingleUnderline does paint underlineColor.
_SOLID = getattr(_UNDERLINE, "SingleUnderline")
_DOT = getattr(_UNDERLINE, "DotLine")
_ELIDE = getattr(getattr(Qt, "TextElideMode", Qt), "ElideRight")
_ESC_SENTENCE = "Fix or press Esc to undo this formula"


class _Highlighter(QSyntaxHighlighter):
    def __init__(self, document: object) -> None:
        super().__init__(document)  # type: ignore[arg-type]
        self._colors = {
            "name": "",
            "number": "",
            "string": "",
            "operator": "",
            "function": "",
            "keyword": "",
        }

    def set_colors(self, chrome: FormChrome) -> None:
        self._colors = {
            "name": chrome.syntax_name,
            "number": chrome.syntax_number,
            "string": chrome.syntax_string,
            "operator": chrome.syntax_operator,
            "function": chrome.syntax_function,
            "keyword": chrome.syntax_keyword,
        }
        self.rehighlight()

    def highlightBlock(self, text: str) -> None:  # noqa: N802
        if not text or not any(self._colors.values()):
            return
        try:
            tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
        except (tokenize.TokenError, IndentationError, SyntaxError):
            return
        for tok in tokens:
            if tok.type in (tokenize.ENCODING, tokenize.ENDMARKER, tokenize.NEWLINE, tokenize.NL):
                continue
            role = _role(tok)
            color = self._colors.get(role, "")
            if not color:
                continue
            start = tok.start[1]
            length = max(0, tok.end[1] - start)
            if length <= 0 or start < 0 or start >= len(text):
                continue
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(color))
            self.setFormat(start, length, fmt)


def _role(tok: tokenize.TokenInfo) -> str:
    if tok.type == tokenize.NUMBER:
        return "number"
    if tok.type == tokenize.STRING:
        return "string"
    if tok.type == tokenize.OP:
        return "operator"
    if tok.type == tokenize.NAME:
        if tok.string in _KEYWORDS:
            return "keyword"
        if tok.string in FUNCTIONS:
            return "function"
        return "name"
    return ""


class FormulaEditor(QPlainTextEdit):
    """Analysis, completion, and underlines. The State row commits and cancels."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.formula")
        self.setTabChangesFocus(True)
        wrap = getattr(getattr(QPlainTextEdit, "LineWrapMode", QPlainTextEdit), "WidgetWidth")
        self.setLineWrapMode(wrap)
        hidden = getattr(getattr(Qt, "ScrollBarPolicy", Qt), "ScrollBarAlwaysOff")
        self.setHorizontalScrollBarPolicy(hidden)
        self.setMinimumWidth(0)
        self._fitting = False
        self._placing = False
        self._reflowing = False
        self._highlighter = _Highlighter(self.document())
        self._chrome = default_chrome()
        self._env: Optional[FormulaEnv] = None
        self._slot = SlotKind.condition()
        self._reader: object = None
        self._analysis: Optional[Analysis] = None
        self._now = "blank"
        self._words = ""
        self._rows: Tuple[Completion, ...] = ()
        self._fixes: Tuple[Fix, ...] = ()
        self._floating: Optional[QListWidget] = None
        self._suppress = False
        self._status: Optional[QWidget] = None
        self._complete = QListWidget(self)
        self._complete.setObjectName("formBuilder.formula.complete")
        self._complete.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._complete.hide()
        self._fix_list = QListWidget(self)
        self._fix_list.setObjectName("formBuilder.formula.fixes")
        self._fix_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._fix_list.hide()
        self.textChanged.connect(self._on_text)
        self._fit()

    def lists(self) -> Tuple[QListWidget, QListWidget]:
        return (self._complete, self._fix_list)

    def hide_lists(self) -> None:
        self._dismiss(self._complete)
        self._dismiss(self._fix_list)

    def set_status_label(self, label: QWidget) -> None:
        self._status = label

    def set_chrome(self, chrome: FormChrome) -> None:
        self._chrome = chrome
        self._highlighter.set_colors(chrome)
        if chrome.text and chrome.input:
            name = (self.objectName() or "formBuilder.formula").replace("\\", "\\\\").replace(".", "\\.")
            focus = chrome.focus_width if chrome.focus_width > 0 else 1
            ink = chrome.accent or chrome.text
            self.setStyleSheet(
                "QPlainTextEdit#%s { color: %s; background: %s; border: 1px solid %s; }"
                "QPlainTextEdit#%s:focus { border: %dpx solid %s; }"
                % (name, chrome.text, chrome.input, chrome.border, name, focus, ink)
            )
        self._paint_list(self._complete)
        self._paint_list(self._fix_list)
        self._underlines()

    def set_context(self, env: FormulaEnv, slot: SlotKind, reader: object) -> None:
        self._env = env
        self._slot = slot
        self._reader = reader
        self._reanalyze()

    def show_text(self, text: str) -> None:
        self._suppress = True
        self.setPlainText(text)
        self._place_cursor(len(text))
        self._suppress = False
        self._dismiss(self._complete)
        self._dismiss(self._fix_list)
        self._fit()

    def analysis(self) -> Optional[Analysis]:
        return self._analysis

    def has_error(self) -> bool:
        # A blank field is a clear, even though analyze calls it unfinished.
        if normalize(self.toPlainText()) == "":
            return False
        found = self._analysis
        if found is None:
            return True
        return _errored(found)

    def status_text(self) -> str:
        found = self._analysis
        if found is None:
            return ""
        text = self.toPlainText()
        if normalize(text) == "":
            return ""
        problem = _lead_problem(found)
        if problem is not None and _severity(problem.code) is Severity.ERROR:
            return "%s\n%s" % (problem.message, _ESC_SENTENCE)
        phrase = _type_words(found)
        line = "%s    now: %s" % (phrase, self._now) if phrase else "now: %s" % self._now
        words = self._words.strip()
        raw = text.strip()
        if words and words != raw:
            line = "%s\n%s" % (line, words)
        if problem is not None:
            line = "%s\n%s" % (line, problem.message)
        return line

    def event(self, event: object) -> bool:  # noqa: N802
        kind = enum_value(event.type())  # type: ignore[attr-defined]
        if kind == _KEY_PRESS and self._tab_takes_row(event):
            if self._fix_list.isVisible():
                self._accept_fix()
            else:
                self._accept()
            event.accept()  # type: ignore[attr-defined]
            return True
        return bool(super().event(event))  # type: ignore[arg-type]

    def _tab_takes_row(self, event: object) -> bool:
        key = enum_value(event.key())  # type: ignore[attr-defined]
        mods = enum_value(event.modifiers())  # type: ignore[attr-defined]
        if key != _TAB or bool(mods & _CTRL):
            return False
        if self._fix_list.isVisible() and self._fix_list.count():
            return True
        return self._complete.isVisible() and self._complete.count() > 0

    def keyPressEvent(self, event: object) -> None:  # noqa: N802
        key = enum_value(event.key())  # type: ignore[attr-defined]
        mods = enum_value(event.modifiers())  # type: ignore[attr-defined]
        ctrl = bool(mods & _CTRL)
        shift = bool(mods & _SHIFT)
        if key == _ESC:
            if self._fix_list.isVisible():
                self._dismiss(self._fix_list)
            elif self._complete.isVisible():
                self._dismiss(self._complete)
            else:
                self.cancel_requested()
            event.accept()  # type: ignore[attr-defined]
            return
        if key == _PERIOD and ctrl:
            self._fix_key()
            event.accept()  # type: ignore[attr-defined]
            return
        if key == _SPACE and ctrl:
            self._offer(True)
            event.accept()  # type: ignore[attr-defined]
            return
        if key in _ENTER and ctrl:
            self.commit_requested()
            event.accept()  # type: ignore[attr-defined]
            return
        if key in _ENTER and shift:
            if self.document().blockCount() >= _MAX_LINES:
                event.accept()  # type: ignore[attr-defined]
                return
            cursor = self.textCursor()
            cursor.insertText("\n")
            self.setTextCursor(cursor)
            self._fit()
            event.accept()  # type: ignore[attr-defined]
            return
        if key in _ENTER:
            if self._fix_list.isVisible() and self._fix_list.count():
                self._accept_fix()
            elif self._complete.isVisible() and self._complete.count():
                self._accept()
            event.accept()  # type: ignore[attr-defined]
            return
        if key == _TAB and not ctrl and self._complete.isVisible() and self._complete.count():
            self._accept()
            event.accept()  # type: ignore[attr-defined]
            return
        if key in (_UP, _DOWN) and self._complete.isVisible() and self._complete.count():
            self._move(self._complete, -1 if key == _UP else 1)
            event.accept()  # type: ignore[attr-defined]
            return
        if key in (_UP, _DOWN) and self._fix_list.isVisible() and self._fix_list.count():
            self._move(self._fix_list, -1 if key == _UP else 1)
            event.accept()  # type: ignore[attr-defined]
            return
        super().keyPressEvent(event)  # type: ignore[arg-type]

    def cancel_requested(self) -> None:
        host = getattr(self, "_on_cancel", None)
        if callable(host):
            host()

    def commit_requested(self) -> None:
        host = getattr(self, "_on_commit", None)
        if callable(host):
            host()

    def set_handlers(self, on_commit: object, on_cancel: object) -> None:
        self._on_commit = on_commit
        self._on_cancel = on_cancel

    def _on_text(self) -> None:
        self._fit()
        self._reanalyze()
        if self._suppress:
            self._dismiss(self._complete)
            return
        self._offer(False)

    def _reanalyze(self) -> None:
        env = self._env
        if env is None:
            self._analysis = None
            self._now = "blank"
            self._words = ""
        else:
            self._analysis = analyze(self.toPlainText(), env, self._slot)
            self._now = now_text(self._analysis, env, self._reader)
            self._words = as_words(self.toPlainText(), env)
        self._underlines()
        self._publish_status()

    def _offer(self, forced: bool) -> None:
        env = self._env
        if env is None:
            self._dismiss(self._complete)
            return
        cursor = self.textCursor().position()
        self._rows = completions(self.toPlainText(), cursor, env, forced=forced)
        if not self._rows:
            self._dismiss(self._complete)
            return
        self._fill(self._complete, [row.label for row in self._rows])
        self._dismiss(self._fix_list)
        self._popup(self._complete)

    def _accept(self) -> None:
        index = self._complete.currentRow()
        if index < 0 or index >= len(self._rows):
            return
        row = self._rows[index]
        text = self.toPlainText()
        cursor = self.textCursor().position()
        start = max(0, min(row.start, len(text)))
        if start > cursor:
            start = cursor
        merged = text[:start] + row.insert + text[cursor:]
        self._suppress = True
        self.setPlainText(merged)
        self._place_cursor(start + len(row.insert))
        self._suppress = False
        self._dismiss(self._complete)
        self._rows = ()

    def _fix_key(self) -> None:
        found = self._analysis
        fixes = () if found is None else found.fixes
        if len(fixes) == 1:
            self._apply(fixes[0])
            return
        if len(fixes) > 1:
            self._fixes = fixes
            self._fill(self._fix_list, [fix.message for fix in fixes])
            self._dismiss(self._complete)
            self._popup(self._fix_list)

    def _accept_fix(self) -> None:
        index = self._fix_list.currentRow()
        if index < 0 or index >= len(self._fixes):
            return
        self._apply(self._fixes[index])

    def _apply(self, fix: Fix) -> None:
        text = apply_fix(self.toPlainText(), fix)
        self._suppress = True
        self.setPlainText(text)
        self._place_cursor(len(text))
        self._suppress = False
        self._dismiss(self._fix_list)
        self._fixes = ()
        self._reanalyze()

    def _underlines(self) -> None:
        found = self._analysis
        if found is None or normalize(self.toPlainText()) == "":
            self.setExtraSelections([])
            return
        extras = []
        for problem in found.problems:
            if problem.span.end <= problem.span.start:
                continue
            severity = _severity(problem.code)
            if severity is Severity.WARNING:
                color = self._chrome.warning
                style = _SOLID
            elif severity is Severity.INFO:
                color = self._chrome.info
                style = _DOT
            else:
                color = self._chrome.error
                style = _SOLID
            if not color:
                continue
            cursor = self.textCursor()
            cursor.setPosition(min(problem.span.start, len(self.toPlainText())))
            cursor.setPosition(min(problem.span.end, len(self.toPlainText())), _KEEP)
            extra = QTextEdit.ExtraSelection()
            extra.format.setUnderlineStyle(style)
            extra.format.setUnderlineColor(QColor(color))
            extra.cursor = cursor
            extras.append(extra)
        self.setExtraSelections(extras)

    def _fill(self, widget: QListWidget, labels: Sequence[str]) -> None:
        widget.clear()
        for label in labels:
            widget.addItem(QListWidgetItem(label))
        if widget.count():
            widget.setCurrentRow(0)
        widget.setFixedHeight(min(6, max(1, widget.count())) * 22 + 4)

    def _move(self, widget: QListWidget, delta: int) -> None:
        row = widget.currentRow() + delta
        if widget.count():
            widget.setCurrentRow(max(0, min(widget.count() - 1, row)))

    def _place_cursor(self, position: int) -> None:
        cursor = self.textCursor()
        cursor.setPosition(max(0, min(position, len(self.toPlainText()))))
        self.setTextCursor(cursor)

    def _publish_status(self) -> None:
        label = self._status
        if label is None or not hasattr(label, "setText"):
            return
        text = self.status_text()
        label.setToolTip(text)  # type: ignore[attr-defined]
        label.setWordWrap(True)  # type: ignore[attr-defined]
        label.setText(text)  # type: ignore[attr-defined]
        if text:
            label.setVisible(True)  # type: ignore[attr-defined]
        label.setMinimumHeight(0)  # type: ignore[attr-defined]
        measure = int(label.contentsRect().width())  # type: ignore[attr-defined]
        if measure >= 20 and bool(label.hasHeightForWidth()):  # type: ignore[attr-defined]
            needed = int(label.heightForWidth(measure))  # type: ignore[attr-defined]
            if needed > 0:
                label.setMinimumHeight(needed)  # type: ignore[attr-defined]
        self._reflow_block()

    def _dismiss(self, widget: QListWidget) -> None:
        if self._floating is widget:
            self._floating = None
        widget.hide()
        widget.setMinimumWidth(0)
        widget.setMaximumWidth(16777215)

    def _popup(self, widget: QListWidget) -> None:
        self._floating = widget
        self._place_popup()
        QTimer.singleShot(0, self._place_popup)

    def _place_popup(self) -> None:
        widget = self._floating
        if widget is None or self._placing:
            return
        self._placing = True
        try:
            self._place_popup_now(widget)
        finally:
            self._placing = False

    def _place_popup_now(self, widget: QListWidget) -> None:
        host = self._popup_host()
        if widget.parentWidget() is not host:
            widget.setParent(host)
        self._paint_list(widget)
        self._publish_status()
        pad = self.parentWidget()
        if pad is not None and pad.layout() is not None:
            pad.layout().activate()
        if host.layout() is not None:
            host.layout().activate()
        width = host.width() if host is not self and host.width() > 20 else max(self.width(), 160)
        widget.setFixedWidth(max(160, width))
        if widget is self._complete and self._rows:
            self._fill(
                widget,
                [_fit_completion(row.label, widget.fontMetrics(), widget.viewport().width()) for row in self._rows],
            )
        list_h = widget.height()
        if pad is not None and pad.objectName() == "formBuilder.state.edit" and host is not self:
            below = pad.mapTo(host, QPoint(0, pad.height() + 2))
            if below.y() + list_h > host.height():
                above = self.mapTo(host, QPoint(0, -(list_h + 2)))
                point = above if above.y() >= 0 else below
            else:
                point = below
        elif host.objectName() == "formBuilder.eventPicker":
            anchor = self._status if self._status is not None and self._status.isVisible() else self
            point = anchor.mapTo(host, QPoint(0, anchor.height() + 2))
        elif host is self:
            point = QPoint(0, self.height())
        else:
            point = self.mapTo(host, QPoint(0, self.height() + 1))
        widget.move(point)
        widget.raise_()
        widget.show()
        if host.objectName() == "formBuilder.eventPicker":
            needed = point.y() + list_h + 8
            if host.height() < needed:
                host.setMinimumHeight(needed)
                host.resize(max(host.width(), widget.width() + 16), needed)

    def _reflow_block(self) -> None:
        # activate() only packs children into the height already assigned.
        # The wrapped status changes heightForWidth, and the tab does not ask
        # again, so the pad stays short and the label draws over the next rows.
        # Pin the pad and the section to the height their layouts report for
        # the width they already have. Do not resize(): that freezes the width.
        if self._reflowing:
            return
        self._reflowing = True
        try:
            widget: Optional[QWidget] = self.parentWidget()
            targets = []
            while widget is not None:
                targets.append(widget)
                if widget.objectName() == "formBuilder.behaviorBody":
                    break
                widget = widget.parentWidget()
            for target in targets:
                width = target.width()
                if width < 20 or not target.hasHeightForWidth():
                    continue
                height = int(target.heightForWidth(width))
                if height <= 0:
                    continue
                # resize() would pin the width captured before the splitter
                # finished narrowing. A minimum height grows the block and
                # still lets that pass own the width.
                if target.objectName() in ("formBuilder.state.edit", "formBuilder.state"):
                    target.setMinimumHeight(height)
                lay = target.layout()
                if lay is not None:
                    lay.invalidate()
                    lay.activate()
        finally:
            self._reflowing = False

    def _popup_host(self) -> QWidget:
        current: Optional[QWidget] = self.parentWidget()
        picker: Optional[QWidget] = None
        while current is not None:
            name = current.objectName()
            if name == "formBuilder.state":
                return current
            if name == "formBuilder.eventPicker":
                picker = current
            current = current.parentWidget()
        return picker if picker is not None else self

    def _paint_list(self, widget: QListWidget) -> None:
        chrome = self._chrome
        panel = chrome.popup or chrome.panel
        border = chrome.popup_border or chrome.border
        if not panel or not chrome.text:
            return
        widget.setStyleSheet(
            "QListWidget { background: %s; color: %s; border: 1px solid %s; }"
            % (panel, chrome.text, border)
        )

    def resizeEvent(self, event: object) -> None:  # noqa: N802
        super().resizeEvent(event)  # type: ignore[arg-type]
        if self._fitting or self._reflowing:
            return
        self._fit()
        self._reflow_block()
        if self._floating is not None:
            self._place_popup()

    def _fit(self) -> None:
        if self._fitting:
            return
        self._fitting = True
        try:
            doc = self.document()
            line = max(1, self.fontMetrics().lineSpacing())
            doc.setTextWidth(max(1, self.viewport().width()))
            wrapped = max(1, int((doc.size().height() + line - 1) // line))
            lines = min(_MAX_LINES, max(wrapped, doc.blockCount()))
            target = line * lines + 12
            if self.height() != target:
                self.setFixedHeight(target)
        finally:
            self._fitting = False


def _fit_completion(label: str, metrics: object, width: int) -> str:
    """Keep the object name. Elide the display (or the function note) to the row width."""
    parts = label.split("  ")
    room = max(8, width)
    elide = getattr(metrics, "elidedText")
    advance = getattr(metrics, "horizontalAdvance")
    if len(parts) < 2:
        return str(elide(label, _ELIDE, room))
    name = parts[0]
    if len(parts) == 2:
        name_w = int(advance(name + "  "))
        shown = str(elide(parts[1], _ELIDE, max(8, room - name_w)))
        return "%s  %s" % (name, shown)
    kind = parts[-1]
    display = "  ".join(parts[1:-1])
    fixed = int(advance("%s    %s" % (name, kind)))
    shown = str(elide(display, _ELIDE, max(8, room - fixed)))
    return "%s  %s  %s" % (name, shown, kind)


def _severity(code: str) -> Severity:
    info = CODES.get(code)
    if info is None:
        return Severity.ERROR
    return info.severity


def _errored(analysis: Analysis) -> bool:
    return any(_severity(problem.code) is Severity.ERROR for problem in analysis.problems)


def _type_words(analysis: Analysis) -> str:
    typed = analysis.type
    if typed is None:
        return ""
    if typed.kind == FKind.ANY and not analysis.window_calls:
        return ""
    return type_phrase(typed)


def _lead_problem(analysis: Analysis) -> Optional[object]:
    errors = [problem for problem in analysis.problems if _severity(problem.code) is Severity.ERROR]
    if errors:
        return errors[0]
    if analysis.problems:
        return analysis.problems[0]
    return None
