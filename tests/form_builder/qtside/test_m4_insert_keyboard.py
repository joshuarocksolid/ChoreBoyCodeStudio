# pyright: reportAttributeAccessIssue=false
"""K9 Insert by words (UX_SPEC 12.3), with real key events at an offscreen main window.

Open a form-layout form, select its last field, then drive Insert and quick insert
from the keyboard. After each insert: one undo step named "Insert ...", and focus
where UX-CAT-010 and UX-CAT-011 put it. Undo back to the original bytes.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.features.form_builder.integration.workbench import FormWorkbench
from app.features.form_builder.qtside.insert.delegate import ROW_ROLE
from app.features.form_builder.install import form_builder_enabled
from app.qt.QtCore import Qt
from app.qt.QtTest import QTest
from app.qt.QtWidgets import QApplication, QLineEdit
from app.shell.main_window import MainWindow
from app.core.models import LoadedProject, ProjectMetadata
from testing.main_window_shutdown import shutdown_main_window_for_test

_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <layout class="QFormLayout" name="formLayout">
     <item row="0" column="0">
      <widget class="QLabel" name="nameLabel">
       <property name="text"><string>Name</string></property>
       <property name="buddy"><cstring>nameEdit</cstring></property>
      </widget>
     </item>
     <item row="0" column="1">
      <widget class="QLineEdit" name="nameEdit"/>
     </item>
     <item row="1" column="0">
      <widget class="QLabel" name="notesLabel">
       <property name="text"><string>Notes</string></property>
       <property name="buddy"><cstring>notesEdit</cstring></property>
      </widget>
     </item>
     <item row="1" column="1">
      <widget class="QLineEdit" name="notesEdit"/>
     </item>
    </layout>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


def _require() -> None:
    if not form_builder_enabled():
        pytest.skip("form builder is registered on PySide6")


def _key(name: str) -> object:
    return getattr(getattr(Qt, "Key", Qt), name)


def _mods(name: str) -> object:
    enum = getattr(Qt, "KeyboardModifier", Qt)
    return getattr(enum, "NoModifier") if name == "" else getattr(enum, name + "Modifier")


def _project(window: MainWindow, root: Path) -> None:
    (root / "forms").mkdir(parents=True, exist_ok=True)
    (root / "cbcs").mkdir(exist_ok=True)
    (root / "main.py").write_text("print('shop')\n", encoding="utf-8")
    manifest = root / "cbcs" / "project.json"
    manifest.write_text(
        json.dumps({"schema_version": 2, "name": "Shop", "default_entry": "main.py"}) + "\n",
        encoding="utf-8",
    )
    window._loaded_project = LoadedProject(  # noqa: SLF001
        project_root=str(root.resolve()),
        manifest_path=str(manifest.resolve()),
        metadata=ProjectMetadata(schema_version=2, name="Shop", default_entry="main.py"),
    )


class _Keys:
    def __init__(self, window: MainWindow, qapp: QApplication) -> None:
        self.window = window
        self.qapp = qapp

    def press(self, key: str, modifier: str = "") -> None:
        focus = QApplication.focusWidget()
        target = focus if focus is not None else self.window
        QTest.keyClick(target, _key(key), _mods(modifier))
        self.pump()

    def type(self, text: str) -> None:
        focus = QApplication.focusWidget()
        QTest.keyClicks(focus if focus is not None else self.window, text)
        self.pump()

    def pump(self) -> None:
        for _ in range(6):
            self.qapp.processEvents()


def _focus_name() -> str:
    focus = QApplication.focusWidget()
    return "" if focus is None else focus.objectName() or type(focus).__name__


def test_k9_insert_by_words(tmp_path: Path, qapp: QApplication) -> None:
    _require()
    root = tmp_path / "shop"
    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    try:
        _project(window, root)
        path = root / "forms" / "form.ui"
        path.write_text(_FORM, encoding="utf-8")
        assert window._editor_tab_factory.open_file_in_editor(str(path))  # noqa: SLF001
        stack = window._center_stack  # noqa: SLF001
        assert stack is not None
        stack.setCurrentIndex(1)
        window.resize(1400, 900)
        window.show()
        window.activateWindow()
        for _ in range(8):
            qapp.processEvents()
        surface = window._tab_content_registry.surface_for_path(str(path))  # noqa: SLF001
        assert surface is not None
        session = surface.session  # type: ignore[attr-defined]
        workbench = surface._workbench  # type: ignore[attr-defined]
        assert isinstance(workbench, FormWorkbench)
        insert = workbench.insert
        keys = _Keys(window, qapp)
        original = session.text()
        surface.focus_primary()  # type: ignore[attr-defined]
        surface.select_object("notesEdit")  # type: ignore[attr-defined]
        keys.pump()

        # Alt+2 focuses Insert; typing goes to its search field.
        keys.press("Key_2", "Alt")
        assert insert.isAncestorOf(QApplication.focusWidget()) or QApplication.focusWidget() is insert.body
        keys.type("dropdown")
        assert insert.filter.text() == "dropdown"
        assert QApplication.focusWidget() is insert.filter
        assert insert.body.item(0).data(int(Qt.ItemDataRole.UserRole)) == "QComboBox"
        keys.press("Key_Return")
        assert session.text().count('class="QComboBox"') == 1
        assert session.log.undo_label() == "Insert combo box"
        editor = QApplication.focusWidget()
        assert isinstance(editor, QLineEdit), "the form-row label editor opens (UX-FORML-002)"
        keys.type("Size")
        keys.press("Key_Return")
        assert "<string>Size</string>" in session.text()
        assert QApplication.focusWidget() is insert.body, "focus returns to the Insert tile (UX-CAT-011)"

        # Esc in Insert clears the filter and keeps focus there; Recently used now starts with Combo box.
        keys.press("Key_Escape")
        assert insert.filter.text() == ""
        assert insert.isAncestorOf(QApplication.focusWidget())
        recent_section = insert.body.item(0).data(int(ROW_ROLE))
        assert recent_section.kind == "section" and recent_section.title == "Recently used"
        assert insert.body.item(1).data(int(Qt.ItemDataRole.UserRole)) == "QComboBox"

        # Ctrl+Down twice reaches the next category; Enter inserts its first entry after the combo box.
        keys.press("Key_Down", "Control")
        keys.press("Key_Down", "Control")
        keys.press("Key_Return")
        assert session.log.undo_label() == "Insert line edit"
        assert session.text().count('class="QLineEdit"') >= 3
        keys.press("Key_Escape")  # the label editor takes Esc (cancels the label)
        keys.pump()
        assert QApplication.focusWidget() is insert.body

        # Esc with the filter empty hands focus back to the canvas.
        keys.press("Key_Escape")
        assert QApplication.focusWidget() is workbench.canvas or workbench.canvas.isAncestorOf(QApplication.focusWidget())

        # "/" opens the quick list; typing filters it; Enter inserts the first result and closes it.
        keys.press("Key_Slash")
        search = workbench.outline._insert_filter  # noqa: SLF001
        assert QApplication.focusWidget() is search
        keys.type("tabs")
        keys.press("Key_Return")
        assert session.log.undo_label() == "Insert tab widget"
        assert session.text().count('class="QTabWidget"') == 1
        assert workbench.canvas.isAncestorOf(QApplication.focusWidget()) or QApplication.focusWidget() is workbench.canvas

        # Undo back to the original bytes.
        undone = 0
        while session.log.can_undo() and session.text() != original and undone < 8:
            session.log.undo()
            undone += 1
        assert session.text() == original
        assert 3 <= undone <= 6
    finally:
        shutdown_main_window_for_test(window, qapp)
