"""Shared list editor (UX-PED-044).

Three hosts use the same widget.

String list. Call ``set_texts`` and ``on_texts``. The editor inserts, deletes
and reorders rows itself, then reports the whole tuple. There is no details
panel and no start marker.

Pages. The host owns structure. Pass ``on_add(index)``, ``on_delete(index)``
and ``on_move(index, delta)``. ``on_edit(index, text)`` reports a title
change. ``set_start(index)`` paints a filled dot on that row. Enter on the
last row calls ``on_add`` instead of inserting an empty string.

Items. ``set_details(factory)`` supplies a widget for the focused row.
Alt+Right opens it and Alt+Left closes it. Ctrl+Left and Ctrl+Right stay
word moves in the field. The factory may return None.

Keys, when focus is in a row: Enter moves to the next row and adds on the
last row; Enter on an empty last row calls ``on_close``; Up and Down move;
Alt+Up and Alt+Down move the row; Ctrl+Delete deletes; Backspace in an empty
row deletes it; Ctrl+V of several lines inserts one row per line after the
focused row; Esc calls ``on_revert``; Tab and Shift+Tab call ``on_tab`` so
the host can move to its footer. The widget sets ``fbEnterStays`` so a row
popover does not treat Enter as Done.

Dragging a grip reorders. The insertion line is 2 px. A drop counts only
when the pointer is within 8 px of a boundary. An empty list shows
"No items yet. Type one and press Enter." Rows are 24 px. Only a window of
row widgets is built, so 500 entries do not build 500 fields.

Accessible name of a field is "{name} row {n}". The × button is
"Delete row {n}", shown on hover and focus.
"""

from __future__ import annotations

from typing import Callable, List, Optional, Sequence, Tuple

from app.qt.QtCore import QEvent, QObject, QPoint, Qt
from app.qt.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

ROW_H = 24
_POOL = 20
_HIT = 8
_LINE = 2

_OPEN = "No items yet. Type one and press Enter."


def summarize(items: Sequence[str]) -> str:
    """The row summary. "No items", or "3 items: Red, Green, Blue"."""
    if not items:
        return "No items"
    noun = "item" if len(items) == 1 else "items"
    shown = ", ".join(items[:3])
    if len(items) > 3:
        shown += "\u2026"
    return "%d %s: %s" % (len(items), noun, shown)


def _key(name: str) -> object:
    return getattr(getattr(Qt, "Key", Qt), name)


def _mod(name: str) -> object:
    return getattr(getattr(Qt, "KeyboardModifier", Qt), name)


