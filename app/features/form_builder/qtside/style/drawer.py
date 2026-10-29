"""The style sheet drawer under the canvas (UX-STYLE-002 .. 007). Qt side.

The workbench shows this widget through ``open_under_canvas``. The text editor
is handed in (the shell's code editor when the drawer is built by the
integration; a plain text edit in tests), so this module imports nothing from
the shell.

* Typing is applied 300 ms after the last key: a text Qt can read is set as the
  widget's ``styleSheet`` in one edit session; a text it cannot read leaves the
  last readable one on the canvas and shows the problem.
* A rule's first line carries a chip with the number of widgets it styles.
* While the caret is in a rule, the canvas outlines the widgets it styles.
* The whole visit to one widget is one undo step, "Change style sheet of {name}".
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, replace
from typing import Callable, List, Optional, Sequence, Tuple

from app.features.form_builder.engine.commands.base import CommandRejected
from app.features.form_builder.engine.commands.catalog import SetProperty
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.style.check import Check
from app.features.form_builder.engine.style.selectors import RuleMatch, match_sheet, shared_index
from app.features.form_builder.engine.style.sheet import Sheet
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.engine.ui4.values import StringValue
from app.features.form_builder.qtside.style import insert as insert_text
from app.features.form_builder.qtside.theme.style_tokens import INSERT_COLOUR, ok_color
from app.features.form_builder.qtside.style.verdict import check_text
from app.features.form_builder.qtside.theme.chrome import FormChrome, default_chrome
from app.qt.QtCore import QEvent, QObject, QPoint, QRect, Qt, QTimer
from app.qt.QtGui import QColor, QFont, QPainter, QPen, QTextCursor
from app.qt.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QToolButton,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

APPLY_MS = 300
HEADER_HEIGHT = 32
GUTTER_WIDTH = 92
_TOKENS = itertools.count(1)

NO_MATCH = "No match"


@dataclass(frozen=True)
class DrawerHooks:
    """What the drawer asks of the workbench and the surface around it."""

    chrome: Callable[[], FormChrome] = default_chrome
    #: Outline these widgets on the canvas (an empty tuple clears the outline).
    show_matches: Callable[[Tuple[NodeId, ...]], None] = lambda ids: None
    narrate: Callable[[str], None] = lambda sentence: None
    #: Called after the drawer committed its step and hid itself.
    closed: Callable[[Optional[NodeId]], None] = lambda target: None
    #: Pictures: ``pick_picture(parent)`` returns the stored path (``:/pictures/a.png``) or "".
    pick_picture: Callable[[QWidget], str] = lambda parent: ""


def sheet_text_of(node: object) -> str:
    entry = node.prop("styleSheet") if isinstance(node, WidgetNode) else None
    if entry is not None and isinstance(entry.value, StringValue):
        return entry.value.text
    return ""


def chip_text(match: RuleMatch) -> Tuple[str, bool]:
    """``(text, is a warning)`` for a rule's count chip."""
    if match.count == 0 or not match.valid:
        return NO_MATCH, True
    base = "1 widget" if match.count == 1 else "%d widgets" % match.count
    if match.states:
        base += " · when " + " and ".join(match.states)
    return base, False


def styles_sentence(names: Sequence[str]) -> str:
    """"This rule styles saveButton, cancelButton and 1 more." (UX-STYLE-005)"""
    if not names:
        return ""
    if len(names) == 1:
        return "This rule styles %s." % names[0]
    if len(names) == 2:
        return "This rule styles %s and %s." % (names[0], names[1])
    return "This rule styles %s, %s and %d more." % (names[0], names[1], len(names) - 2)


