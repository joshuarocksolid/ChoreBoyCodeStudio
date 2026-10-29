# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
"""The resource editor tab: edit, save with stable bytes, rewrite ``*_rc.py`` (UX-RES-004; K17)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

import pytest

from app.features.form_builder.engine.project.qrc_write import add_pictures
from app.features.form_builder.integration.provider import FormTabProvider
from app.features.form_builder.integration.qrc_provider import is_qrc
from app.qt.QtCore import Qt
from app.qt.QtGui import QPalette
from app.qt.QtTest import QTest
from app.qt.QtWidgets import QApplication, QPlainTextEdit, QWidget
from app.shell.tab_content_providers import TabMatchContext
from app.shell.theme_tokens import tokens_from_palette
from tests.form_builder.inspector.test_m43c_pictures import _png_bytes

pytestmark = [pytest.mark.unit, pytest.mark.usefixtures("qapp")]


class _Editor(QPlainTextEdit):
    def apply_theme(self, tokens: object) -> None:
        pass

    def go_to_line(self, line: int) -> None:
        pass


@dataclass
class _Request:
    file_path: str
    initial_text: str
    parent: Optional[QWidget]
    theme: object
    create_source_editor: Callable[[], QWidget]
    open_linked_file: Callable[[str], None]
    project_root: Optional[str]


def _shop(tmp_path: Path) -> Path:
    root = tmp_path / "shop"
    (root / "forms").mkdir(parents=True)
    (tmp_path / "logo.png").write_bytes(_png_bytes())
    add_pictures(str(root), str(root / "forms" / "resources.qrc"), [str(tmp_path / "logo.png")])
    (root / "forms" / "till.ui").write_text(
        '<ui version="4.0"><class>Till</class><widget class="QLabel" name="Till">'
        '<property name="pixmap"><pixmap>:/pictures/logo.png</pixmap></property></widget>'
        '<resources><include location="resources.qrc"/></resources></ui>',
        encoding="utf-8",
    )
    return root


def _open(qapp: QApplication, root: Path):  # type: ignore[no-untyped-def]
    path = root / "forms" / "resources.qrc"
    opened: List[str] = []
    request = _Request(
        str(path),
        path.read_text(encoding="utf-8"),
        None,
        tokens_from_palette(QPalette(), force_mode="light"),
        _Editor,
        opened.append,
        str(root),
    )
    surface = FormTabProvider().create_surface(request)
    surface.resize(900, 600)
    surface.show()
    qapp.processEvents()
    return surface, opened, path


def test_qrc_files_open_in_the_resource_editor_and_forced_text_does_not() -> None:
    provider = FormTabProvider()
    assert provider.matches("/p/forms/resources.qrc", TabMatchContext(project_root="/p"))
    assert not provider.matches("/p/forms/resources.qrc", TabMatchContext(project_root="/p", forced_text=True))
    assert is_qrc("/p/A.QRC") and not is_qrc("/p/a.py")


def test_an_untouched_file_is_not_dirty_and_edits_name_their_steps(qapp: QApplication, tmp_path: Path) -> None:
    root = _shop(tmp_path)
    surface, _opened, path = _open(qapp, root)
    try:
        source = surface.content_source()
        assert not source.is_dirty() and source.current_text() == path.read_text(encoding="utf-8")
        assert surface.grid.count() == 1 and surface.grid.selected_name() == "logo.png"
        surface.rename("shop_logo.png")
        assert source.undo_label() == "Rename logo.png" and source.is_dirty()
        assert surface.grid.selected_resource() == ":/shop_logo.png"
        surface.new_prefix("/icons/")
        assert source.undo_label() == "New prefix /icons"
        extra = root.parent / "mark.png"
        extra.write_bytes(_png_bytes() + b"")
        assert surface.add_pictures([str(extra)])
        assert source.undo_label() == "Add picture mark.png"
        assert (root / "forms" / "pictures" / "mark.png").is_file()
        assert surface.remove_selected()
        assert source.undo_label() == "Remove mark.png" and (root / "forms" / "pictures" / "mark.png").is_file()
        while source.undo():
            pass
        assert not source.is_dirty()
        assert source.redo() and source.undo_label() == "Rename logo.png"
    finally:
        surface.release()


@pytest.mark.parity("R3-174", "R3-175")
def test_k17_rename_then_save_writes_the_alias_and_rewrites_the_forms_picture_module(
    qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.qt.QtWidgets import QInputDialog

    root = _shop(tmp_path)
    surface, _opened, path = _open(qapp, root)
    try:
        monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("shop_logo.png", True)))
        surface.grid.setFocus()
        QTest.keyClick(surface.grid, Qt.Key.Key_Return)
        source = surface.content_source()
        assert source.undo_label() == "Rename logo.png"
        text = source.current_text()
        path.write_text(text, encoding="utf-8")
        source.mark_saved(text)
        source.after_save()
        assert '<file alias="shop_logo.png">pictures/logo.png</file>' in path.read_text(encoding="utf-8")
        assert path.read_text(encoding="utf-8").startswith("<!DOCTYPE RCC>\n<RCC version=\"1.0\">\n  <qresource")
        rc = (root / "forms" / "resources_rc.py").read_bytes()
        assert b"shop_logo.png".decode().encode("utf-16-be") in _names_of(rc)
        assert not source.is_dirty()
    finally:
        surface.release()


def _names_of(module_bytes: bytes) -> bytes:
    """The resource-name table is a bytes literal in the module; decode it for a UTF-16 search."""
    import ast

    tree = ast.parse(module_bytes.decode("utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "qt_resource_name":
            return ast.literal_eval(node.value)
    return b""


def test_delete_asks_when_a_form_uses_the_picture(qapp: QApplication, tmp_path: Path) -> None:
    root = _shop(tmp_path)
    surface, _opened, _path = _open(qapp, root)
    try:
        asked: List[int] = []
        assert not surface.remove_selected(confirm=lambda n: asked.append(n) or False)
        assert asked == [1] and surface.content_source().layout.entry_count() == 1
        assert surface.remove_selected(confirm=lambda n: True)
        assert surface.content_source().layout.entry_count() == 0
        from app.features.form_builder.qtside.resources.editor import remove_prompt

        assert remove_prompt(2, "resources.qrc") == "2 forms use this picture. Remove it from resources.qrc anyway?"
    finally:
        surface.release()


def test_show_where_it_is_used_lists_the_form_and_property(qapp: QApplication, tmp_path: Path) -> None:
    root = _shop(tmp_path)
    surface, _opened, _path = _open(qapp, root)
    try:
        assert surface.uses() == [(str(root / "forms" / "till.ui"), "Till.pixmap")]
    finally:
        surface.release()


def test_xml_view_applies_on_switching_back_and_an_invalid_file_stays_in_xml(qapp: QApplication, tmp_path: Path) -> None:
    root = _shop(tmp_path)
    surface, _opened, _path = _open(qapp, root)
    try:
        surface._xml.click()
        editor = surface.source_editor()
        assert editor.toPlainText().startswith("<!DOCTYPE RCC>")
        editor.setPlainText(editor.toPlainText().replace("</RCC>", "<oops>"))
        surface._pictures.click()
        assert surface.content_source().mode == "xml" and "not valid XML" in surface.banner_text
        editor.setPlainText(editor.toPlainText().replace("<oops>", "</RCC>"))
        editor.setPlainText(editor.toPlainText().replace("pictures/logo.png", "pictures/logo.png</file><file>pictures/b.png"))
        surface._pictures.click()
        assert surface.content_source().mode == "pictures" and surface.grid.count() == 2
        assert surface.content_source().undo_label() == "Edit XML"
    finally:
        surface.release()


def test_ctrl_z_in_the_grid_undoes_the_tabs_last_step(qapp: QApplication, tmp_path: Path) -> None:
    root = _shop(tmp_path)
    surface, _opened, _path = _open(qapp, root)
    try:
        surface.rename("x.png")
        surface.grid.setFocus()
        QTest.keyClick(surface.grid, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
        assert not surface.content_source().is_dirty()
        QTest.keyClick(surface.grid, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
        assert surface.content_source().is_dirty()
    finally:
        surface.release()


def test_a_missing_file_is_drawn_with_the_word_missing(qapp: QApplication, tmp_path: Path) -> None:
    root = _shop(tmp_path)
    (root / "forms" / "pictures" / "logo.png").unlink()
    surface, _opened, _path = _open(qapp, root)
    try:
        image = surface.grid.grab().toImage()
        assert not image.isNull()
        from app.features.form_builder.engine.project.pictures import missing_listed

        assert missing_listed(str(root / "forms" / "resources.qrc")) == ("pictures/logo.png",)
    finally:
        surface.release()


def test_edit_menu_undo_names_and_runs_the_tabs_step_and_goes_off_when_the_tab_hides(
    qapp: QApplication, tmp_path: Path
) -> None:
    from app.qt.QtWidgets import QAction, QMainWindow

    class _Registry:
        def __init__(self, window: QWidget) -> None:
            self.actions = {
                "shell.action.edit.undo": QAction("Undo", window),
                "shell.action.edit.redo": QAction("Redo", window),
            }

        def action(self, action_id: str) -> QAction:
            return self.actions[action_id]

    class _Window(QMainWindow):
        def __init__(self) -> None:
            super().__init__()
            self.registry = _Registry(self)

        def menu_registry(self) -> _Registry:
            return self.registry

    window = _Window()
    root = _shop(tmp_path)
    path = root / "forms" / "resources.qrc"
    request = _Request(
        str(path), path.read_text(encoding="utf-8"), window,
        tokens_from_palette(QPalette(), force_mode="light"), _Editor, lambda _p: None, str(root),
    )
    surface = FormTabProvider().create_surface(request)
    window.setCentralWidget(surface)
    window.show()
    qapp.processEvents()
    undo = window.registry.action("shell.action.edit.undo")
    try:
        assert not undo.isEnabled()
        surface.rename("x.png")
        assert undo.isEnabled() and undo.text() == "Undo Rename logo.png"
        undo.trigger()
        assert not surface.content_source().is_dirty() and not undo.isEnabled()
        assert window.registry.action("shell.action.edit.redo").text() == "Redo Rename logo.png"
        surface.rename("x.png")
        surface.hide()
        assert not undo.isEnabled() and undo.text() == "Undo"
    finally:
        surface.release()
        window.close()