class ListEditor(QWidget):
    def __init__(self, parent: Optional[QWidget] = None, *, name: str = "List") -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.listEditor")
        self.setProperty("fbEnterStays", True)
        self._name = name
        self._texts: List[str] = []
        self._focus_at = 0
        self._start: Optional[int] = None
        self._details_factory: Optional[Callable[[int], Optional[QWidget]]] = None
        self._details_open = False
        self._details: Optional[QWidget] = None
        self._on_texts: Optional[Callable[[Tuple[str, ...]], None]] = None
        self._on_rows: Optional[Callable[[Tuple[str, ...], Tuple[Optional[int], ...]], None]] = None
        self._on_edit: Optional[Callable[[int, str], None]] = None
        self._on_add: Optional[Callable[[int], None]] = None
        self._on_delete: Optional[Callable[[int], None]] = None
        self._on_move: Optional[Callable[[int, int], None]] = None
        self._on_close: Optional[Callable[[], None]] = None
        self._on_revert: Optional[Callable[[], None]] = None
        self._on_tab: Optional[Callable[[bool], None]] = None
        self._on_space: Optional[Callable[[int], None]] = None
        self._on_focus: Optional[Callable[[int], None]] = None
        self._locked: Optional[Callable[[int], bool]] = None
        self._drag_from: Optional[int] = None
        self._drop_at: Optional[int] = None
        self._hint = QLabel(_OPEN, self)
        self._hint.setObjectName("formBuilder.listEmpty")
        self._hint.setWordWrap(True)
        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(getattr(QFrame, "NoFrame"))
        self._canvas = QWidget()
        self._scroll.setWidget(self._canvas)
        self._line = QFrame(self._canvas)
        self._line.setObjectName("formBuilder.listInsert")
        self._line.setFixedHeight(_LINE)
        self._line.hide()
        self._keys = _KeyFilter(self)
        self.installEventFilter(self._keys)
        self._pool: List[_ListRow] = []
        for _index in range(_POOL):
            row = _ListRow(self._canvas, self)
            row.hide()
            self._pool.append(row)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(self._hint)
        layout.addWidget(self._scroll, 1)
        self.setMinimumHeight(ROW_H * 3)
        self._scroll.verticalScrollBar().valueChanged.connect(lambda _value: self._place())

    def set_name(self, name: str) -> None:
        self._name = name
        self._place()

    def set_texts(self, texts: Sequence[str]) -> None:
        incoming = list(texts)
        if incoming == self._texts:
            self._place()
            return
        self._texts = incoming
        if self._focus_at >= len(self._texts):
            self._focus_at = max(0, len(self._texts) - 1)
        self._close_details()
        self._place()

    def texts(self) -> Tuple[str, ...]:
        return tuple(self._texts)

    def set_start(self, index: Optional[int]) -> None:
        """Pages host. A filled dot on this row. None hides the marker."""
        self._start = index
        self._place()

    def set_details(self, factory: Optional[Callable[[int], Optional[QWidget]]]) -> None:
        """Items host. ``factory(index)`` is the details panel, or None."""
        self._details_factory = factory

    def set_on_texts(self, callback: Optional[Callable[[Tuple[str, ...]], None]]) -> None:
        self._on_texts = callback

    def set_on_rows(self, callback: Optional[Callable[[Tuple[str, ...], Tuple[Optional[int], ...]], None]]) -> None:
        """Items host. ``callback(texts, origin)`` instead of ``on_texts``.

        ``origin[i]`` is the old index of new row ``i``, or None for a new row,
        so a host can keep each row's other data with it across a move or delete.
        """
        self._on_rows = callback

    def set_on_edit(self, callback: Optional[Callable[[int, str], None]]) -> None:
        self._on_edit = callback

    def set_on_add(self, callback: Optional[Callable[[int], None]]) -> None:
        self._on_add = callback

    def set_on_delete(self, callback: Optional[Callable[[int], None]]) -> None:
        self._on_delete = callback

    def set_on_move(self, callback: Optional[Callable[[int, int], None]]) -> None:
        self._on_move = callback

    def set_on_close(self, callback: Optional[Callable[[], None]]) -> None:
        self._on_close = callback

    def set_on_revert(self, callback: Optional[Callable[[], None]]) -> None:
        self._on_revert = callback

    def set_on_tab(self, callback: Optional[Callable[[bool], None]]) -> None:
        """``callback(backward)``. The host moves focus to its footer."""
        self._on_tab = callback

    def set_on_space(self, callback: Optional[Callable[[int], None]]) -> None:
        """Pages host. Space sets the start page instead of typing a space."""
        self._on_space = callback

    def set_on_focus(self, callback: Optional[Callable[[int], None]]) -> None:
        """Called with the row index when focus lands on it."""
        self._on_focus = callback

    def set_read_only(self, locked: Optional[Callable[[int], bool]]) -> None:
        """``locked(index)`` true makes that row's field read-only (stacked pages)."""
        self._locked = locked
        self._place()

    def focused_index(self) -> int:
        return self._focus_at

    def toggle_details(self, index: int) -> None:
        if index != self._focus_at:
            self._close_details()
            self.focus_row(index)
        self._set_details_open(not self._details_open)

    def focus_row(self, index: int) -> None:
        if not self._texts:
            return
        self._focus_at = max(0, min(index, len(self._texts) - 1))
        self._scroll.ensureVisible(0, self._focus_at * ROW_H + 1, 0, ROW_H)
        self._place()
        row = self._row_for(self._focus_at)
        if row is not None:
            row.edit.setFocus()
        focus = self._on_focus
        if focus is not None:
            focus(self._focus_at)

    def row_count(self) -> int:
        return len(self._texts)

    def handle_key(self, event: QEvent) -> bool:
        key = event.key()  # type: ignore[attr-defined]
        mods = event.modifiers()  # type: ignore[attr-defined]
        ctrl = bool(mods & _mod("ControlModifier"))
        alt = bool(mods & _mod("AltModifier"))
        if key == _key("Key_Escape"):
            self._revert()
            event.accept()  # type: ignore[attr-defined]
            return True
        if key in (_key("Key_Tab"), _key("Key_Backtab")):
            backward = key == _key("Key_Backtab") or bool(mods & _mod("ShiftModifier"))
            self._tab(backward)
            event.accept()  # type: ignore[attr-defined]
            return True
        if key in (_key("Key_Return"), _key("Key_Enter")) and not ctrl:
            self._enter()
            event.accept()  # type: ignore[attr-defined]
            return True
        if key == _key("Key_Up") and alt:
            self._move(-1)
            event.accept()  # type: ignore[attr-defined]
            return True
        if key == _key("Key_Down") and alt:
            self._move(1)
            event.accept()  # type: ignore[attr-defined]
            return True
        if key == _key("Key_Up"):
            self.focus_row(self._focus_at - 1)
            event.accept()  # type: ignore[attr-defined]
            return True
        if key == _key("Key_Down"):
            self.focus_row(self._focus_at + 1)
            event.accept()  # type: ignore[attr-defined]
            return True
        if key == _key("Key_Delete") and ctrl:
            self._delete(self._focus_at)
            event.accept()  # type: ignore[attr-defined]
            return True
        if key == _key("Key_Backspace") and self._focused_empty():
            self._delete(self._focus_at, to_end=True)
            event.accept()  # type: ignore[attr-defined]
            return True
        if key == _key("Key_V") and ctrl and self._paste_lines():
            event.accept()  # type: ignore[attr-defined]
            return True
        if key == _key("Key_Right") and alt and not ctrl:
            self._set_details_open(True)
            event.accept()  # type: ignore[attr-defined]
            return True
        if key == _key("Key_Left") and alt and not ctrl:
            self._set_details_open(False)
            event.accept()  # type: ignore[attr-defined]
            return True
        if key == _key("Key_Space") and not ctrl and not alt and self._on_space is not None:
            self._on_space(self._focus_at)
            event.accept()  # type: ignore[attr-defined]
            return True
        return False

    def note_text(self, index: int, text: str) -> None:
        if index < 0 or index >= len(self._texts) or self._texts[index] == text:
            return
        self._texts[index] = text
        edit = self._on_edit
        if edit is not None:
            edit(index, text)
            return
        self._emit()

    def note_focus(self, index: int) -> None:
        if index == self._focus_at or index >= len(self._texts):
            return
        self._focus_at = index
        self._place()
        focus = self._on_focus
        if focus is not None:
            focus(index)

    def note_hover(self, index: int, hovered: bool) -> None:
        row = self._row_for(index)
        if row is not None:
            row.set_hover(hovered or (index == self._focus_at and row.edit.hasFocus()))

    def begin_drag(self, index: int) -> None:
        self._drag_from = index

    def drag_to(self, global_pos: QPoint) -> None:
        if self._drag_from is None:
            return
        local = self._canvas.mapFromGlobal(global_pos)
        boundary = self._boundary(local.y())
        self._drop_at = boundary
        if boundary is None:
            self._line.hide()
            return
        self._line.setGeometry(0, boundary * ROW_H - 1, max(1, self._canvas.width()), _LINE)
        self._line.show()
        self._line.raise_()

    def end_drag(self) -> None:
        source = self._drag_from
        target = self._drop_at
        self._drag_from = None
        self._drop_at = None
        self._line.hide()
        if source is None or target is None or target == source or target == source + 1:
            return
        if self._on_move is not None:
            delta = target - source
            if target > source:
                delta -= 1
            self._on_move(source, delta)
            return
        origin: List[Optional[int]] = list(range(len(self._texts)))
        item = self._texts.pop(source)
        insert = target if target < source else target - 1
        self._texts.insert(insert, item)
        origin.insert(insert, origin.pop(source))
        self._focus_at = insert
        self._emit(origin)
        self._place()

    def delete_clicked(self, index: int) -> None:
        self._delete(index)

    def _place(self) -> None:
        count = len(self._texts)
        empty = count == 0
        self._hint.setVisible(empty)
        extra = self._details_height()
        self._canvas.setFixedHeight(max(count, 1) * ROW_H + extra)
        top = self._scroll.verticalScrollBar().value() // ROW_H
        if self._focus_at < top:
            top = self._focus_at
        if self._focus_at >= top + _POOL:
            top = self._focus_at - _POOL + 1
        top = max(0, top)
        # Rows below an open details panel move down by its height.
        below = extra
        for slot, row in enumerate(self._pool):
            index = top + slot
            if index >= count:
                row.hide()
                row.bind(-1, "", False, "")
                continue
            row.show()
            y = index * ROW_H + (below if index > self._focus_at else 0)
            row.setGeometry(0, y, self._canvas.width() or self.width(), ROW_H)
            row.bind(
                index,
                self._texts[index],
                self._start == index,
                "%s row %d" % (self._name, index + 1),
            )
            # × shows on hover and on real focus, not on the remembered row of
            # a list that does not have focus (the Pages group at rest).
            row.set_hover(index == self._focus_at and row.edit.hasFocus())
            policy = getattr(Qt, "FocusPolicy", Qt)
            strong = getattr(policy, "StrongFocus")
            click = getattr(policy, "ClickFocus")
            row.edit.setFocusPolicy(strong if index == self._focus_at else click)  # type: ignore[arg-type]
        if self._details is not None and self._details_open:
            y = (self._focus_at + 1) * ROW_H
            self._details.setGeometry(0, y, self._canvas.width() or self.width(), self._details_height())
            self._details.show()

    def _details_height(self) -> int:
        if self._details is None or not self._details_open:
            return 0
        hint = self._details.sizeHint().height()
        minimum = self._details.minimumHeight()
        return max(ROW_H, hint, minimum)

    def _row_for(self, index: int) -> Optional["_ListRow"]:
        for row in self._pool:
            if row.index == index and not row.isHidden():
                return row
        return None

    def _enter(self) -> None:
        if not self._texts:
            closer = self._on_close
            if closer is not None:
                closer()
            return
        index = self._focus_at
        if index == len(self._texts) - 1 and self._texts[index] == "":
            closer = self._on_close
            if closer is not None:
                closer()
            return
        if index < len(self._texts) - 1:
            self.focus_row(index + 1)
            return
        adder = self._on_add
        if adder is not None:
            adder(index)
            return
        self._texts.append("")
        self._emit(list(range(len(self._texts) - 1)) + [None])
        self._focus_at = len(self._texts) - 1
        self._place()
        self.focus_row(self._focus_at)

    def _delete(self, index: int, *, to_end: bool = False) -> None:
        if index < 0 or index >= len(self._texts):
            return
        deleter = self._on_delete
        if deleter is not None:
            deleter(index)
            return
        origin: List[Optional[int]] = [at for at in range(len(self._texts)) if at != index]
        del self._texts[index]
        if self._texts:
            self._focus_at = min(index, len(self._texts) - 1)
            if to_end and index > 0:
                self._focus_at = index - 1
        else:
            self._focus_at = 0
        self._emit(origin)
        self._place()
        if self._texts:
            row = self._row_for(self._focus_at)
            if row is not None:
                row.edit.setFocus()
                if to_end:
                    row.edit.end(False)

    def _move(self, delta: int) -> None:
        index = self._focus_at
        target = index + delta
        if target < 0 or target >= len(self._texts):
            return
        mover = self._on_move
        if mover is not None:
            mover(index, delta)
            return
        origin: List[Optional[int]] = list(range(len(self._texts)))
        origin[index], origin[target] = origin[target], origin[index]
        self._texts[index], self._texts[target] = self._texts[target], self._texts[index]
        self._focus_at = target
        self._emit(origin)
        self._place()
        self.focus_row(target)

    def _paste_lines(self) -> bool:
        clipboard = QApplication.clipboard()
        if clipboard is None:
            return False
        text = clipboard.text() or ""
        if "\n" not in text:
            return False
        lines = [line for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n") if line != ""]
        if not lines:
            return False
        at = self._focus_at + 1
        adder = self._on_add
        if adder is not None:
            return False
        origin: List[Optional[int]] = list(range(len(self._texts)))
        origin[at:at] = [None] * len(lines)
        self._texts[at:at] = lines
        self._focus_at = at + len(lines) - 1
        self._emit(origin)
        self._place()
        self.focus_row(self._focus_at)
        return True

    def _focused_empty(self) -> bool:
        if not self._texts:
            return False
        return self._texts[self._focus_at] == ""

    def _revert(self) -> None:
        callback = self._on_revert
        if callback is not None:
            callback()

    def _tab(self, backward: bool) -> None:
        callback = self._on_tab
        if callback is not None:
            callback(backward)
            return
        self.focusNextPrevChild(not backward)

    def _set_details_open(self, open_: bool) -> None:
        factory = self._details_factory
        if factory is None or not self._texts:
            return
        if not open_:
            self._close_details()
            self._place()
            return
        if self._details is not None:
            self._details.setParent(None)
            self._details.deleteLater()
        built = factory(self._focus_at)
        self._details = built
        if built is not None:
            built.setParent(self._canvas)
        self._details_open = built is not None
        self._place()

    def _close_details(self) -> None:
        self._details_open = False
        if self._details is not None:
            self._details.hide()

    def _emit(self, origin: Optional[List[Optional[int]]] = None) -> None:
        rows = self._on_rows
        if rows is not None:
            kept = tuple(range(len(self._texts))) if origin is None else tuple(origin)
            rows(tuple(self._texts), kept)
            return
        callback = self._on_texts
        if callback is not None:
            callback(tuple(self._texts))

    def _boundary(self, y: int) -> Optional[int]:
        if not self._texts:
            return None
        for index in range(len(self._texts) + 1):
            if abs(y - index * ROW_H) <= _HIT:
                return index
        return None

    def resizeEvent(self, event: QEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._place()


class _ListRow(QWidget):
    def __init__(self, parent: QWidget, editor: ListEditor) -> None:
        super().__init__(parent)
        self._editor = editor
        self.index = -1
        self._grip = QLabel("\u2630", self)
        self._grip.setFixedWidth(16)
        self._grip.setCursor(getattr(getattr(Qt, "CursorShape", Qt), "OpenHandCursor"))
        self._dot = QLabel("", self)
        self._dot.setFixedWidth(10)
        self._dot.hide()
        self.edit = QLineEdit(self)
        self._delete = QToolButton(self)
        self._delete.setText("\u00d7")
        self._delete.setFixedSize(16, 16)
        self._delete.hide()
        self._delete.clicked.connect(self._clicked)
        self._more = QToolButton(self)
        self._more.setText("\u25b8")
        self._more.setFixedSize(16, 16)
        self._more.hide()
        self._more.clicked.connect(self._toggle)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(self._grip)
        layout.addWidget(self._dot)
        layout.addWidget(self.edit, 1)
        layout.addWidget(self._more)
        layout.addWidget(self._delete)
        self.setFixedHeight(ROW_H)
        self.edit.textChanged.connect(self._typed)
        self.edit.installEventFilter(editor._keys)
        self._grip.installEventFilter(_Grip(editor, self))
        self.setMouseTracking(True)

    def bind(self, index: int, text: str, start: bool, accessible: str) -> None:
        self.index = index
        self.edit.blockSignals(True)
        if self.edit.text() != text:
            self.edit.setText(text)
        self.edit.blockSignals(False)
        self.edit.setAccessibleName(accessible)
        self._delete.setAccessibleName("Delete row %d" % (index + 1) if index >= 0 else "Delete row")
        self._more.setAccessibleName("Details of row %d" % (index + 1) if index >= 0 else "Details")
        self._more.setVisible(index >= 0 and self._editor._details_factory is not None)
        locked = self._editor._locked
        self.edit.setReadOnly(bool(locked is not None and index >= 0 and locked(index)))
        self.edit.setToolTip(text)
        # The dot keeps its column on every row once a list has a start page,
        # so the titles line up.
        self._dot.setVisible(self._editor._start is not None)
        self._dot.setText("\u25cf" if start else "")
        if not self.edit.hasFocus():
            # Long titles show their start and elide at the end (UX-CONT-019).
            self.edit.setCursorPosition(0)

    def set_hover(self, shown: bool) -> None:
        self._delete.setVisible(shown and self.index >= 0)

    def enterEvent(self, event: QEvent) -> None:  # noqa: N802
        super().enterEvent(event)
        if self.index >= 0:
            self._editor.note_hover(self.index, True)

    def leaveEvent(self, event: QEvent) -> None:  # noqa: N802
        super().leaveEvent(event)
        if self.index >= 0:
            self._editor.note_hover(self.index, False)

    def _typed(self, text: str) -> None:
        if self.index >= 0:
            self._editor.note_text(self.index, text)

    def _clicked(self) -> None:
        if self.index >= 0:
            self._editor.delete_clicked(self.index)

    def _toggle(self) -> None:
        if self.index >= 0:
            self._editor.toggle_details(self.index)


class _Grip(QObject):
    def __init__(self, editor: ListEditor, row: _ListRow) -> None:
        super().__init__(row)
        self._editor = editor
        self._row = row

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        kind = event.type()
        mouse = getattr(QEvent, "Type", QEvent)
        if kind == getattr(mouse, "MouseButtonPress"):
            self._editor.begin_drag(self._row.index)
            return True
        if kind == getattr(mouse, "MouseMove"):
            pos = event.globalPos()  # type: ignore[attr-defined]
            self._editor.drag_to(pos)
            return True
        if kind == getattr(mouse, "MouseButtonRelease"):
            self._editor.end_drag()
            return True
        return False


class _KeyFilter(QObject):
    def __init__(self, editor: ListEditor) -> None:
        super().__init__(editor)
        self._editor = editor

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        kinds = getattr(QEvent, "Type", QEvent)
        if event.type() == getattr(kinds, "FocusIn") and isinstance(watched, QLineEdit):
            # A click puts focus in a row without the keys; the keys act on that row next.
            row = watched.parentWidget()
            if isinstance(row, _ListRow) and row.index >= 0:
                self._editor.note_focus(row.index)
                row.set_hover(True)
            return False
        if event.type() == getattr(kinds, "FocusOut") and isinstance(watched, QLineEdit):
            row = watched.parentWidget()
            if isinstance(row, _ListRow):
                row.set_hover(row.underMouse())
            return False
        if event.type() != getattr(kinds, "KeyPress"):
            return False
        if isinstance(watched, QLineEdit) and self._editor.isAncestorOf(watched):
            return self._editor.handle_key(event)
        focus = QApplication.focusWidget()
        if not isinstance(focus, QWidget):
            return False
        if focus is not self._editor and not self._editor.isAncestorOf(focus):
            return False
        return self._editor.handle_key(event)

