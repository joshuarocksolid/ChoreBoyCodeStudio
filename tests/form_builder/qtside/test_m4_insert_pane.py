# pyright: reportAttributeAccessIssue=false
"""The Insert pane: recent use, views, folding, names, per-document widgets, one name per class."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.features.form_builder.integration.insert_memory import InMemoryInsertMemory, InsertMemoryStore
from app.features.form_builder.qtside.canvas.core.words import hover_sentence
from app.features.form_builder.qtside.insert.catalog import load_catalog
from app.features.form_builder.qtside.insert.delegate import ROW_ROLE
from app.features.form_builder.qtside.insert.pane import InsertPane
from app.features.form_builder.qtside.insert.rows import ENTRY, HEADER
from app.features.form_builder.qtside.inspector.words import class_words
from app.features.form_builder.qtside.outline.friendly import friendly_of
from app.qt.QtCore import Qt
from app.qt.QtWidgets import QApplication, QWidget
from tests.form_builder.qtside.support import open_session

pytestmark = pytest.mark.usefixtures("qapp")

_CUSTOM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="Shop::Card" name="card"/>
   </item>
  </layout>
 </widget>
 <customwidgets>
  <customwidget>
   <class>Shop::Card</class>
   <extends>QFrame</extends>
   <header>shop/card.h</header>
  </customwidget>
 </customwidgets>
 <resources/>
 <connections/>
</ui>
"""


_KEEP: list = []


def _pane(parent: QWidget, memory: object) -> InsertPane:
    """A pane under ``parent``. The parent is kept alive for the test run (Qt owns the pane)."""
    from app.features.form_builder.integration.workbench import _PieceOps

    _KEEP.append(parent)
    pane = InsertPane(lambda _collapsed: None, parent, memory=memory, pieces=_PieceOps())  # type: ignore[arg-type]
    _KEEP.append(pane)
    return pane


def _rows(pane: InsertPane) -> list:
    return [pane.body.item(index).data(int(ROW_ROLE)) for index in range(pane.body.count())]


def test_recent_entries_move_to_the_front_and_stay_six(tmp_path: Path) -> None:
    store = InsertMemoryStore(str(tmp_path))
    for key in ("QLabel", "QComboBox", "QTabWidget"):
        store.note_used(key)
    store.note_used("QLabel")
    assert store.recent() == ("QLabel", "QTabWidget", "QComboBox")
    for key in ("QTextEdit", "QDial", "QSpinBox", "QCheckBox"):
        store.note_used(key)
    assert len(store.recent()) == 6
    assert store.recent()[0] == "QCheckBox"


def test_recent_entries_survive_a_new_pane_instance(tmp_path: Path, qapp: QApplication) -> None:
    del qapp
    parent = QWidget()
    store = InsertMemoryStore(str(tmp_path))
    store.note_used("QComboBox")
    store.note_used("QLabel")
    first = _pane(parent, store)
    assert [row.key for row in _rows(first) if row.kind == ENTRY][:2] == ["QLabel", "QComboBox"]
    fresh = _pane(QWidget(), InsertMemoryStore(str(tmp_path)))
    recent = [row for row in _rows(fresh) if row.kind == ENTRY][:2]
    assert [row.key for row in recent] == ["QLabel", "QComboBox"]


def test_clear_recently_used_empties_the_section(tmp_path: Path, qapp: QApplication) -> None:
    del qapp
    store = InsertMemoryStore(str(tmp_path))
    store.note_used("QComboBox")
    pane = _pane(QWidget(), store)
    store.clear_recent()
    pane._refill()  # noqa: SLF001
    assert not any(row.kind == "section" for row in _rows(pane))


@pytest.mark.parity("R3-133")
def test_the_view_toggle_and_folding_persist(tmp_path: Path, qapp: QApplication) -> None:
    del qapp
    store = InsertMemoryStore(str(tmp_path))
    pane = _pane(QWidget(), store)
    pane._choose_view("list")  # noqa: SLF001 - the same call the menu's action makes
    pane.set_category_expanded("Containers", False)
    assert store.view() == "list"
    assert store.expanded_states()["Containers"] is False
    reopened = _pane(QWidget(), InsertMemoryStore(str(tmp_path)))
    assert reopened._auto_icons() is False  # noqa: SLF001
    headers = {row.category: row for row in _rows(reopened) if row.kind == HEADER}
    assert headers["Containers"].expanded is False
    assert headers["Choices"].expanded is True


