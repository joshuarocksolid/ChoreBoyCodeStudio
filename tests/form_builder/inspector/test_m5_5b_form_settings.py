# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportOptionalMemberAccess=false
"""The form inspector's Code, Translation and Free placement groups (UX-FSET-001 ... 006)."""

from __future__ import annotations

from typing import Optional

import pytest

from app.features.form_builder.engine.commands.catalog_ext.form_fields import SetFormGrid, SetFormSetting
from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.ui4.schema import LayoutDefault
from app.features.form_builder.engine.ui4.writer import write_ui
from app.qt.QtCore import Qt
from app.qt.QtTest import QTest
from app.qt.QtWidgets import QCheckBox, QComboBox, QLabel, QLineEdit, QPushButton, QSpinBox, QToolButton, QWidget
from tests.form_builder.inspector.m5_5b_support import LAID_OUT, close, free_form, open_pane

pytestmark = [pytest.mark.unit, pytest.mark.usefixtures("qapp")]


def _show_form(pane, session) -> None:  # type: ignore[no-untyped-def]
    session.selection.clear(source=SelectionSource.PROGRAM)
    pane.flush()


def _open_group(pane, key: str, qapp) -> QWidget:  # type: ignore[no-untyped-def]
    toggle = pane.findChild(QToolButton, "formBuilder.group.%s" % key)
    assert toggle is not None, key
    if not toggle.isChecked():
        toggle.click()
    pane.flush()
    qapp.processEvents()
    body = pane.findChild(QWidget, "formBuilder.formSettings.%s" % key)
    assert body is not None and body.isVisible(), key
    return body


def _row(body: QWidget, key: str) -> QWidget:
    row = body.findChild(QWidget, "formBuilder.formSetting.%s" % key)
    assert row is not None, key
    return row


def test_the_three_groups_are_collapsed_until_opened(qapp) -> None:  # type: ignore[no-untyped-def]
    window, pane, session, realizer = open_pane(qapp, free_form())
    try:
        _show_form(pane, session)
        for key in ("code", "translation", "freePlacement"):
            toggle = pane.findChild(QToolButton, "formBuilder.group.%s" % key)
            assert toggle is not None and toggle.isVisible() and not toggle.isChecked(), key
            body = pane.findChild(QWidget, "formBuilder.formSettings.%s" % key)
            assert body is not None and not body.isVisible(), key
        assert [t.text() for t in (pane.findChild(QToolButton, "formBuilder.group.%s" % k) for k in ("code", "translation", "freePlacement"))] == [
            "CODE",
            "TRANSLATION",
            "FREE PLACEMENT",
        ]
    finally:
        close(window, pane, realizer, session, qapp)


def test_the_groups_show_with_the_root_widget_selected_and_not_with_another_widget(qapp) -> None:  # type: ignore[no-untyped-def]
    window, pane, session, realizer = open_pane(qapp, free_form())
    try:
        session.selection.set((session.document.root.id,), source=SelectionSource.PROGRAM)
        pane.flush()
        assert pane.findChild(QToolButton, "formBuilder.group.code").isVisible()
        session.selection.set((session.document.by_name("payButton")[0],), source=SelectionSource.PROGRAM)
        pane.flush()
        assert not pane.findChild(QToolButton, "formBuilder.group.code").isVisible()
    finally:
        close(window, pane, realizer, session, qapp)


def test_free_placement_shows_only_when_a_container_has_no_layout(qapp) -> None:  # type: ignore[no-untyped-def]
    window, pane, session, realizer = open_pane(qapp, LAID_OUT)
    try:
        _show_form(pane, session)
        assert pane.findChild(QToolButton, "formBuilder.group.code").isVisible()
        assert not pane.findChild(QToolButton, "formBuilder.group.freePlacement").isVisible()
    finally:
        close(window, pane, realizer, session, qapp)


