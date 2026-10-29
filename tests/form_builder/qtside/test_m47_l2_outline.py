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
    <item><property name="text"><string>Red</string></property></item>
    <item><property name="text"><string>Amber</string></property></item>
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
        assert "Red, Amber" in _caption(pane, session, "size")
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
        extra = replace(draft.items[0], texts=("Green",), id=None)
        draft = replace(draft, items=draft.items + (extra,))
        items, _rows, _cols = commit_slots(draft)
        session.log.execute(SetItems(combo, items, None, None, merge_token="t2", widget_name="size"))
        pane.note_edited()
        qapp.processEvents()
        assert "\u201cRed, Amber, \u2026\u201d" in _caption(pane, session, "size")


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


def test_closing_a_new_rows_label_editor_selects_the_field(qapp: QApplication, tmp_path) -> None:  # type: ignore[no-untyped-def]
    from app.qt.QtTest import QTest
    from app.qt.QtWidgets import QWidget
    from tests.form_builder.qtside.test_m4_insert_keyboard import _FORM
    from tests.form_builder.qtside.test_m4_pages_keyboard import _flush
    from tests.unit.features.form_builder.test_workbench import _open

    parent = QWidget()
    parent.resize(1100, 760)
    surface = _open(parent, _FORM, tmp_path / "row.ui")
    surface.resize(1100, 760)
    parent.show()
    surface.show()
    _flush()
    session = surface._session
    surface.select_object("notesEdit")
    _flush()
    surface._workbench._place_tile("QComboBox")
    _flush()
    editor = QApplication.focusWidget()
    QTest.keyClicks(editor, "Size")
    QTest.keyClick(editor, Qt.Key.Key_Return)
    _flush()
    state = session.selection.state
    assert [session.document.node(node).object_name for node in state.ids] == ["comboBox"]
    surface.release()
    parent.deleteLater()
    _flush()


def test_outline_item_text_screenshots(qapp: QApplication, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Skips unless CBCS_FB_SCREENSHOT_DIR is set. Light and high-contrast dark, outline with item text."""
    import os
    from pathlib import Path

    from app.qt.QtWidgets import QTreeWidget, QWidget
    from app.shell.theme_tokens import tokens_from_palette
    from tests.form_builder.qtside.test_m4_pages_keyboard import _flush
    from tests.unit.features.form_builder.test_workbench import _open

    folder = os.environ.get("CBCS_FB_SCREENSHOT_DIR")
    if not folder:
        pytest.skip("CBCS_FB_SCREENSHOT_DIR is not set")
    out = Path(folder)
    out.mkdir(parents=True, exist_ok=True)
    parent = QWidget()
    parent.resize(1280, 800)
    surface = _open(parent, _COMBO, tmp_path / "items.ui")
    surface.resize(1280, 800)
    parent.show()
    surface.show()
    _flush()
    session = surface._session
    combo = _id(session, "size")
    draft = load_draft(session.document, combo)
    assert draft is not None
    extra = tuple(replace(draft.items[0], texts=(word,), id=None) for word in ("Green", "Blue"))
    items, _rows, _cols = commit_slots(replace(draft, items=draft.items + extra))
    session.log.execute(SetItems(combo, items, None, None, merge_token="shot", widget_name="size"))
    _flush()
    for mode in ("light", "high_contrast_dark"):
        surface.apply_theme(tokens_from_palette(qapp.palette(), force_mode=mode))
        _flush()
        tree = surface.findChild(QTreeWidget, "formBuilder.structure")
        assert tree is not None
        tree.window().grab().save(str(out / ("outline-item-text-%s.png" % mode)), "PNG")
        surface.grab().save(str(out / ("outline-item-text-%s-full.png" % mode)), "PNG")
    surface.release()
    parent.deleteLater()
    _flush()
