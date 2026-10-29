# pyright: reportAttributeAccessIssue=false
"""The Actions section: rows, used-in lines, Alt+5, and the keys of UX-MAIN-011."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.features.form_builder.engine.commands.catalog_ext.actions import NewAction
from app.features.form_builder.engine.commands.catalog_ext.main_window import AddEntry, AddMainWindowPart, AddMenu
from app.features.form_builder.engine.query import actions as q
from app.qt.QtCore import Qt
from app.qt.QtTest import QTest
from app.qt.QtWidgets import QWidget
from tests.unit.features.form_builder.test_workbench import _open

pytestmark = [pytest.mark.usefixtures("qapp"), pytest.mark.unit]

_MAIN = (
    '<?xml version="1.0" encoding="UTF-8"?>\n<ui version="4.0">\n <class>shop</class>\n'
    ' <widget class="QMainWindow" name="shop">\n'
    '  <widget class="QWidget" name="centralwidget"/>\n </widget>\n <resources/>\n <connections/>\n</ui>\n'
)


def test_alt_5_focuses_the_actions_section_and_rows_say_where_actions_are_used(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    host = QWidget()
    surface = _open(host, _MAIN, tmp_path / "shop.ui")
    host.resize(1200, 800)
    host.show()
    surface.show()
    qapp.processEvents()
    try:
        session = surface.session
        bar = session.log.execute(AddMainWindowPart("menubar")).result
        menu = session.log.execute(AddMenu(bar, 0, "&File")).result
        session.log.execute(AddEntry(menu, 0, "Print receipt"))
        session.log.execute(NewAction("Lonely"))
        qapp.processEvents()
        qapp.processEvents()
        bench = surface.workbench
        pane = bench.section_widget("actions")
        assert pane is not None and bench.focus_section("actions")
        qapp.processEvents()
        assert pane.row_texts() == [("Print receipt", "", "File menu"), ("Lonely", "", "Not used")]
        assert pane._title.text() == "ACTIONS 2"
        # A printable key types into the filter; no match leaves one row that creates the action.
        pane._tree.setCurrentItem(pane._tree.topLevelItem(0))
        QTest.keyClicks(pane._tree, "zzz")
        assert pane._filter.text() == "zzz"
        qapp.processEvents()
        assert pane.row_texts() == [("New action “zzz”", "", "")]
        pane._tree.setCurrentItem(pane._tree.topLevelItem(0))
        QTest.keyClick(pane._tree, Qt.Key.Key_Return)
        qapp.processEvents()
        assert "actionZzz" in session.document.names()
        # Delete on a used action asks first; cancel leaves it.
        asked = []
        pane._confirm = lambda sentence, ok: asked.append(sentence) or False
        pane._tree.clearSelection()
        pane._filter.clear()
        qapp.processEvents()
        pane._tree.topLevelItem(0).setSelected(True)
        pane._tree.setCurrentItem(pane._tree.topLevelItem(0))
        QTest.keyClick(pane._tree, Qt.Key.Key_Delete)
        assert asked == ["Delete the action Print receipt? It's on File menu."]
        assert "actionPrint_receipt" in session.document.names()
    finally:
        host.deleteLater()