@pytest.mark.parity("R3-185")
def test_a_text_row_writes_one_step_named_for_the_row_and_reset_removes_it(qapp) -> None:  # type: ignore[no-untyped-def]
    window, pane, session, realizer = open_pane(qapp, free_form())
    try:
        _show_form(pane, session)
        body = _open_group(pane, "code", qapp)
        edit = body.findChild(QLineEdit, "formBuilder.formSetting.author.edit")
        steps = len(session.log.entries())
        edit.setFocus()
        QTest.keyClicks(edit, "Pat")
        QTest.keyClick(edit, Qt.Key.Key_Return)
        qapp.processEvents()
        assert "<author>Pat</author>" in write_ui(session.document).text
        assert len(session.log.entries()) == steps + 1
        assert session.log.undo_label() == "Change form setting: author"
        row = _row(body, "author")
        reset = row.findChild(QToolButton, "formBuilder.rowReset")
        assert not reset.isHidden()
        reset.click()
        qapp.processEvents()
        assert "<author>" not in write_ui(session.document).text
        assert session.log.undo_label() == "Reset Author"
        # The same text typed again is not a second step.
        steps = len(session.log.entries())
        edit.setFocus()
        QTest.keyClick(edit, Qt.Key.Key_Return)
        assert len(session.log.entries()) == steps
    finally:
        close(window, pane, realizer, session, qapp)


@pytest.mark.parity("R3-186")
def test_default_gaps_check_box_and_numbers_write_layoutdefault(qapp) -> None:  # type: ignore[no-untyped-def]
    window, pane, session, realizer = open_pane(qapp, free_form())
    try:
        _show_form(pane, session)
        body = _open_group(pane, "code", qapp)
        box = body.findChild(QCheckBox, "formBuilder.formSetting.layoutdefault.check")
        gap = body.findChild(QSpinBox, "formBuilder.formSetting.layoutdefault.gap")
        margin = body.findChild(QSpinBox, "formBuilder.formSetting.layoutdefault.margin")
        assert not box.isChecked() and not gap.isEnabled() or not gap.parentWidget().isEnabled()
        box.click()
        assert session.document.ui.field("layoutdefault") == LayoutDefault(8, 8)
        gap.setFocus()
        gap.setValue(6)
        gap.editingFinished.emit()
        margin.setFocus()
        margin.setValue(12)
        margin.editingFinished.emit()
        assert session.document.ui.field("layoutdefault") == LayoutDefault(6, 12)
        assert session.log.undo_label() == "Change form setting: default gaps"
        box.click()
        assert session.document.ui.field("layoutdefault") is None
    finally:
        close(window, pane, realizer, session, qapp)


@pytest.mark.parity("R3-187")
@pytest.mark.parity("R3-188")
def test_function_names_are_checked_and_a_refusal_shows_under_the_row(qapp) -> None:  # type: ignore[no-untyped-def]
    window, pane, session, realizer = open_pane(qapp, free_form())
    try:
        _show_form(pane, session)
        body = _open_group(pane, "code", qapp)
        edit = body.findChild(QLineEdit, "formBuilder.formSetting.pixmapfunction.edit")
        edit.setFocus()
        edit.setText("load picture")
        edit.editingFinished.emit()
        row = _row(body, "pixmapfunction")
        note = row.findChildren(QLabel, "formBuilder.rowError")
        assert [label.text() for label in note] == ["Use a function name like margin_for."]
        assert "pixmapfunction" not in write_ui(session.document).text
        edit.setText("load_picture")
        edit.editingFinished.emit()
        assert "<pixmapfunction>load_picture</pixmapfunction>" in write_ui(session.document).text
        assert not row.findChildren(QLabel, "formBuilder.rowError")
        functions = _row(body, "layoutfunction")
        check = functions.findChild(QCheckBox, "formBuilder.formSetting.layoutfunction.check")
        check.click()
        gap = functions.findChild(QLineEdit, "formBuilder.formSetting.layoutfunction.gap")
        margin = functions.findChild(QLineEdit, "formBuilder.formSetting.layoutfunction.margin")
        gap.setText("spacing_for")
        gap.editingFinished.emit()
        margin.setText("margin_for")
        margin.editingFinished.emit()
        assert '<layoutfunction spacing="spacing_for" margin="margin_for"/>' in write_ui(session.document).text
        assert session.log.undo_label() == "Change form setting: gap functions"
    finally:
        close(window, pane, realizer, session, qapp)


@pytest.mark.parity("R3-189")
def test_extra_includes_add_edit_and_delete_lines_with_local_or_global(qapp) -> None:  # type: ignore[no-untyped-def]
    window, pane, session, realizer = open_pane(qapp, free_form())
    try:
        _show_form(pane, session)
        body = _open_group(pane, "code", qapp)
        add = body.findChild(QPushButton, "formBuilder.formSetting.includes.add")
        add.click()
        name = body.findChild(QLineEdit, "formBuilder.formSetting.includes.name0")
        name.setText("shop.h")
        name.editingFinished.emit()
        assert '<include location="local">shop.h</include>' in write_ui(session.document).text
        where = body.findChild(QComboBox, "formBuilder.formSetting.includes.where0")
        where.setCurrentIndex(1)
        where.activated.emit(1)
        assert '<include location="global">shop.h</include>' in write_ui(session.document).text
        assert session.log.undo_label() == "Change form setting: extra includes"
        body.findChild(QToolButton, "formBuilder.formSetting.includes.delete0").click()
        assert "<includes>" not in write_ui(session.document).text
    finally:
        close(window, pane, realizer, session, qapp)