class _Gutter(QWidget):
    """The strip right of the editor with one chip beside each rule's first line."""

    def __init__(self, editor: QPlainTextEdit, drawer: "StyleDrawer") -> None:
        super().__init__(drawer)
        self._editor = editor
        self._drawer = drawer
        self._chips: List[Tuple[int, str, bool, Tuple[NodeId, ...], Tuple[str, ...]]] = []
        self._rects: List[Tuple[QRect, Tuple[NodeId, ...], Tuple[str, ...]]] = []
        self.setObjectName("formBuilder.styleGutter")
        self.setFixedWidth(GUTTER_WIDTH)
        self.setMouseTracking(True)
        editor.verticalScrollBar().valueChanged.connect(self.update)

    def set_chips(self, chips: List[Tuple[int, str, bool, Tuple[NodeId, ...], Tuple[str, ...]]]) -> None:
        self._chips = chips
        self.update()

    def chips(self) -> List[Tuple[int, str, bool, Tuple[NodeId, ...], Tuple[str, ...]]]:
        return list(self._chips)

    def paintEvent(self, _event: QEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        chrome = self._drawer.chrome()
        warn = QColor(self._drawer.warning())
        normal = QColor(chrome.muted)
        metrics = painter.fontMetrics()
        self._rects = []
        document = self._editor.document()
        for line, text, is_warn, ids, names in self._chips:
            block = document.findBlockByNumber(line - 1)
            if not block.isValid():
                continue
            geometry = self._editor.blockBoundingGeometry(block).translated(self._editor.contentOffset())
            top = int(geometry.top())
            if top < -geometry.height() or top > self.height():
                continue
            shown = metrics.elidedText(text, Qt.TextElideMode.ElideRight, self.width() - 12)
            width = min(self.width() - 4, metrics.horizontalAdvance(shown) + 12)
            rect = QRect(self.width() - width - 2, top + 1, width, max(14, int(geometry.height()) - 2))
            ink = warn if is_warn else normal
            fill = QColor(ink)
            fill.setAlpha(36)
            painter.setPen(QPen(ink, 1))
            painter.setBrush(fill)
            painter.drawRoundedRect(rect, 7, 7)
            painter.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), shown)
            self._rects.append((rect, ids, names))

    def _at(self, point: QPoint) -> Optional[Tuple[Tuple[NodeId, ...], Tuple[str, ...]]]:
        for rect, ids, names in self._rects:
            if rect.contains(point):
                return ids, names
        return None

    def mouseMoveEvent(self, event: QEvent) -> None:  # noqa: N802
        found = self._at(event.position().toPoint())  # type: ignore[attr-defined]
        if found is None or not found[1]:
            QToolTip.hideText()
            return
        QToolTip.showText(event.globalPosition().toPoint(), ", ".join(found[1]), self)  # type: ignore[attr-defined]

    def mousePressEvent(self, event: QEvent) -> None:  # noqa: N802
        found = self._at(event.position().toPoint())  # type: ignore[attr-defined]
        if found is not None and found[0]:
            self._drawer.select_nodes(found[0])
            event.accept()  # type: ignore[attr-defined]
            return
        super().mousePressEvent(event)  # type: ignore[arg-type]


class _EscapeFilter(QObject):
    def __init__(self, drawer: "StyleDrawer") -> None:
        super().__init__(drawer)
        self._drawer = drawer

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:  # type: ignore[attr-defined]
            self._drawer.close_drawer()
            return True
        return False


