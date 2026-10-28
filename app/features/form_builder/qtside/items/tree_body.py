"""Tree items and columns (UX-ITEM-004)."""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional, Tuple

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
    def __init__(self, editor: "ItemEditor", parent: QWidget) -> None:
        super().__init__(parent)
        self._editor = editor
        self._rows: List[_Row] = []
        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._canvas = QWidget()
        self._canvas_layout = QVBoxLayout(self._canvas)
        self._canvas_layout.setContentsMargins(0, 0, 0, 0)
        self._canvas_layout.addStretch(1)
        self._scroll.setWidget(self._canvas)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._scroll)
        self._filter = _Keys(self)
        self.rebuild()

    def focus_first(self) -> None:
        if not self._rows:
            draft, path = add_sibling(self._editor.draft, ())
            # empty tree: add a root row so typing has a field
            if not draft.items:
                from app.features.form_builder.qtside.items.model import add_root

                draft, path = add_root(self._editor.draft)
            self._editor.replace(draft)
            self.rebuild()
        if self._rows:
            self._rows[0].field(0).setFocus()

    def rebuild(self) -> None:
        while self._canvas_layout.count() > 1:
            item = self._canvas_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._rows = []
        for path, item in flat_paths(self._editor.draft.items):
            row = _Row(self, path, item, max(1, len(self._editor.draft.columns)))
            self._canvas_layout.insertWidget(self._canvas_layout.count() - 1, row)
            self._rows.append(row)

    def _commit_text(self, path: Tuple[int, ...], column: int, text: str) -> None:
        self._editor.replace(set_text(self._editor.draft, path, column, text))

    def apply(self, draft: Draft, focus: Optional[Tuple[int, ...]] = None) -> None:
        self._editor.replace(draft)
        self.rebuild()
        if not self._rows:
            self.focus_first()
            return
        if focus is not None:
            self._focus(focus)

    def _focus(self, path: Tuple[int, ...]) -> None:
        for row in self._rows:
            if row.path == path:
                row.field(0).setFocus()
                return


class _Row(QWidget):
    def __init__(self, host: _Items, path: Tuple[int, ...], item: Item, columns: int) -> None:
        super().__init__(host)
        self._host = host
        self.path = path
        row = QHBoxLayout(self)
        row.setContentsMargins(16 * (len(path) - 1), 0, 0, 0)
        self._fields: List[QLineEdit] = []
        shown = min(columns, _VISIBLE)
        for column in range(shown):
            edit = QLineEdit(item.text_at(column))
            edit.setObjectName("formBuilder.treeItem")
            edit.installEventFilter(host._filter)
            # Live: each keystroke reaches the canvas (UX-ITEM-007).
            edit.textEdited.connect(lambda text, column=column, path=path: host._commit_text(path, column, text))
            row.addWidget(edit)
            self._fields.append(edit)
        if columns > _VISIBLE:
            self.setToolTip("More columns are off to the side")

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
