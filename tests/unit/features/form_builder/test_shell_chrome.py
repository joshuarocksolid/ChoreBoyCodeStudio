"""What a form tab shows in the shell: the Form menu, the routed Edit rows, keys and the selection sentence."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.features.form_builder.engine.query.selection import SelectionState  # noqa: E402
from app.features.form_builder.engine.ui4.writer import write_ui  # noqa: E402
from app.features.form_builder.install import PROVIDER_ID  # noqa: E402
from app.features.form_builder.integration.chrome_text import selection_sentence  # noqa: E402
from app.features.form_builder.integration.content_source import open_document_log  # noqa: E402
from app.features.form_builder.integration.provider import FormTabProvider  # noqa: E402
from app.features.form_builder.integration.surface import FormSurface  # noqa: E402
from app.qt.QtCore import Qt  # noqa: E402
from app.qt.QtGui import QTextCursor  # noqa: E402
from app.qt.QtTest import QTest  # noqa: E402
from app.qt.QtWidgets import (  # noqa: E402
    QAction,
    QApplication,
    QFrame,
    QMainWindow,
    QMenu,
    QPlainTextEdit,
    QToolButton,
    QTreeWidget,
    QWidget,
)
from app.shell.active_surface_chrome import ActiveSurfaceChrome  # noqa: E402
from app.shell.menus import MenuCallbacks, build_menu_stubs  # noqa: E402
from app.shell.tab_content_providers import TabContentProviderRegistry, TabSurfaceRequest  # noqa: E402
from app.shell.theme_tokens import tokens_from_palette  # noqa: E402

pytestmark = pytest.mark.unit

_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Invoice</class>
 <widget class="QWidget" name="Invoice">
  <property name="geometry">
   <rect>
    <x>0</x>
    <y>0</y>
    <width>400</width>
    <height>300</height>
   </rect>
  </property>
  <layout class="QFormLayout" name="formLayout">
   <item row="0" column="0">
    <widget class="QLabel" name="nameLabel">
     <property name="text">
      <string>Name</string>
     </property>
    </widget>
   </item>
   <item row="0" column="1">
    <widget class="QLineEdit" name="name"/>
   </item>
   <item row="1" column="0">
    <widget class="QLabel" name="emailLabel">
     <property name="text">
      <string>Email</string>
     </property>
    </widget>
   </item>
   <item row="1" column="1">
    <widget class="QLineEdit" name="email"/>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


class _Editor(QPlainTextEdit):
    def apply_theme(self, _tokens: object) -> None:
        return None

    def go_to_line(self, line_number: int) -> None:
        cursor = self.textCursor()
        move = getattr(QTextCursor, "MoveOperation", QTextCursor)
        mode = getattr(QTextCursor, "MoveMode", QTextCursor)
        cursor.movePosition(getattr(move, "Start"))
        cursor.movePosition(getattr(move, "Down"), getattr(mode, "MoveAnchor"), max(0, int(line_number) - 1))
        self.setTextCursor(cursor)


def _request(parent: QWidget, text: str, path: str) -> TabSurfaceRequest:
    app = QApplication.instance()
    assert app is not None

    def create_source_editor() -> _Editor:
        editor = _Editor(parent)
        editor.setObjectName("shell.editorTabs.textEditor")
        return editor

    return TabSurfaceRequest(
        file_path=path,
        initial_text=text,
        parent=parent,
        theme=tokens_from_palette(app.palette(), force_mode="light"),
        create_source_editor=create_source_editor,  # type: ignore[arg-type]
        open_linked_file=lambda _linked: None,
        project_root=None,
        publish_problems=lambda _path, _rows: None,
        show_problems=lambda: None,
        save_file=lambda _path: True,
        unsaved_text=lambda _path: None,
    )


class _Shell:
    def __init__(self, *, form_provider: bool = True) -> None:
        self.window = QMainWindow()
        self.registry = TabContentProviderRegistry()
        if form_provider:
            self.registry.register(FormTabProvider())
        self.chrome = ActiveSurfaceChrome(self.registry)
        route = self.chrome.route
        self.menus = build_menu_stubs(
            self.window.menuBar(),
            MenuCallbacks(
                on_undo=route("shell.action.edit.undo"),
                on_redo=route("shell.action.edit.redo"),
                on_cut=route("shell.action.edit.cut"),
            ),
        )
        self.chrome.bind(
            self.menus,
            self.window.menuBar(),
            before_menu_id="shell.menu.view",
            on_sentence_changed=lambda: None,
        )
        self.surfaces: list[FormSurface] = []

    def open(self, path: Path) -> FormSurface:
        canonical = write_ui(open_document_log(_FORM).document).text
        path.write_text(canonical, encoding="utf-8")
        surface = FormTabProvider().create_surface(_request(self.window, canonical, str(path)))
        self.registry.bind(str(path), surface, PROVIDER_ID)
        self.chrome.follow(str(path))
        self.surfaces.append(surface)
        return surface

    def action(self, action_id: str) -> QAction:
        action = self.menus.action(action_id)
        assert action is not None, action_id
        return action

    def form_menu(self) -> QMenu:
        menu = self.menus.menu("shell.menu.form")
        assert menu is not None
        return menu

    def row(self, command_id: str) -> Optional[QAction]:
        return self.form_menu().findChild(QAction, command_id)

    def close(self) -> None:
        for surface in self.surfaces:
            surface.release()
        self.window.close()


def _edit_xml(surface: FormSurface, old: str, new: str) -> None:
    toggle = surface.findChild(QToolButton, "formBuilder.viewXml")
    assert toggle is not None
    toggle.setChecked(True)
    editor = surface.source_editor()
    assert editor is not None
    editor.setPlainText(editor.toPlainText().replace(old, new))
    toggle.setChecked(False)


def _menu_bar_titles(shell: _Shell) -> list[str]:
    return [action.text().replace("&", "") for action in shell.window.menuBar().actions() if action.isVisible()]


def test_form_menu_sits_between_run_and_view_only_while_a_form_tab_is_active(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    del qapp
    shell = _Shell()
    assert "Form" not in _menu_bar_titles(shell)

    shell.open(tmp_path / "invoice.ui")
    titles = _menu_bar_titles(shell)
    form = titles.index("Form")
    assert titles[form - 1 : form + 2] == ["Run", "Form", "View"]

    shell.chrome.follow(str(tmp_path / "report.py"))
    assert "Form" not in _menu_bar_titles(shell)
    shell.close()


def test_without_the_form_provider_there_is_no_form_menu(qapp) -> None:  # type: ignore[no-untyped-def]
    del qapp
    shell = _Shell(form_provider=False)
    assert shell.menus.menu("shell.menu.form") is None
    assert "Form" not in [action.text().replace("&", "") for action in shell.window.menuBar().actions()]
    shell.close()


def test_rows_that_are_not_ready_are_disabled_with_a_plain_reason(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    del qapp
    shell = _Shell()
    shell.open(tmp_path / "invoice.ui")
    insert = shell.row("form.insertWidget")
    grid = shell.row("form.layout.grid")
    view_xml = shell.row("form.viewXml")
    cut = shell.action("shell.action.edit.cut")
    assert insert is not None and grid is not None and view_xml is not None

    assert (insert.isEnabled(), insert.toolTip()) == (False, "Insert widget is not available yet.")
    assert (grid.isEnabled(), grid.toolTip()) == (False, "Grid is not available yet.")
    assert (cut.isVisible(), cut.isEnabled(), cut.toolTip()) == (True, False, "Cut is not available yet.")
    assert view_xml.isEnabled() is True
    rows = [row for row in shell.form_menu().findChildren(QAction) if row.objectName().startswith("form.")]
    assert rows and not [row.objectName() for row in rows if re.search(r"\bM\d", row.toolTip())]
    assert shell.row("form.overlay.connections") is None
    assert shell.row("form.preview.twoWidths") is None
    shell.close()


def test_shell_undo_names_the_form_command_and_undoes_it(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    del qapp
    shell = _Shell()
    surface = shell.open(tmp_path / "invoice.ui")
    _edit_xml(surface, ">Name<", ">Full name<")
    undo = shell.action("shell.action.edit.undo")

    assert (undo.text(), undo.isEnabled()) == ("Undo XML edits", True)
    undo.trigger()
    assert ">Name<" in surface.content_source().current_text()
    assert ">Full name<" not in surface.content_source().current_text()
    shell.close()


def test_edit_rows_go_back_to_the_shell_when_no_form_tab_is_active(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    del qapp
    shell = _Shell()
    surface = shell.open(tmp_path / "invoice.ui")
    _edit_xml(surface, ">Name<", ">Full name<")

    shell.chrome.follow(None)
    undo = shell.action("shell.action.edit.undo")
    assert (undo.text(), undo.isEnabled()) == ("Undo", False)
    assert shell.action("shell.action.edit.cut").isVisible() is False
    undo.trigger()
    assert ">Full name<" in surface.content_source().current_text()
    shell.close()


def test_shell_undo_follows_the_active_form(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    del qapp
    shell = _Shell()
    first = shell.open(tmp_path / "one.ui")
    second = shell.open(tmp_path / "two.ui")
    _edit_xml(first, ">Name<", ">Aaa<")
    _edit_xml(second, ">Name<", ">Bbb<")

    shell.chrome.follow(str(tmp_path / "one.ui"))
    shell.action("shell.action.edit.undo").trigger()
    assert ">Aaa<" not in first.content_source().current_text()
    assert ">Bbb<" in second.content_source().current_text()
    shell.close()


def test_view_xml_row_switches_the_form_and_shows_its_mode(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    del qapp
    shell = _Shell()
    surface = shell.open(tmp_path / "invoice.ui")
    view_xml = shell.row("form.viewXml")
    assert view_xml is not None

    view_xml.trigger()
    assert (surface.content_source().mode, view_xml.isChecked()) == ("xml", True)
    view_xml.trigger()
    assert (surface.content_source().mode, view_xml.isChecked()) == ("visual", False)
    shell.close()


def test_ready_keys_run_their_commands(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    canonical = write_ui(open_document_log(_FORM).document).text
    path = tmp_path / "invoice.ui"
    path.write_text(canonical, encoding="utf-8")
    host = QWidget()
    surface = FormTabProvider().create_surface(_request(host, canonical, str(path)))
    host.show()
    surface.show()
    host.resize(700, 500)
    surface.resize(700, 500)
    qapp.processEvents()
    assert (surface.width(), surface.height()) == (700, 500)
    qapp.setActiveWindow(host)
    tree = surface.findChild(QTreeWidget, "formBuilder.structure")
    drawer = surface.findChild(QFrame, "formBuilder.drawer")
    assert tree is not None and drawer is not None
    assert drawer.isVisible() is False

    QTest.keyClick(surface, Qt.Key.Key_1, Qt.KeyboardModifier.AltModifier)
    qapp.processEvents()
    assert qapp.focusWidget() is tree
    assert drawer.isVisible() is True
    QTest.keyClick(tree, Qt.Key.Key_Escape)
    qapp.processEvents()
    assert drawer.isVisible() is False
    surface.release()
    host.close()


@pytest.mark.parametrize(
    ("names", "expected"),
    [
        (("email",), "email · Line edit · row 2 of the form layout"),
        (("nameLabel",), "nameLabel · Label · row 1 of the form layout"),
        ((), "Invoice · the form · 400 × 300"),
        (("name", "email"), "2 selected"),
    ],
)
def test_selection_sentence_names_the_widget_its_kind_and_its_place(names: tuple[str, ...], expected: str) -> None:
    document = open_document_log(_FORM).document
    ids = tuple(document.by_name(name)[0] for name in names)
    state = SelectionState(ids=ids, current=ids[-1] if ids else None)

    assert selection_sentence(document, state) == expected