@pytest.mark.parity("R3-190")
def test_export_macro_and_comment_keep_their_captions(qapp) -> None:  # type: ignore[no-untyped-def]
    window, pane, session, realizer = open_pane(qapp, free_form())
    try:
        _show_form(pane, session)
        body = _open_group(pane, "code", qapp)
        for key in ("exportmacro", "comment"):
            row = _row(body, key)
            assert [l.text() for l in row.findChildren(QLabel, "formBuilder.rowNote")] == ["Kept for Qt Designer and C++ code."]
        macro = body.findChild(QLineEdit, "formBuilder.formSetting.exportmacro.edit")
        macro.setText("SHOP_EXPORT")
        macro.editingFinished.emit()
        assert "<exportmacro>SHOP_EXPORT</exportmacro>" in write_ui(session.document).text
    finally:
        close(window, pane, realizer, session, qapp)


@pytest.mark.parity("R3-191")
@pytest.mark.parity("R3-192")
def test_translation_rows(qapp) -> None:  # type: ignore[no-untyped-def]
    window, pane, session, realizer = open_pane(qapp, free_form())
    try:
        _show_form(pane, session)
        body = _open_group(pane, "translation", qapp)
        check = body.findChild(QCheckBox, "formBuilder.formSetting.idbasedtr.check")
        check.click()
        assert 'idbasedtr="true"' in write_ui(session.document).text
        assert session.log.undo_label() == "Change form setting: translate by id"
        check.click()
        assert "idbasedtr" not in write_ui(session.document).text
        for key, attr in (("language", "language"), ("displayname", "displayname")):
            edit = body.findChild(QLineEdit, "formBuilder.formSetting.%s.edit" % key)
            edit.setText("Value")
            edit.editingFinished.emit()
            assert '%s="Value"' % attr in write_ui(session.document).text
        captions = [l.text() for l in body.findChildren(QLabel, "formBuilder.rowNote")]
        assert captions == [
            "Each text uses its translation ID instead of the English text.",
            "Kept for Qt Designer.",
            "Kept for Qt Designer.",
        ]
    finally:
        close(window, pane, realizer, session, qapp)


@pytest.mark.parity("R3-193")
def test_the_older_file_setting_shows_only_when_present_and_remove_is_one_step(qapp) -> None:  # type: ignore[no-untyped-def]
    window, pane, session, realizer = open_pane(qapp, free_form(' stdSetDef="1"'))
    try:
        _show_form(pane, session)
        body = _open_group(pane, "code", qapp)
        row = _row(body, "stdSetDef")
        assert row.isVisible() and not _row(body, "stdsetdef").isVisible()
        assert row.findChild(QLabel, "formBuilder.formSetting.stdSetDef.value").text() == 'stdSetDef = "1"'
        assert [l.text() for l in row.findChildren(QLabel, "formBuilder.rowNote")] == ["Kept as is. Newer forms don't use it."]
        steps = len(session.log.entries())
        row.findChild(QPushButton, "formBuilder.formSetting.stdSetDef.remove").click()
        assert "stdSetDef" not in write_ui(session.document).text
        assert len(session.log.entries()) == steps + 1 and session.log.undo_label() == "Remove older file setting"
        pane.flush()
        assert not row.isVisible()
    finally:
        close(window, pane, realizer, session, qapp)


