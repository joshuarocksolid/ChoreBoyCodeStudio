# pyright: reportAttributeAccessIssue=false
"""M4.7 L2: outline captions for item widgets and page titles, and a stale row highlight."""

from __future__ import annotations

from dataclasses import replace

import pytest

from app.features.form_builder.engine.commands.catalog import SetItems, SetProperty
from app.features.form_builder.engine.ui4.values import StringValue
from app.features.form_builder.qtside.items.model import commit_slots, load_draft
from app.features.form_builder.engine.query.selection import SelectionSource
from app.qt.QtWidgets import QApplication
from app.qt.QtCore import Qt
from tests.form_builder.qtside.support import form
from tests.form_builder.qtside.test_outline_pane import _id, _items, _opened, _tabs

pytestmark = pytest.mark.usefixtures("qapp")

_COMBO = form(
    'class="QWidget" name="Form"',
    """
  <layout class="QVBoxLayout" name="verticalLayout">
   <item><widget class="QComboBox" name="size">
    <item><property name="text"><string>Small</string></property></item>
    <item><property name="text"><string>Medium</string></property></item>
   </widget></item>
   <item><widget class="QListWidget" name="names">
    <item><property name="text"><string>Ada</string></property></item>
   </widget></item>
  </layout>
""",
)


def _caption(pane, session, name):  # type: ignore[no-untyped-def]
    from app.features.form_builder.qtside.outline.delegate import CAPTION

    item = _items(pane.tree)[int(_id(session, name))]
    return str(item.data(0, CAPTION) or "")


def test_a_combo_and_a_list_show_their_item_text(qapp: QApplication) -> None:
    with _opened(qapp, _COMBO, "items") as (pane, session):
        assert "Small, Medium" in _caption(pane, session, "size")
        assert "Ada" in _caption(pane, session, "names")


def test_editing_items_updates_the_outline_caption(qapp: QApplication) -> None:
    with _opened(qapp, _COMBO, "items-edit") as (pane, session):
        combo = _id(session, "size")
        draft = load_draft(session.document, combo)
        assert draft is not None
        draft = replace(draft, items=(replace(draft.items[0], texts=("Tiny",)),) + draft.items[1:])
        items, _rows, _cols = commit_slots(draft)
        session.log.execute(SetItems(combo, items, None, None, merge_token="t", widget_name="size"))
        pane.note_edited()
        qapp.processEvents()
        assert "Tiny" in _caption(pane, session, "size")


def test_renaming_a_tab_page_updates_its_outline_caption(qapp: QApplication) -> None:
    with _opened(qapp, _tabs(), "tab-rename") as (pane, session):
        page = _id(session, "pageB")
        session.log.execute(SetProperty(page, "title", StringValue("Renamed"), kind="attribute"))
        pane.note_edited()
        qapp.processEvents()
        assert _caption(pane, session, "pageB") == "Tab 2 · Renamed"


def test_adding_an_item_updates_the_outline_caption(qapp: QApplication) -> None:
    with _opened(qapp, _COMBO, "items-add") as (pane, session):
        combo = _id(session, "size")
        draft = load_draft(session.document, combo)
        assert draft is not None
        extra = replace(draft.items[0], texts=("Large",), id=None)
        draft = replace(draft, items=draft.items + (extra,))
        items, _rows, _cols = commit_slots(draft)
        session.log.execute(SetItems(combo, items, None, None, merge_token="t2", widget_name="size"))
        pane.note_edited()
        qapp.processEvents()
        assert "Small, Medium, Large" in _caption(pane, session, "size")


def test_narrowing_a_selection_drops_the_old_highlight(qapp: QApplication) -> None:
    from tests.form_builder.qtside.test_outline_pane import _buttons

    with _opened(qapp, _buttons(3), "stale") as (pane, session):
        first, second = _id(session, "field0"), _id(session, "field1")
        session.selection.set((first, second), current=second, source=SelectionSource.OUTLINE)
        pane.show_current(second)
        assert len(pane.tree.selectedItems()) == 2
        session.selection.set((second,), current=second, source=SelectionSource.CANVAS)
        pane.show_current(second)
        names = [item.text(0) for item in pane.tree.selectedItems()]
        assert names == ["field1"]


def test_a_page_titled_like_its_number_is_not_repeated(qapp: QApplication) -> None:
    from app.features.form_builder.engine.commands.catalog_ext.pages import InsertPage

    with _opened(qapp, _tabs(), "tab-repeat") as (pane, session):
        session.log.execute(InsertPage(_id(session, "tabs")))
        pane.note_edited()
        qapp.processEvents()
        assert _caption(pane, session, "tab_3") == "Tab 3"