def test_freecad_starts_folded_and_the_user_can_open_it(tmp_path: Path, qapp: QApplication) -> None:
    del qapp
    pane = _pane(QWidget(), InMemoryInsertMemory())
    headers = {row.category: row for row in _rows(pane) if row.kind == HEADER}
    assert headers["FreeCAD"].expanded is False
    pane.set_category_expanded("FreeCAD", True)
    assert any(row.kind == ENTRY and row.category == "FreeCAD" for row in _rows(pane))


def test_category_headers_and_tiles_have_their_accessible_names(tmp_path: Path, qapp: QApplication) -> None:
    del qapp
    pane = _pane(QWidget(), InMemoryInsertMemory())
    names = {}
    for index in range(pane.body.count()):
        item = pane.body.item(index)
        names[item.data(int(ROW_ROLE)).key or item.data(int(ROW_ROLE)).title] = item.data(int(Qt.ItemDataRole.AccessibleTextRole))
    assert names["QComboBox"] == "Insert combo box"
    assert names["Containers"] == "Containers, 11 widgets, expanded"
    assert names["FreeCAD"] == "FreeCAD, 7 widgets, collapsed"
    assert pane.filter.accessibleName() == "Search widgets"
    assert pane.filter.placeholderText() == "Search widgets"


def test_a_tile_tooltip_has_name_class_and_description(tmp_path: Path, qapp: QApplication) -> None:
    del qapp
    pane = _pane(QWidget(), InMemoryInsertMemory())
    item = next(pane.body.item(index) for index in range(pane.body.count()) if pane.body.item(index).data(int(Qt.ItemDataRole.UserRole)) == "QComboBox")
    tip = item.toolTip()
    assert "<b>Combo box</b>" in tip
    assert "QComboBox" in tip
    assert "Pick one item from a drop-down list." in tip


def test_a_filter_with_no_match_says_so_and_offers_clear(tmp_path: Path, qapp: QApplication) -> None:
    del qapp
    pane = _pane(QWidget(), InMemoryInsertMemory())
    pane.filter.setText("zzqq")
    QApplication.processEvents()
    assert not pane.empty.isHidden()
    assert pane.empty_text.text() == "Nothing called “zzqq”. Try text, list or date."
    assert pane.body.isHidden()
    pane.clear_link.click()
    assert pane.filter.text() == ""
    assert pane.empty.isHidden()


def test_your_widgets_follow_the_document(qapp: QApplication) -> None:
    del qapp
    parent = QWidget()
    pane = _pane(parent, InMemoryInsertMemory())
    assert not any(row.kind == HEADER and row.category == "Your widgets" for row in _rows(pane))
    session = open_session(_CUSTOM, "/tmp/cbcs-m41-custom.ui")
    try:
        pane.bind_session(session)
        found = [row for row in _rows(pane) if row.kind == ENTRY and row.category == "Your widgets"]
        assert [row.key for row in found] == ["custom:Shop::Card"]
        assert found[0].description == "Your class Shop::Card, based on QFrame."
    finally:
        session.dispose()


def test_one_friendly_name_per_class_through_every_public_reader(qapp: QApplication) -> None:
    del qapp
    catalog = load_catalog()
    for entry in catalog.entries:
        if entry.freecad or entry.qt_class in ("spacer", "Line"):
            continue
        expected = catalog.friendly_for_class(entry.qt_class)
        assert friendly_of(entry.qt_class) == expected, entry.key
        assert class_words(entry.qt_class).friendly == expected, entry.key


def test_the_canvas_status_sentence_uses_the_catalog_name(qapp: QApplication) -> None:
    del qapp
    session = open_session(
        '<?xml version="1.0" encoding="UTF-8"?>\n<ui version="4.0"><class>F</class>'
        '<widget class="QWidget" name="F"><layout class="QVBoxLayout" name="v">'
        '<item><widget class="QListWidget" name="items"/></item></layout></widget></ui>\n',
        "/tmp/cbcs-m41-names.ui",
    )
    try:
        node = next(item.id for item in session.document.iter_widgets() if item.object_name == "items")
        sentence = hover_sentence(session.document, node, False)
        assert "List widget" in sentence
        assert "List widget" == load_catalog().friendly_for_class("QListWidget")
    finally:
        session.dispose()

