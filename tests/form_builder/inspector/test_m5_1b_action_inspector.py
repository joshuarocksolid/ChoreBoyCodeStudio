# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportOptionalMemberAccess=false
"""The action inspector (UX-MAIN-012, R3-140) and the menu inspector's single Title row."""

from __future__ import annotations

import pytest

from app.features.form_builder.engine.commands.catalog_ext.actions import GroupActions, NewAction
from app.features.form_builder.engine.commands.catalog_ext.main_window import AddEntry, AddMenu
from app.features.form_builder.engine.project.templates import build_template_ui
from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.ui4.writer import write_ui
from app.qt.QtWidgets import QCheckBox, QComboBox, QLabel, QLineEdit, QWidget
from tests.form_builder.inspector.test_inspector_round2 import _close, _pane

pytestmark = [pytest.mark.usefixtures("qapp"), pytest.mark.unit]


def _rows(pane) -> list:  # type: ignore[no-untyped-def]
    return sorted(w.objectName().split("formBuilder.row.")[1] for w in pane.findChildren(QWidget) if w.objectName().startswith("formBuilder.row.") and w.isVisibleTo(pane))


@pytest.mark.parity("R3-140")
def test_an_action_shows_its_rows_the_places_it_is_used_and_a_group_drop_down(qapp) -> None:  # type: ignore[no-untyped-def]
    window, pane, session, realizer = _pane(qapp, build_template_ui("main_window", "shop_window"))
    try:
        doc = session.document
        bar = doc.by_name("menubar")[0]
        menu = session.log.execute(AddMenu(bar, 0, "&File")).result
        session.log.execute(AddEntry(menu, 0, "Print", None, "the File menu"))
        action = doc.by_name("actionPrint")[0]
        other = session.log.execute(NewAction("Open")).result
        group = session.log.execute(GroupActions((action, other))).result
        session.selection.set((action,), source=SelectionSource.PROGRAM)
        pane.flush()
        qapp.processEvents()
        rows = _rows(pane)
        for key in ("action.text", "action.icon", "action.shortcut", "action.toolTip", "action.statusTip", "action.whatsThis",
                    "action.checkable", "action.enabled", "action.visible", "action.shortcutContext", "action.group"):
            assert key in rows, (key, rows)
        assert "action.checked" not in rows  # only while "Can be ticked" is on
        header = pane.findChild(QLabel, "formBuilder.inspectorCrumbs")
        assert header.text().startswith("Used in ") and "File" in header.text()
        # Text writes through; the object name stays.
        edit = pane.findChild(QWidget, "formBuilder.row.action.text").findChild(QLineEdit)
        edit.setText("Print receipt")
        edit.editingFinished.emit()
        assert 'Print receipt' in write_ui(doc).text and "actionPrint" in doc.names()
        # Can be ticked reveals Starts ticked.
        pane.findChild(QWidget, "formBuilder.row.action.checkable").findChild(QCheckBox).click()
        pane.flush()
        qapp.processEvents()
        assert "action.checked" in _rows(pane)
        # The Group drop-down lists the form's groups and None; the action is in the one just made.
        combo = pane.findChild(QWidget, "formBuilder.row.action.group").findChild(QComboBox)
        assert [combo.itemText(i) for i in range(combo.count())][0] == "None" and combo.count() == 2
        assert combo.currentIndex() == 1
        combo.setCurrentIndex(0)
        combo.activated.emit(0)
        assert session.log.undo_label() == "Change group of Print receipt"
        assert doc.parent(action).kind != "actiongroup"
        del group
    finally:
        _close(window, pane, realizer, session, qapp)


def test_a_menu_shows_one_title_row(qapp) -> None:  # type: ignore[no-untyped-def]
    window, pane, session, realizer = _pane(qapp, build_template_ui("main_window", "shop_window"))
    try:
        doc = session.document
        menu = session.log.execute(AddMenu(doc.by_name("menubar")[0], 0, "&File")).result
        session.selection.set((menu,), source=SelectionSource.PROGRAM)
        pane.flush()
        qapp.processEvents()
        titles = [w for w in pane.findChildren(QWidget) if w.objectName() in ("formBuilder.row.title", "formBuilder.row.menuTitle") and w.isVisibleTo(pane)]
        assert [w.objectName() for w in titles] == ["formBuilder.row.menuTitle"]
    finally:
        _close(window, pane, realizer, session, qapp)


def test_the_toolbar_side_is_four_segments_that_write_the_attribute(qapp) -> None:  # type: ignore[no-untyped-def]
    from app.features.form_builder.engine.commands.catalog_ext.main_window import AddMainWindowPart
    from app.qt.QtWidgets import QToolButton

    window, pane, session, realizer = _pane(qapp, build_template_ui("main_window", "shop_window"))
    try:
        doc = session.document
        toolbar = session.log.execute(AddMainWindowPart("toolbar")).result
        session.selection.set((toolbar,), source=SelectionSource.PROGRAM)
        pane.flush()
        qapp.processEvents()
        row = pane.findChild(QWidget, "formBuilder.row.toolbarSide")
        segments = {b.text(): b for b in row.findChildren(QToolButton) if b.text() != "\u21ba"}
        assert list(segments) == ["Top", "Bottom", "Left", "Right"] and segments["Top"].isChecked()
        segments["Left"].click()
        assert "Qt::LeftToolBarArea" in write_ui(doc).text
    finally:
        _close(window, pane, realizer, session, qapp)


def test_a_buttons_group_drop_down_makes_and_clears_a_group_and_the_summary_says_so(qapp) -> None:  # type: ignore[no-untyped-def]
    from app.features.form_builder.integration.chrome_text import selection_sentence

    window, pane, session, realizer = _pane(qapp)
    try:
        doc = session.document
        button = doc.by_name("okButton")[0]
        session.selection.set((button,), source=SelectionSource.PROGRAM)
        pane.flush()
        qapp.processEvents()
        combo = pane.findChild(QWidget, "formBuilder.row.buttonGroup").findChild(QComboBox)
        texts = [combo.itemText(i) for i in range(combo.count())]
        assert texts[0] == "None" and texts[-1] == "New group"
        combo.setCurrentIndex(len(texts) - 1)
        combo.activated.emit(len(texts) - 1)
        assert 'name="buttonGroup"' in write_ui(doc).text
        assert selection_sentence(doc, button, 1).endswith("· in button group buttonGroup")
        assert session.log.undo_label() == "Change button group of okButton"
    finally:
        _close(window, pane, realizer, session, qapp)
