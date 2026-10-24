"""A form tab in a real MainWindow: keys reach their widgets and reveal survives an XML apply."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.features.form_builder.install import form_builder_enabled  # noqa: E402
from app.features.form_builder.integration.problems_bridge import code_diagnostics_for_form  # noqa: E402
from app.qt.QtCore import QEvent, QObject, Qt  # noqa: E402
from app.qt.QtTest import QTest  # noqa: E402
from app.qt.QtWidgets import QApplication, QTreeWidget, QWidget  # noqa: E402
from app.shell.main_window import MainWindow  # noqa: E402
from testing.main_window_shutdown import shutdown_main_window_for_test  # noqa: E402

pytestmark = pytest.mark.unit

_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Invoice</class>
 <widget class="QWidget" name="Invoice">
  <layout class="QFormLayout" name="formLayout">
   <item row="0" column="0">
    <widget class="QLabel" name="title">
     <property name="text"><string>Invoice entry</string></property>
    </widget>
   </item>
   <item row="1" column="0">
    <widget class="QLabel" name="shopName">
     <property name="text"><string>a<b>x</b>c</string></property>
    </widget>
   </item>
   <item row="2" column="0">
    <widget class="QPushButton" name="okButton">
     <property name="text"><string>OK</string></property>
    </widget>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


class _KeyLog(QObject):
    """Records key presses that reach the watched widget (not eaten by a shortcut)."""

    def __init__(self) -> None:
        super().__init__()
        self.keys: list = []

    def eventFilter(self, watched: object, event: object) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.KeyPress:  # type: ignore[attr-defined]
            self.keys.append(event.key())  # type: ignore[attr-defined]
        return False


def _require_feature() -> None:
    if not form_builder_enabled():
        pytest.skip("form builder is registered on PySide6")


def _open_form(window: MainWindow, qapp: QApplication, path: Path) -> object:
    path.write_text(_FORM, encoding="utf-8")
    assert window._editor_tab_factory.open_file_in_editor(str(path))  # noqa: SLF001
    # Without a project the center shows the welcome page. Show the editors.
    window._center_stack.setCurrentIndex(1)  # noqa: SLF001
    window.resize(1400, 900)
    window.show()
    window.activateWindow()
    qapp.processEvents()
    surface = window._tab_content_registry.surface_for_path(str(path))  # noqa: SLF001
    assert surface is not None
    return surface


def test_down_in_the_outline_moves_the_current_item(tmp_path: Path, qapp: QApplication) -> None:
    _require_feature()
    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    try:
        surface = _open_form(window, qapp, tmp_path / "invoice.ui")
        tree = surface.findChild(QTreeWidget, "formBuilder.structure")  # type: ignore[attr-defined]
        assert tree is not None and tree.isVisible()
        assert tree.topLevelItemCount() > 0
        tree.setCurrentItem(tree.topLevelItem(0))
        tree.setFocus()
        qapp.processEvents()
        before = tree.currentItem()
        QTest.keyClick(tree, Qt.Key_Down)
        qapp.processEvents()
        assert tree.currentItem() is not None
        assert tree.currentItem() is not before

        log = _KeyLog()
        tree.installEventFilter(log)
        QTest.keyClick(tree, Qt.Key_A, Qt.ControlModifier)
        QTest.keyClick(tree, Qt.Key_Return)
        qapp.processEvents()
        tree.removeEventFilter(log)
        assert Qt.Key_A in log.keys
        assert Qt.Key_Return in log.keys
    finally:
        shutdown_main_window_for_test(window, qapp)


def test_tab_on_the_canvas_selects_the_next_widget(tmp_path: Path, qapp: QApplication) -> None:
    _require_feature()
    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    try:
        surface = _open_form(window, qapp, tmp_path / "invoice.ui")
        canvas = surface.findChild(QWidget, "formBuilder.canvas")  # type: ignore[attr-defined]
        assert canvas is not None
        canvas.setFocus()
        qapp.processEvents()
        focused = qapp.focusWidget()
        assert focused is canvas or canvas.isAncestorOf(focused)
        log = _KeyLog()
        focused.installEventFilter(log)
        QTest.keyClick(focused, Qt.Key_A, Qt.ControlModifier)
        QTest.keyClick(focused, Qt.Key_Return)
        qapp.processEvents()
        focused.removeEventFilter(log)
        assert Qt.Key_A in log.keys
        assert Qt.Key_Return in log.keys
        QTest.keyClick(focused, Qt.Key_Tab)
        qapp.processEvents()
        after = qapp.focusWidget()
        assert after is canvas or canvas.isAncestorOf(after)
        tree = surface.findChild(QTreeWidget, "formBuilder.structure")  # type: ignore[attr-defined]
        assert tree is not None
        current = tree.currentItem()
        assert current is not None
        assert current.text(0) == "QLabel  title"
    finally:
        shutdown_main_window_for_test(window, qapp)


def test_no_window_scope_form_action_shares_a_shell_key(tmp_path: Path, qapp: QApplication) -> None:
    """install_form_builder registers the form rows. Menu hints must stay labels."""
    _require_feature()
    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    try:
        registry = window.menu_registry
        assert registry is not None
        context = getattr(Qt, "ShortcutContext", Qt)
        window_scope = {getattr(context, "WindowShortcut"), getattr(context, "ApplicationShortcut")}

        def keys(prefix_is_form: bool) -> dict:
            found = {}
            for action_id, action in registry.actions.items():
                if action is None or str(action_id).startswith("form.action.") != prefix_is_form:
                    continue
                key = action.shortcut().toString()
                if key and action.shortcutContext() in window_scope:
                    found.setdefault(key, []).append(str(action_id))
            return found

        shell = keys(False)
        form = keys(True)
        shared = sorted("%s %s" % (key, ids) for key, ids in form.items() if key in shell)
        assert shared == []
        horizontal = registry.actions["form.action.layoutHorizontal"]
        assert horizontal.shortcut().isEmpty() or horizontal.shortcutContext() not in window_scope
        assert "Ctrl+1" in horizontal.text()
        insert = registry.actions["form.action.insert"]
        assert insert.shortcut().isEmpty() or insert.shortcutContext() not in window_scope
        assert "/" in insert.text()

        # Settings apply re-sets every menu action's key from the effective map.
        window._shell_preferences_runtime.apply_shortcut_overrides_runtime()  # noqa: SLF001
        assert keys(True).get("Ctrl+1") is None
        assert keys(True).get("/") is None
    finally:
        shutdown_main_window_for_test(window, qapp)


def test_reveal_after_an_xml_apply_selects_the_live_node(tmp_path: Path, qapp: QApplication) -> None:
    _require_feature()
    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    path = tmp_path / "invoice.ui"
    try:
        surface = _open_form(window, qapp, path)
        session = surface._session  # type: ignore[attr-defined]  # noqa: SLF001
        before = [d for d in session.diagnostics.all() if d.code == "FB005"]
        assert before and before[0].location.object_name == "shopName"
        old_id = before[0].location.node_id

        surface.toggle_source_view()  # type: ignore[attr-defined]
        qapp.processEvents()
        editor = surface.source_editor()  # type: ignore[attr-defined]
        assert editor is not None
        editor.setPlainText(editor.toPlainText().replace("Invoice entry", "Invoice entry form"))
        surface.toggle_source_view()  # type: ignore[attr-defined]
        qapp.processEvents()
        live = session.document.by_name("shopName")[0]
        assert live != old_id
        assert session.document.get(old_id) is None

        after = [d for d in session.diagnostics.all() if d.code == "FB005"]
        assert after and after[0].location.node_id == live
        rows = code_diagnostics_for_form(str(path), session.diagnostics.all())
        row = [r for r in rows if "shopName" in r.message or (r.detail or {}).get("fb_object") == "shopName"][0]

        assert surface.reveal(row.line_number, row.detail)  # type: ignore[attr-defined]
        qapp.processEvents()
        assert session.selection.state.current == live
        assert "shopName" in surface.editor_status_sentence()  # type: ignore[attr-defined]
    finally:
        shutdown_main_window_for_test(window, qapp)


def test_reveal_with_a_stale_id_falls_back_to_the_name_and_keeps_focus_when_nothing_matches(
    tmp_path: Path, qapp: QApplication
) -> None:
    _require_feature()
    from app.features.form_builder.engine.diagnostics import (
        DiagnosticLocation,
        FormDiagnostic,
        Severity,
    )

    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    try:
        surface = _open_form(window, qapp, tmp_path / "invoice.ui")
        session = surface._session  # type: ignore[attr-defined]  # noqa: SLF001
        stale = FormDiagnostic(
            code="FB003",
            severity=Severity.ERROR,
            message="Stale.",
            location=DiagnosticLocation(node_id=9999, object_name="okButton"),
            source="test",
        )
        session.diagnostics.publish("test", (stale,))
        assert surface.reveal(1, {"fb_key": stale.key, "fb_object": "okButton"})  # type: ignore[attr-defined]
        qapp.processEvents()
        assert session.selection.state.current == session.document.by_name("okButton")[0]

        gone = FormDiagnostic(
            code="FB003",
            severity=Severity.ERROR,
            message="Gone.",
            location=DiagnosticLocation(node_id=9998, object_name="nobody"),
            source="test",
        )
        session.diagnostics.publish("test", (gone,))
        tree = surface._workbench.outline.tree  # type: ignore[attr-defined]  # noqa: SLF001
        tree.setFocus()
        qapp.processEvents()
        surface.reveal(0, {"fb_key": gone.key, "fb_object": "nobody"})  # type: ignore[attr-defined]
        qapp.processEvents()
        qapp.processEvents()
        assert qapp.focusWidget() is tree
    finally:
        shutdown_main_window_for_test(window, qapp)


def _status_label(window: MainWindow) -> object:
    from app.qt.QtWidgets import QLabel

    label = window.findChild(QLabel, "shell.editorStatusLabel")
    assert label is not None
    return label


def test_reveal_applies_pending_xml_edits_first(tmp_path: Path, qapp: QApplication) -> None:
    _require_feature()
    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    try:
        surface = _open_form(window, qapp, tmp_path / "invoice.ui")
        session = surface._session  # type: ignore[attr-defined]  # noqa: SLF001
        surface.toggle_source_view()  # type: ignore[attr-defined]
        qapp.processEvents()
        editor = surface.source_editor()  # type: ignore[attr-defined]
        editor.setPlainText(editor.toPlainText().replace("Invoice entry", "Invoice entry form"))
        qapp.processEvents()
        assert surface.reveal(1, {"fb_object": "okButton"})  # type: ignore[attr-defined]
        qapp.processEvents()
        assert session.selection.state.current == session.document.by_name("okButton")[0]
        assert surface.content_source().mode == "visual"  # type: ignore[attr-defined]
        assert "Invoice entry form" in session.text()
    finally:
        shutdown_main_window_for_test(window, qapp)


def test_an_inert_shell_key_explains_itself_on_the_status_bar(tmp_path: Path, qapp: QApplication) -> None:
    _require_feature()
    from app.features.form_builder.engine.shell_commands import INERT_STATUS

    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    try:
        surface = _open_form(window, qapp, tmp_path / "invoice.ui")
        assert INERT_STATUS == "Not used in the form designer."
        tree = surface._workbench.outline.tree  # type: ignore[attr-defined]  # noqa: SLF001
        tree.setFocus()
        qapp.processEvents()
        for key, mods in (
            (Qt.Key_H, Qt.ControlModifier),
            (Qt.Key_G, Qt.ControlModifier),
            (Qt.Key_Slash, Qt.ControlModifier),
            (Qt.Key_F9, Qt.NoModifier),
        ):
            surface._inert_note = ""  # type: ignore[attr-defined]  # noqa: SLF001
            QTest.keyClick(tree, key, mods)
            qapp.processEvents()
            assert _status_label(window).text() == INERT_STATUS, key  # type: ignore[attr-defined]
    finally:
        shutdown_main_window_for_test(window, qapp)


def test_tab_leaves_the_inspector(tmp_path: Path, qapp: QApplication) -> None:
    _require_feature()
    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    try:
        surface = _open_form(window, qapp, tmp_path / "invoice.ui")
        body = surface.findChild(QWidget, "formBuilder.inspectorBody")  # type: ignore[attr-defined]
        assert body is not None and body.isVisible()
        body.setFocus()
        qapp.processEvents()
        assert qapp.focusWidget() is body
        # With "Show in Problems" showing, the first Tab lands on the link.
        for _ in range(2):
            if qapp.focusWidget() is not body:
                break
            QTest.keyClick(body, Qt.Key_Tab)
            qapp.processEvents()
        assert qapp.focusWidget() is not body
    finally:
        shutdown_main_window_for_test(window, qapp)


def test_tab_still_indents_in_the_xml_view(tmp_path: Path, qapp: QApplication) -> None:
    _require_feature()
    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    try:
        surface = _open_form(window, qapp, tmp_path / "invoice.ui")
        surface.toggle_source_view()  # type: ignore[attr-defined]
        qapp.processEvents()
        editor = surface.source_editor()  # type: ignore[attr-defined]
        editor.setFocus()
        qapp.processEvents()
        before = editor.toPlainText()
        QTest.keyClick(editor, Qt.Key_Tab)
        qapp.processEvents()
        assert editor.toPlainText() != before
        assert qapp.focusWidget() is editor
    finally:
        shutdown_main_window_for_test(window, qapp)


def test_show_in_problems_link_uses_a_token_colour_and_takes_the_keyboard(
    tmp_path: Path, qapp: QApplication
) -> None:
    _require_feature()
    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    try:
        surface = _open_form(window, qapp, tmp_path / "invoice.ui")
        qapp.processEvents()
        body = surface.findChild(QWidget, "formBuilder.inspectorBody")  # type: ignore[attr-defined]
        assert "Show in Problems" in body.text()  # type: ignore[attr-defined]
        tokens = window._shell_theme_workflow.resolve_theme_tokens()  # noqa: SLF001
        assert ("color:%s" % tokens.text_primary).lower() in body.text().replace(" ", "").lower()  # type: ignore[attr-defined]
        flags = body.textInteractionFlags()  # type: ignore[attr-defined]
        keyboard = getattr(Qt, "TextInteractionFlag", Qt).LinksAccessibleByKeyboard
        assert flags & keyboard
    finally:
        shutdown_main_window_for_test(window, qapp)


def test_the_tree_lock_draws_its_shackle_in_the_muted_token(tmp_path: Path, qapp: QApplication) -> None:
    from app.core import constants
    from app.core.models import LoadedProject, ProjectFileEntry, ProjectMetadata
    from app.qt.QtGui import QColor
    from app.shell.theme_tokens import tokens_from_palette
    from app.shell.tree_item_roles import TREE_ROLE_RELATIVE_PATH

    root = tmp_path / "project"
    forms = root / "forms"
    forms.mkdir(parents=True)
    (forms / "invoice.ui").write_text(_FORM, encoding="utf-8")
    (forms / "ui_invoice.py").write_text("label = 1\n", encoding="utf-8")
    entries = [
        ProjectFileEntry(relative_path="forms", absolute_path=str(forms.resolve()), is_directory=True),
        ProjectFileEntry(
            relative_path="forms/ui_invoice.py",
            absolute_path=str((forms / "ui_invoice.py").resolve()),
            is_directory=False,
        ),
        ProjectFileEntry(
            relative_path="forms/invoice.ui",
            absolute_path=str((forms / "invoice.ui").resolve()),
            is_directory=False,
        ),
    ]
    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    try:
        dark = tokens_from_palette(qapp.palette(), force_mode=constants.UI_THEME_MODE_DARK)
        window._shell_theme_workflow.resolve_theme_tokens = lambda: dark  # type: ignore[method-assign]  # noqa: SLF001
        loaded = LoadedProject(
            project_root=str(root.resolve()),
            manifest_path=str((root / "cbcs" / "project.json").resolve()),
            metadata=ProjectMetadata(schema_version=1, name="Tree", default_entry="forms/invoice.ui"),
            entries=entries,
        )
        window._loaded_project = loaded  # noqa: SLF001
        window._project_tree_ui_workflow.populate_project_tree(loaded)  # noqa: SLF001
        item = None
        for candidate in window._project_tree_ui_workflow.iter_project_tree_items():  # noqa: SLF001
            if str(candidate.data(0, TREE_ROLE_RELATIVE_PATH) or "") == "forms":
                window._project_tree_presenter.ensure_children_loaded(candidate)  # noqa: SLF001
        for candidate in window._project_tree_ui_workflow.iter_project_tree_items():  # noqa: SLF001
            if str(candidate.data(0, TREE_ROLE_RELATIVE_PATH) or "") == "forms/ui_invoice.py":
                item = candidate
        assert item is not None
        image = item.icon(0).pixmap(16, 16).toImage()
        want = QColor(dark.text_muted)
        body = image.pixelColor(8, 11)
        assert (body.red(), body.green(), body.blue()) == (want.red(), want.green(), want.blue())
        shackle = [
            image.pixelColor(x, y).alpha() for y in range(1, 6) for x in range(16)
        ]
        assert max(shackle) > 128
    finally:
        shutdown_main_window_for_test(window, qapp)