@pytest.mark.parity("R3-222")
def test_free_placement_rows_write_the_grid_only_when_it_differs(qapp) -> None:  # type: ignore[no-untyped-def]
    window, pane, session, realizer = open_pane(qapp, free_form())
    try:
        _show_form(pane, session)
        body = _open_group(pane, "freePlacement", qapp)
        assert [l.text() for l in body.findChildren(QLabel, "formBuilder.rowNote")][0] == (
            "Only for containers without a layout. Alt+arrows move by one step."
        )
        across = body.findChild(QSpinBox, "formBuilder.formSetting.grid.across")
        down = body.findChild(QSpinBox, "formBuilder.formSetting.grid.down")
        assert (across.minimum(), across.maximum(), across.value(), down.value()) == (2, 100, 8, 8)
        across.setFocus()
        across.setValue(8)
        across.editingFinished.emit()
        assert "designerdata" not in write_ui(session.document).text
        across.setValue(16)
        across.editingFinished.emit()
        assert session.log.undo_label() == "Change form setting: step across"
        assert "gridDeltaX" in write_ui(session.document).text and "gridDeltaY" not in write_ui(session.document).text
        show = body.findChild(QCheckBox, "formBuilder.formSetting.grid.show")
        snap = body.findChild(QCheckBox, "formBuilder.formSetting.grid.snap")
        assert show.isChecked() and snap.isChecked()
        show.click()
        snap.click()
        text = write_ui(session.document).text
        assert "gridVisible" in text and "gridSnapX" in text and "gridSnapY" in text
        reset = _row(body, "grid.across").findChild(QToolButton, "formBuilder.rowReset")
        reset.click()
        assert "gridDeltaX" not in write_ui(session.document).text
        assert session.log.undo_label() == "Reset Step across"
    finally:
        close(window, pane, realizer, session, qapp)


def test_a_change_from_elsewhere_refreshes_the_open_rows(qapp) -> None:  # type: ignore[no-untyped-def]
    window, pane, session, realizer = open_pane(qapp, free_form())
    try:
        _show_form(pane, session)
        body = _open_group(pane, "code", qapp)
        session.log.execute(SetFormSetting("author", "Elsewhere"))
        session.log.execute(SetFormSetting("layoutdefault", LayoutDefault(5, 7)))
        pane.flush()
        assert body.findChild(QLineEdit, "formBuilder.formSetting.author.edit").text() == "Elsewhere"
        assert body.findChild(QSpinBox, "formBuilder.formSetting.layoutdefault.gap").value() == 5
        session.log.undo()
        session.log.undo()
        pane.flush()
        assert body.findChild(QLineEdit, "formBuilder.formSetting.author.edit").text() == ""
        # A group that was closed while the form changed is current when it opens.
        toggle = pane.findChild(QToolButton, "formBuilder.group.translation")
        session.log.execute(SetFormSetting("language", "Python"))
        pane.flush()
        translation = _open_group(pane, "translation", qapp)
        assert translation.findChild(QLineEdit, "formBuilder.formSetting.language.edit").text() == "Python"
        assert toggle.isChecked()
    finally:
        close(window, pane, realizer, session, qapp)


def test_every_row_has_an_accessible_name(qapp) -> None:  # type: ignore[no-untyped-def]
    window, pane, session, realizer = open_pane(qapp, free_form(' stdsetdef="1"'))
    try:
        _show_form(pane, session)
        for key in ("code", "translation", "freePlacement"):
            body = _open_group(pane, key, qapp)
            for kind in (QLineEdit, QCheckBox, QSpinBox, QComboBox):
                for control in body.findChildren(kind):
                    if control.objectName() and not control.objectName().startswith("qt_"):
                        assert control.accessibleName().startswith("Form setting:"), control.objectName()
    finally:
        close(window, pane, realizer, session, qapp)


def test_the_form_menu_item_comes_from_the_contributor_registry() -> None:
    from app.features.form_builder.integration.form_menu_ext import default_registry

    found = [(module, item) for module, item in default_registry().items() if item.command_id == "form.action.formSettings"]
    assert [(m.rsplit(".", 1)[-1], item.path) for m, item in found] == [("form_settings", ("Form settings…",))]


def test_reveal_selects_the_form_opens_code_and_focuses_author(qapp, tmp_path) -> None:  # type: ignore[no-untyped-def]
    from app.features.form_builder.integration.form_menu_ext.form_settings import reveal
    from tests.form_builder.qtside.test_m5_5b_canvas import _open_big

    host, surface = _open_big(tmp_path / "till.ui", free_form())
    try:
        surface.session.selection.set((surface.session.document.by_name("payButton")[0],), source=SelectionSource.PROGRAM)
        qapp.processEvents()
        assert reveal(surface) is True
        assert surface.session.selection.state.ids == ()
        focus = qapp.focusWidget()
        assert focus is not None and focus.objectName() == "formBuilder.formSetting.author.edit"
        assert surface.workbench.inspector.findChild(QToolButton, "formBuilder.group.code").isChecked()
    finally:
        surface.release()
        host.close()