class StyleDrawer(QFrame):
    """See the module docstring."""

    def __init__(
        self,
        session: FormSession,
        editor: QPlainTextEdit,
        hooks: DrawerHooks,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.styleDrawer")
        self.setAccessibleName("Style sheet")
        self._session = session
        self._editor = editor
        self._hooks = hooks
        self._target: Optional[NodeId] = None
        self._token = ""
        self._written: Optional[str] = None
        self._writing = False
        self._last_check: Optional[Check] = None
        self._matches: Tuple[RuleMatch, ...] = ()
        self._sheet: Optional[Sheet] = None
        self._closing = False
        self._loading = False
        self._pending: Optional[str] = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(APPLY_MS)
        self._timer.timeout.connect(self._apply)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        header = QWidget(self)
        header.setObjectName("formBuilder.styleHeader")
        header.setFixedHeight(HEADER_HEIGHT)
        row = QHBoxLayout(header)
        row.setContentsMargins(8, 0, 8, 0)
        row.setSpacing(8)
        self._title = QLabel("STYLE SHEET", header)
        overline = QFont(self._title.font())
        overline.setPointSizeF(max(7.0, overline.pointSizeF() * 0.8))
        overline.setBold(True)
        overline.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.6)
        self._title.setFont(overline)
        self._scope = QComboBox(header)
        self._scope.setObjectName("formBuilder.styleScope")
        self._scope.setAccessibleName("Style sheet of")
        self._scope.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self._status = QToolButton(header)
        self._status.setObjectName("formBuilder.styleStatus")
        self._status.setAutoRaise(True)
        self._status.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self._status.clicked.connect(self._go_to_problem)
        self._insert = QToolButton(header)
        self._insert.setObjectName("formBuilder.styleInsert")
        self._insert.setText("Insert ▸")
        self._insert.setAccessibleName("Insert")
        self._insert.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._insert.setMenu(self._build_insert_menu())
        self._done = QPushButton("Done", header)
        self._done.setObjectName("formBuilder.styleDone")
        self._done.setAutoDefault(False)
        self._done.clicked.connect(self.close_drawer)
        row.addWidget(self._title)
        row.addWidget(self._scope)
        row.addWidget(self._status, 1)
        row.addWidget(self._insert)
        row.addWidget(self._done)
        outer.addWidget(header)

        body = QWidget(self)
        body_row = QHBoxLayout(body)
        body_row.setContentsMargins(0, 0, 0, 0)
        body_row.setSpacing(0)
        editor.setParent(body)
        editor.setObjectName("formBuilder.styleEditor")
        editor.setAccessibleName("Style sheet text")
        editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._gutter = _Gutter(editor, self)
        body_row.addWidget(editor, 1)
        body_row.addWidget(self._gutter, 0)
        outer.addWidget(body, 1)

        editor.textChanged.connect(self._text_changed)
        editor.cursorPositionChanged.connect(self._caret_moved)
        editor.installEventFilter(_EscapeFilter(self))
        self._scope.activated.connect(self._scope_chosen)
        self._subscription = session.log.subscribe(self._document_changed, priority=900)
        self._stop_selection = session.selection.subscribe(self._selection_changed)
        self.apply_chrome()

    # public ------------------------------------------------------------------

    @property
    def editor(self) -> QPlainTextEdit:
        return self._editor

    @property
    def target(self) -> Optional[NodeId]:
        return self._target

    def chrome(self) -> FormChrome:
        return self._hooks.chrome()

    def warning(self) -> str:
        from app.features.form_builder.qtside.inspector.editors._editor_kit import warning_color

        return warning_color(self.chrome())

    def status_text(self) -> str:
        return self._status.text()

    def check(self) -> Optional[Check]:
        return self._last_check

    def chips(self) -> List[Tuple[int, str, bool, Tuple[NodeId, ...], Tuple[str, ...]]]:
        return self._gutter.chips()

    def apply_chrome(self) -> None:
        chrome = self.chrome()
        self.setStyleSheet(
            "QFrame#formBuilder\\.styleDrawer { background: %(panel)s; color: %(text)s; border-top: 1px solid %(border)s; }"
            "QWidget#formBuilder\\.styleHeader { background: %(panel)s; border-bottom: 1px solid %(border)s; }"
            "QWidget#formBuilder\\.styleHeader QLabel { color: %(muted)s; background: transparent; }"
            "QToolButton#formBuilder\\.styleInsert, QPushButton#formBuilder\\.styleDone, QComboBox#formBuilder\\.styleScope {"
            " color: %(text)s; background: %(input)s; border: 1px solid %(border)s; border-radius: 3px; padding: 2px 10px; }"
            "QToolButton#formBuilder\\.styleInsert::menu-indicator { image: none; width: 0px; }"
            "QPlainTextEdit#formBuilder\\.styleEditor { background: %(input)s; color: %(text)s; border: none; }"
            % {
                "panel": chrome.panel,
                "text": chrome.text,
                "border": chrome.border,
                "muted": chrome.muted,
                "input": chrome.input,
            }
        )
        self._paint_status()

    def show_for(self, node_id: Optional[NodeId]) -> None:
        """Commit the visit in progress, then show ``node_id``'s sheet (the form's when None)."""
        document = self._session.document
        target = node_id if node_id is not None and document.contains(node_id) else document.root.id
        if not isinstance(document.node(target), WidgetNode):
            target = document.root.id
        self._flush()
        self._end_visit()
        self._target = target
        self._token = "style-%d" % next(_TOKENS)
        text = sheet_text_of(document.node(target))
        self._written = text
        self._last_check = None
        self._load(text)
        self._fill_scope()
        self._refresh(text)
        self._editor.setFocus()

    def close_drawer(self) -> None:
        """Esc and Done. The text is kept; the visit is one undo step (UX-STYLE-007)."""
        if self._closing:
            return
        self._closing = True
        try:
            self._flush()
            target = self._target
            self._end_visit()
            self._hooks.show_matches(())
            self._hooks.narrate("")
            self._target = None
            self._hooks.closed(target)
        finally:
            self._closing = False

    def dispose(self) -> None:
        self._timer.stop()
        self._subscription.close()
        self._stop_selection()

    def select_nodes(self, ids: Sequence[NodeId]) -> None:
        live = tuple(node_id for node_id in ids if self._session.document.contains(node_id))
        if live:
            self._flush()
            self._session.selection.set(live, source=SelectionSource.PROGRAM)

    def insert_at_caret(self, text: str, *, caret_offset: Optional[int] = None) -> None:
        """Replace the selection with ``text`` (UX-STYLE-006)."""
        cursor = self._editor.textCursor()
        start = cursor.selectionStart()
        cursor.insertText(text)
        if caret_offset is not None:
            cursor.setPosition(start + caret_offset)
        self._editor.setTextCursor(cursor)
        self._editor.setFocus()

    # editing -----------------------------------------------------------------

    def _load(self, text: str) -> None:
        self._loading = True
        try:
            self._editor.setPlainText(text)
            self._editor.moveCursor(QTextCursor.MoveOperation.Start)
        finally:
            self._loading = False

    def _text_changed(self) -> None:
        if self._loading:
            return
        self._timer.start()

    def _flush(self) -> None:
        if self._timer.isActive():
            self._timer.stop()
            self._apply()

    def _apply(self) -> None:
        target = self._target
        if target is None or not self._session.document.contains(target):
            return
        text = self._editor.toPlainText()
        result = check_text(text)
        self._last_check = result
        self._paint_status()
        self._refresh(text)
        if not result.applies:
            return
        if text == self._written:
            return
        self._write(target, text)

    def visit_step(self) -> Tuple[str, str]:
        """``(undo label, merge token)`` of this visit, so a picture's include joins the visit's one step."""
        target = self._target
        node = self._session.document.get(target) if target is not None else None
        label = "Change style sheet of %s" % (getattr(node, "object_name", "") or "widget")
        if not self._token:
            self._token = "style-%d" % next(_TOKENS)
        return label, self._token

    def _write(self, target: NodeId, text: str) -> None:
        document = self._session.document
        node = document.node(target)
        label = "Change style sheet of %s" % (getattr(node, "object_name", "") or "widget")
        entry = node.prop("styleSheet")
        base = entry.value if entry is not None and isinstance(entry.value, StringValue) else StringValue("", notr=True)
        command = (
            SetProperty(target, "styleSheet", None, undo_label=label)
            if not text.strip()
            else SetProperty(target, "styleSheet", replace(base, text=text), undo_label=label)
        )
        self._writing = True
        try:
            with self._session.log.transaction(label, merge_token=self._token, merge_within_s=math.inf) as txn:
                txn.execute(command)
            self._written = text
        except CommandRejected:
            return
        finally:
            self._writing = False

    def _end_visit(self) -> None:
        self._token = ""

    # looking at the sheet ------------------------------------------------------

    def _refresh(self, text: str) -> None:
        target = self._target
        if target is None:
            return
        result = self._last_check if self._last_check is not None else check_text(text)
        self._last_check = result
        self._paint_status()
        self._sheet = result.sheet
        index = shared_index(self._session.document)
        self._matches = match_sheet(index, target, result.sheet)
        chips = []
        for match in self._matches:
            label, warn = chip_text(match)
            line = self._chip_line(result.sheet, match)
            names = tuple(index.facts[node_id].name or "widget" for node_id in match.ids if node_id in index.facts)
            chips.append((line, label, warn, match.ids, names))
        self._gutter.set_chips(chips)
        self._caret_moved()

    @staticmethod
    def _chip_line(sheet: Sheet, match: RuleMatch) -> int:
        if match.rule >= 0 and match.rule < len(sheet.rules):
            return sheet.rules[match.rule].line
        if sheet.declarations:
            return sheet.declarations[0].line
        return 1

    def _paint_status(self) -> None:
        result = self._last_check
        chrome = self.chrome()
        if result is None:
            self._status.setText("")
            return
        if result.status == "ok":
            tint, text = ok_color(chrome), "✓ " + result.message
        elif result.status == "warning":
            tint, text = self.warning(), "⚠ " + result.message
        else:
            tint, text = chrome.error, "✕ " + result.message
        self._status.setText(text)
        self._status.setToolTip(result.message)
        self._status.setAccessibleName("Style sheet check: %s" % result.message)
        self._status.setStyleSheet("QToolButton { color: %s; background: transparent; border: none; text-align: left; }" % tint)

    def _go_to_problem(self) -> None:
        result = self._last_check
        if result is None or result.line < 1:
            self._editor.setFocus()
            return
        block = self._editor.document().findBlockByNumber(result.line - 1)
        if block.isValid():
            cursor = self._editor.textCursor()
            cursor.setPosition(block.position() + max(0, min(result.column - 1, block.length() - 1)))
            self._editor.setTextCursor(cursor)
        self._editor.setFocus()

    def _rule_at(self, position: int) -> Optional[int]:
        sheet = self._sheet
        if sheet is None:
            return None
        for index, rule in enumerate(sheet.rules):
            end = rule.close + 1 if rule.close >= 0 else len(sheet.text)
            if rule.start <= position <= end:
                return index
        return None

    def _caret_moved(self) -> None:
        if self._target is None:
            return
        position = self._editor.textCursor().position()
        found = self._rule_at(position)
        match: Optional[RuleMatch] = None
        if found is not None:
            match = next((item for item in self._matches if item.rule == found), None)
        elif self._matches and self._matches[0].rule == -1:
            match = self._matches[0]
        if match is None or match.count == 0:
            self._hooks.show_matches(())
            self._hooks.narrate("")
            return
        self._hooks.show_matches(match.ids)
        index = shared_index(self._session.document)
        names = [index.facts[node_id].name or "widget" for node_id in match.ids if node_id in index.facts]
        self._hooks.narrate(styles_sentence(names))

    # scope -----------------------------------------------------------------------

    def _fill_scope(self) -> None:
        document = self._session.document
        wanted: List[NodeId] = [document.root.id]
        for node in document.iter_widgets():
            if node.id != document.root.id and sheet_text_of(node).strip() and node.id not in wanted:
                wanted.append(node.id)
        if self._target is not None and self._target not in wanted:
            wanted.append(self._target)
        self._scope.blockSignals(True)
        self._scope.clear()
        for node_id in wanted:
            node = document.node(node_id)
            self._scope.addItem("of %s" % (getattr(node, "object_name", "") or "widget"), node_id)
        self._scope.setCurrentIndex(max(0, wanted.index(self._target)) if self._target in wanted else 0)
        self._scope.blockSignals(False)

    def _scope_chosen(self, index: int) -> None:
        node_id = self._scope.itemData(index)
        if node_id is not None:
            self.show_for(node_id)

    # the form changing under the drawer -----------------------------------------------

    def _selection_changed(self, _change: object) -> None:
        if self._closing or self._target is None:
            return
        state = self._session.selection.state
        ids = [node_id for node_id in state.ids if isinstance(self._session.document.get(node_id), WidgetNode)]
        wanted = ids[0] if len(ids) == 1 else (self._session.document.root.id if not state.ids else None)
        if wanted is not None and wanted != self._target:
            QTimer.singleShot(0, lambda node_id=wanted: self._follow(node_id))

    def _follow(self, node_id: NodeId) -> None:
        if self._target is not None and node_id != self._target and self._session.document.contains(node_id):
            self.show_for(node_id)

    def _document_changed(self, _change: object) -> None:
        if self._writing or self._target is None or self._closing:
            return
        document = self._session.document
        if not document.contains(self._target):
            QTimer.singleShot(0, self.close_drawer)
            return
        text = sheet_text_of(document.node(self._target))
        if text != self._written:
            # An undo or another row changed the sheet: show what the form has now.
            self._timer.stop()
            self._written = text
            self._load(text)
            self._last_check = None
            self._refresh(text)

    # Insert menu ------------------------------------------------------------------------

    def _build_insert_menu(self) -> QMenu:
        menu = QMenu(self._insert)
        menu.addAction("Colour…").triggered.connect(self._insert_colour)
        menu.addAction("Picture…").triggered.connect(self._insert_picture)
        menu.addAction("Gradient…").triggered.connect(self._insert_gradient)
        menu.addAction("Font…").triggered.connect(self._insert_font)
        menu.addAction("Rule for this widget").triggered.connect(self._insert_rule)
        return menu

    def _insert_colour(self) -> None:
        from app.features.form_builder.qtside.style.insert_dialogs import ask_colour

        text = self._editor.toPlainText()
        cursor = self._editor.textCursor()
        span = insert_text.colour_span_at(text, cursor.position()) if not cursor.hasSelection() else None
        start = text[span[0] : span[1]] if span else INSERT_COLOUR
        chosen = ask_colour(self, self.chrome(), start)
        if not chosen:
            return
        if span is not None:
            cursor.setPosition(span[0])
            cursor.setPosition(span[1], QTextCursor.MoveMode.KeepAnchor)
            self._editor.setTextCursor(cursor)
        self.insert_at_caret(chosen)

    def _insert_picture(self) -> None:
        stored = self._hooks.pick_picture(self)
        if stored:
            self.insert_at_caret(insert_text.picture_text(stored))

    def _insert_gradient(self) -> None:
        from app.features.form_builder.qtside.style.insert_dialogs import ask_gradient

        chosen = ask_gradient(self, self.chrome())
        if chosen:
            self.insert_at_caret(chosen)

    def _insert_font(self) -> None:
        from app.features.form_builder.qtside.style.insert_dialogs import ask_font

        chosen = ask_font(self)
        if chosen:
            self.insert_at_caret(chosen)

    def _insert_rule(self) -> None:
        target = self._target
        if target is None:
            return
        name = getattr(self._session.document.node(target), "object_name", "") or "widget"
        text, caret = insert_text.rule_text(name)
        self.insert_at_caret(text, caret_offset=caret)


__all__: Sequence[str] = ["DrawerHooks", "StyleDrawer", "chip_text", "sheet_text_of", "styles_sentence"]
