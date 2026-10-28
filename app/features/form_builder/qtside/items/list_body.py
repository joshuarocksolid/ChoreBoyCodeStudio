"""Combo and list item bodies (UX-ITEM-003)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Tuple

from app.features.form_builder.engine.ui4.values import Value
from app.features.form_builder.qtside.items.details import build_details
from app.features.form_builder.qtside.items.model import Draft, Item, Origin, rows_from_list, set_item_value
from app.features.form_builder.qtside.inspector.editors._list_editor import ListEditor
from app.qt.QtWidgets import QVBoxLayout, QWidget

if TYPE_CHECKING:
    from app.features.form_builder.qtside.items.editor import ItemEditor


class ListBody(QWidget):
    def __init__(self, editor: "ItemEditor") -> None:
        super().__init__(editor)
        self._editor = editor
        self._list = ListEditor(name="Items", parent=self)
        self._list.set_on_rows(self._rows)
        self._list.set_on_revert(editor.revert)
        self._list.set_on_close(editor.close_keep)
        self._list.set_details(self._details)
        texts = tuple(item.text_at(0) for item in editor.draft.items)
        self._list.set_texts(texts or ("",))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._list)

    def focus_first(self) -> None:
        self._list.focus_row(0)

    def trimmed(self, draft: Draft) -> Draft:
        items = list(draft.items)
        while items and _blank(items[-1]):
            items.pop()
        from dataclasses import replace

        return replace(draft, items=tuple(items))

    def _rows(self, texts: Tuple[str, ...], origin: Origin) -> None:
        self._editor.replace(rows_from_list(self._editor.draft, texts, origin))

    def _details(self, index: int) -> QWidget:
        def current() -> Item:
            items = self._editor.draft.items
            if index < 0 or index >= len(items):
                return Item(texts=("",))
            return items[index]

        def on_value(name: str, value: Optional[Value]) -> None:
            self._editor.replace(set_item_value(self._editor.draft, (index,), name, value))

        def on_more() -> None:
            from app.features.form_builder.qtside.items.more import show_more

            show_more(self, current(), on_value)

        return build_details(self._editor.draft.kind, current, on_value, on_more, self)


def _blank(item: Item) -> bool:
    if any(text for text in item.texts):
        return False
    if item.children:
        return False
    base = item.base
    if base is None:
        return True
    return not any(entry.name != "text" for entry in base.properties)
