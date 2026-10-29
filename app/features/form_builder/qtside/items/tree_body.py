"""Tree items and columns (UX-ITEM-004)."""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional, Tuple

from app.features.form_builder.engine.ui4.values import StringValue, Value
from app.features.form_builder.qtside.items.details import item_details
from app.features.form_builder.qtside.items.model import (
    TREE_COLUMN_SENTENCE,
    Draft,
    Item,
    Origin,
    add_header,
    add_sibling,
    delete_at,
    delete_header,
    delete_row,
    headers_from_list,
    flat_paths,
    item_at,
    move_header,
    move_sibling,
    nest,
    set_header_text,
    set_header_value,
    set_text,
    unnest,
)
from app.features.form_builder.qtside.inspector.editors._list_editor import ListEditor
from app.qt.QtCore import QEvent, QObject, Qt
from app.qt.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from app.features.form_builder.qtside.items.editor import ItemEditor

_VISIBLE = 3
_ROW_H = 28
_GAP = 4
_INDENT = 16
_MIN_COL = 90
_MARGIN = 4


class TreeBody(QWidget):
    def __init__(self, editor: "ItemEditor") -> None:
        super().__init__(editor)
        self._editor = editor
        self._tabs = QTabWidget(self)
        self._items = _Items(editor, self)
        self._columns = _Columns(editor, self)
        self._tabs.addTab(self._items, "Items")
        self._tabs.addTab(self._columns, "Columns")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._tabs)
        note = QLabel(TREE_COLUMN_SENTENCE)
        note.setObjectName("formBuilder.treeColumnNote")
        note.hide()
        self._note = note
        layout.addWidget(note)
        self._columns.set_note(note)
        # A column added or moved in Columns shows in Items at once.
        self._tabs.currentChanged.connect(self._refresh)

    def _refresh(self, _index: int) -> None:
        self._items.rebuild()
        self._columns.refresh()

    def focus_first(self) -> None:
        self._items.focus_first()

    def trimmed(self, draft: Draft) -> Draft:
        from dataclasses import replace

        from app.features.form_builder.qtside.items.model import trim_blank_tail

        return replace(draft, items=trim_blank_tail(draft.items))


class _Items(QWidget):
    """The Items tab. Only the rows in view (and a margin) have fields.

    A pool of row widgets is rebound to other rows as the list scrolls, so a
    500-row tree opens as fast as a 5-row one. A row that holds keyboard focus
    is never rebound, so typing cannot land in another row.
    """

    def __init__(self, editor: "ItemEditor", parent: QWidget) -> None:
        super().__init__(parent)
        self._editor = editor
        self._paths: List[Tuple[int, ...]] = []
        self._pool: List[_Row] = []
        self._columns = 1
        self._col_w = 120
        self._scroll = QScrollArea(self)
        self._scroll.setObjectName("formBuilder.treeItemsScroll")
        self._scroll.setWidgetResizable(False)
        self._scroll.viewport().installEventFilter(self)
        self._canvas = QWidget()
        self._scroll.setWidget(self._canvas)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._scroll)
        self._filter = _Keys(self)
        self._scroll.verticalScrollBar().valueChanged.connect(lambda _value: self._layout())
        self.rebuild()

    def focus_first(self) -> None:
        if not self._paths:
            draft, path = add_sibling(self._editor.draft, ())
            # empty tree: add a root row so typing has a field
            if not draft.items:
                from app.features.form_builder.qtside.items.model import add_root

                draft, path = add_root(self._editor.draft)
            self._editor.replace(draft)
            self.rebuild()
        if self._paths:
            self._focus(self._paths[0])

    def rebuild(self) -> None:
        self._paths = [path for path, _item in flat_paths(self._editor.draft.items)]
        columns = max(1, len(self._editor.draft.columns))
        if columns != self._columns:
            self._columns = columns
            for row in self._pool:
                row.setParent(None)
                row.deleteLater()
            self._pool = []
        for row in self._pool:
            row.release()
        self._layout()

    def _layout(self) -> None:
        view = self._scroll.viewport()
        width = view.width() if view.width() > 80 else 320
        height = view.height() if view.height() > _ROW_H * 3 else 420
        shown = min(self._columns, _VISIBLE)
        self._col_w = max(_MIN_COL, (width - 8 - _GAP * shown) // shown)
        depth = max((len(path) for path in self._paths), default=1) - 1
        need = 8 + depth * _INDENT + self._columns * (self._col_w + _GAP)
        self._canvas.setFixedSize(max(width, need), max(len(self._paths), 1) * _ROW_H)
        top = self._scroll.verticalScrollBar().value()
        first = max(0, top // _ROW_H - _MARGIN)
        last = min(len(self._paths), (top + height) // _ROW_H + 1 + _MARGIN)
        bound = {}
        free: List[_Row] = []
        for row in self._pool:
            at = row.index
            if row.path is not None and (first <= at < last or row.has_focus()) and at not in bound:
                bound[at] = row
            else:
                free.append(row)
        for index in range(first, last):
            if index in bound:
                continue
            if free:
                row = free.pop()
            else:
                row = _Row(self, self._columns)
                self._pool.append(row)
            row.bind(index, self._paths[index], self._item(self._paths[index]), self._col_w)
            bound[index] = row
        for row in free:
            row.release()
        for index, row in bound.items():
            row.setGeometry(0, index * _ROW_H, self._canvas.width(), _ROW_H)
            row.show()

    def _item(self, path: Tuple[int, ...]) -> Item:
        return item_at(self._editor.draft.items, path)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        # The viewport knows its size after the scroll area has laid out, which
        # is later than this widget's own resize.
        if watched is self._scroll.viewport() and event.type() == getattr(getattr(QEvent, "Type", QEvent), "Resize"):
            self._layout()
        return False

    def _commit_text(self, path: Tuple[int, ...], column: int, text: str) -> None:
        self._editor.replace(set_text(self._editor.draft, path, column, text))

    def apply(self, draft: Draft, focus: Optional[Tuple[int, ...]] = None) -> None:
        self._editor.replace(draft)
        self.rebuild()
        if not self._paths:
            self.focus_first()
            return
        if focus is not None:
            self._focus(focus)

    def _focus(self, path: Tuple[int, ...]) -> None:
        row = self.row_at(path)
        if row is not None:
            row.field(0).setFocus()

    def row_at(self, path: Tuple[int, ...]) -> Optional["_Row"]:
        """The row widget for ``path``, scrolled into view and bound."""
        try:
            index = self._paths.index(path)
        except ValueError:
            return None
        bar = self._scroll.horizontalScrollBar()
        self._scroll.ensureVisible(bar.value(), index * _ROW_H + _ROW_H // 2, 0, _ROW_H // 2)
        self._layout()
        for row in self._pool:
            if row.path == path:
                return row
        return None

    def reveal(self, edit: QLineEdit) -> None:
        self._scroll.ensureWidgetVisible(edit, 24, 0)


class _Row(QWidget):
    def __init__(self, host: _Items, columns: int) -> None:
        super().__init__(host._canvas)
        self._host = host
        self.path: Optional[Tuple[int, ...]] = None
        self.index = -1
        self._row = QHBoxLayout(self)
        self._row.setContentsMargins(0, 0, 0, 0)
        self._row.setSpacing(_GAP)
        self._fields: List[QLineEdit] = []
        for column in range(columns):
            edit = QLineEdit()
            edit.setObjectName("formBuilder.treeItem")
            edit.installEventFilter(host._filter)
            # Live: each keystroke reaches the canvas (UX-ITEM-007).
            edit.textEdited.connect(lambda text, column=column: self._typed(column, text))
            self._row.addWidget(edit)
            self._fields.append(edit)
        self._row.addStretch(1)
        self.hide()

    def bind(self, index: int, path: Tuple[int, ...], item: Item, col_w: int) -> None:
        self.index = index
        self.path = path
        self._row.setContentsMargins(8 + _INDENT * (len(path) - 1), 0, 0, 0)
        for column, edit in enumerate(self._fields):
            edit.setFixedWidth(col_w)
            edit.setText(item.text_at(column))
            edit.setAccessibleName("Row %d, column %d" % (index + 1, column + 1))

    def release(self) -> None:
        self.path = None
        self.index = -1
        self.hide()

    def has_focus(self) -> bool:
        return any(edit.hasFocus() for edit in self._fields)

    def _typed(self, column: int, text: str) -> None:
        if self.path is not None:
            self._host._commit_text(self.path, column, text)

    def field(self, column: int) -> QLineEdit:
        return self._fields[min(column, len(self._fields) - 1)]


class _Keys(QObject):
    def __init__(self, items: _Items) -> None:
        super().__init__(items)
        self._items = items

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if not isinstance(watched, QLineEdit) or event.type() != getattr(getattr(QEvent, "Type", QEvent), "KeyPress", QEvent.KeyPress):
            return False
        key = event.key()  # type: ignore[attr-defined]
        mods = event.modifiers()  # type: ignore[attr-defined]
        ctrl = bool(mods & getattr(Qt, "ControlModifier"))
        alt = bool(mods & getattr(Qt, "AltModifier"))
        shift = bool(mods & getattr(Qt, "ShiftModifier"))
        row = self._row(watched)
        if row is None:
            return False
        if key in (getattr(Qt, "Key_Tab"), getattr(Qt, "Key_Backtab")) and ctrl:
            done = self._items.window().findChild(QWidget, "formBuilder.itemEditorDone")
            if done is not None:
                done.setFocus()
            return True
        if key in (getattr(Qt, "Key_Tab"), getattr(Qt, "Key_Backtab")):
            draft, path = (unnest if shift or key == getattr(Qt, "Key_Backtab") else nest)(self._items._editor.draft, row.path)
            self._items.apply(draft, path)
            return True
        if key == getattr(Qt, "Key_Delete") and ctrl:
            draft, path = delete_row(self._items._editor.draft, row.path)
            self._items.apply(draft, path)
            return True
        if key in (getattr(Qt, "Key_Return"), getattr(Qt, "Key_Enter")):
            draft, path = add_sibling(self._items._editor.draft, row.path)
            self._items.apply(draft, path)
            return True
        if key == getattr(Qt, "Key_Up") and alt:
            draft, path = move_sibling(self._items._editor.draft, row.path, -1)
            self._items.apply(draft, path)
            return True
        if key == getattr(Qt, "Key_Down") and alt:
            draft, path = move_sibling(self._items._editor.draft, row.path, 1)
            self._items.apply(draft, path)
            return True
        if key == getattr(Qt, "Key_Left") and watched.cursorPosition() == 0:
            return self._across(row, watched, -1)
        if key == getattr(Qt, "Key_Right") and watched.cursorPosition() == len(watched.text()):
            return self._across(row, watched, 1)
        return False

    def _across(self, row: _Row, watched: QLineEdit, delta: int) -> bool:
        try:
            index = row._fields.index(watched)
        except ValueError:
            return False
        nxt = index + delta
        if nxt < 0 or nxt >= len(row._fields):
            return False
        row._fields[nxt].setFocus()
        self._items.reveal(row._fields[nxt])
        return True

    def _row(self, watched: QLineEdit) -> Optional[_Row]:
        parent = watched.parent()
        return parent if isinstance(parent, _Row) else None


class _Columns(QWidget):
    def __init__(self, editor: "ItemEditor", parent: QWidget) -> None:
        super().__init__(parent)
        self._editor = editor
        self._note: Optional[QLabel] = None
        self._list = ListEditor(name="Columns", parent=self)
        self._list.set_on_rows(self._rows)
        self._list.set_on_delete(self._delete)
        self._list.set_details(self._details)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._list)
        self._fill()

    def set_note(self, note: QLabel) -> None:
        self._note = note

    def _fill(self) -> None:
        self._list.set_texts(tuple(item.text_at(0) for item in self._editor.draft.columns) or ("Name",))

    def refresh(self) -> None:
        self._fill()

    def _rows(self, texts: Tuple[str, ...], origin: Origin) -> None:
        if self._note is not None:
            self._note.hide()
        self._editor.replace(headers_from_list(self._editor.draft, "column", texts, origin))

    def _details(self, index: int) -> QWidget:
        def current() -> Item:
            columns = self._editor.draft.columns
            if index < 0 or index >= len(columns):
                return Item(texts=("",))
            return columns[index]

        def on_value(name: str, value: Optional[Value]) -> None:
            self._editor.replace(set_header_value(self._editor.draft, "column", index, name, value))
            if name == "text":
                text = value.text if isinstance(value, StringValue) else ""
                self._list.note_external_text(index, text)

        return item_details(self._editor, "header", current, on_value, self)

    def _delete(self, index: int) -> None:
        if len(self._editor.draft.columns) <= 1:
            if self._note is not None:
                self._note.show()
            return
        texts = tuple(item.text_at(0) for item in self._editor.draft.columns)
        origin = tuple(at for at in range(len(texts)) if at != index)
        kept = tuple(texts[at] for at in origin)
        self._editor.replace(headers_from_list(self._editor.draft, "column", kept, origin))
        self._fill()


# Imported by the key filter's type comment. QPushButton is only used as a hint.
from app.qt.QtWidgets import QPushButton  # noqa: E402

_ = (add_header, move_header, item_at, QPushButton)
