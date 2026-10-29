# pyright: reportAttributeAccessIssue=false, reportOptionalMemberAccess=false, reportArgumentType=false
"""K22 Templates (UX_SPEC 12.3, M5.5c): save a template, use it from New form, delete it. Keys only after the menu items.

The window is K16's (a main window with menubar, centralwidget and statusbar) with K17's logo label. A filter
fails the run on any spontaneous mouse event. Differences from the script text, all forced by the form or the
platform: the two File and Form menu items run with ``QAction.trigger`` / ``window._open_new_form`` because the
offscreen platform draws no menu bar to press keys into; "Tab to the card" is as many Tabs as the folder box
and the Your templates group need; "Delete template…" is Down three times in the menu; and "Enter on [Delete
template]" is Tab to that button, then Enter, because Cancel is the default button of the confirm.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable, List

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.features.form_builder.engine.ids import IdAllocator  # noqa: E402
from app.features.form_builder.engine.project.pictures import picture_uses  # noqa: E402
from app.features.form_builder.engine.project.qrc_write import parse_qrc  # noqa: E402
from app.features.form_builder.engine.ui4.reader import read_ui  # noqa: E402
from app.features.form_builder.integration import template_store  # noqa: E402
from app.qt.QtCore import QTimer  # noqa: E402
from app.qt.QtWidgets import QApplication, QMessageBox, QMenu, QWidget  # noqa: E402
from tests.form_builder.inspector.test_m43c_pictures import _png_bytes  # noqa: E402
from tests.form_builder.qtside.test_m3_keyboard_scripts import Kb, _close, _session  # noqa: E402

pytestmark = [pytest.mark.unit, pytest.mark.timeout(300)]

_SHOP = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>ShopWindow</class>
 <widget class="QMainWindow" name="ShopWindow">
  <property name="geometry"><rect><x>0</x><y>0</y><width>480</width><height>320</height></rect></property>
  <property name="windowTitle"><string>Shop window</string></property>
  <widget class="QMenuBar" name="menubar"/>
  <widget class="QWidget" name="centralwidget">
   <layout class="QVBoxLayout" name="verticalLayout">
    <item>
     <widget class="QLabel" name="logoLabel">
      <property name="pixmap"><pixmap resource="resources.qrc">:/pictures/logo.png</pixmap></property>
     </widget>
    </item>
   </layout>
  </widget>
  <widget class="QStatusBar" name="statusbar"/>
 </widget>
 <resources><include location="resources.qrc"/></resources>
 <connections/>
</ui>
"""

_QRC = '<!DOCTYPE RCC>\n<RCC version="1.0">\n  <qresource prefix="/">\n    <file>pictures/logo.png</file>\n  </qresource>\n</RCC>\n'


def _tab_until(kb: Kb, done: Callable[[], bool], what: str, limit: int = 12) -> None:
    for _ in range(limit):
        if done():
            return
        kb.press("Key_Tab")
    kb.check(done(), what)


def _drive_confirm(kb: Kb, button: str, log: List[str]) -> None:
    """Keys into the modal confirm: Tab to ``button``, Enter. Runs from a timer inside the modal loop."""

    def step() -> None:
        box = QApplication.activeModalWidget()
        if not isinstance(box, QMessageBox):
            QTimer.singleShot(20, step)
            return
        log.append(box.text())
        log.append("default=" + box.defaultButton().text())
        for _ in range(4):
            focus = QApplication.focusWidget()
            if focus is not None and getattr(focus, "text", lambda: "")() == button:
                break
            kb.press("Key_Tab")
        log.append("focus=" + getattr(QApplication.focusWidget(), "text", lambda: "?")())
        kb.press("Key_Return")

    QTimer.singleShot(20, step)


def _form_action(window: QWidget, text: str) -> object:
    menu = window.findChild(QMenu, "formBuilder.menu")
    assert menu is not None
    for action in menu.actions():
        if action.text().split("\t")[0] == text:
            return action
    raise AssertionError("no Form menu item %r" % text)


@pytest.mark.parity("R3-184")
def test_k22_templates(tmp_path: Path, qapp: QApplication) -> None:
    root = tmp_path / "shop"
    (root / "forms" / "pictures").mkdir(parents=True)
    (root / "forms" / "pictures" / "logo.png").write_bytes(_png_bytes())
    (root / "forms" / "resources.qrc").write_text(_QRC, encoding="utf-8")
    state = tmp_path / "state"
    template_store.use_state_root(str(state.resolve()))
    window, kb, guard = _session(tmp_path, qapp, _SHOP)
    try:
        # --- Form > Save as template…: Shop window, Tab, Till and receipts, Enter ---------------
        _form_action(window, "Save as template…").trigger()
        kb.pump()
        kb.check(kb.focus_name() == "formBuilder.saveTemplate.name", "the popover opens with Name focused")
        kb.type("Shop window")
        kb.press("Key_Tab")
        kb.check(kb.focus_name() == "formBuilder.saveTemplate.description", "Tab reaches Description")
        kb.type("Till and receipts")
        kb.press("Key_Return")
        kb.check(QApplication.activePopupWidget() is None, "Enter saves and closes the popover")
        folder = state / "form_templates" / "shop_window"
        kb.check(
            sorted(p.name for p in folder.iterdir()) == ["form.ui", "pictures", "resources.qrc", "template.json", "thumbnail.png"],
            "the folder holds form.ui, template.json, thumbnail.png and pictures",
        )
        kb.check((folder / "pictures" / "logo.png").read_bytes() == _png_bytes(), "pictures/logo.png is the logo")
        meta = json.loads((folder / "template.json").read_text(encoding="utf-8"))
        kb.check(meta["name"] == "Shop window" and meta["description"] == "Till and receipts", "name and description kept")
        kb.check((folder / "thumbnail.png").stat().st_size > 0, "the thumbnail has a picture")

        # --- File > New Form…: Your templates first; back_office; Tab to the card; Enter -------------
        window._open_new_form()
        kb.pump()
        surface = window._tab_content_registry.surface_for_path(
            str(root / "cbcs" / "new-form.cbcs-tab")
        )
        panel = surface.widget()
        kb.check(panel.user_template_keys() == ("template:user:shop_window",), "Your templates has the card")
        groups = [w for w in panel.findChildren(type(panel.findChild(QWidget, "formBuilder.newForm.hero"))) if w.objectName().startswith("formBuilder.newForm.group.") and w.isVisible()]
        kb.check(groups[0].text() == "Your templates", "Your templates is the first group")
        kb.check(kb.focus_name() == "formBuilder.newForm.name", "the name row has focus")
        kb.type("back_office")
        card = panel.card("template:user:shop_window")
        _tab_until(kb, lambda: QApplication.focusWidget() is card, "Tab reaches the Shop window card")
        kb.press("Key_Return")
        kb.pump(12)
        made = root / "forms" / "back_office.ui"
        kb.check(made.is_file(), "forms/back_office.ui exists")
        document = read_ui(made.read_text(encoding="utf-8"), allocator=IdAllocator()).document
        kb.check(document.root.object_name == "BackOffice" and document.form_class_name() == "BackOffice", "the root is renamed")
        uses = [use.path for use in picture_uses(document)]
        qrc = parse_qrc((root / "forms" / "resources.qrc").read_text(encoding="utf-8"))
        listed = [entry.path for group in qrc.groups for entry in group.entries]
        kb.check(uses == [":/pictures/logo.png"] and listed == ["pictures/logo.png"], "the picture resolves through forms/resources.qrc")
        kb.check((root / "forms" / "pictures" / "logo.png").read_bytes() == _png_bytes(), "the picture file is in place")
        opened = window._tab_content_registry.surface_for_path(str(made))
        kb.check(opened is not None and hasattr(opened, "workbench"), "the Workbench is open on the new form")
        kb.check(
            tuple(opened.session.selection.state.ids) == (opened.session.document.root.id,),
            "the root is selected (UX-TMPL-003)",
        )
        before = made.read_bytes()
        other = state / "form_templates" / "unrelated"
        other.mkdir()
        (other / "keep.txt").write_text("x", encoding="utf-8")

        # --- File > New Form…, Tab to the card, Shift+F10, Delete template…, Enter on [Delete template] ---
        window._open_new_form()
        kb.pump()
        surface = window._tab_content_registry.surface_for_path(str(root / "cbcs" / "new-form.cbcs-tab"))
        panel = surface.widget()
        card = panel.card("template:user:shop_window")
        _tab_until(kb, lambda: QApplication.focusWidget() is card, "Tab reaches the card again")
        kb.press("Key_F10", "Shift")
        menu = QApplication.activePopupWidget()
        kb.check(isinstance(menu, QMenu), "Shift+F10 opens the card menu")
        for _ in range(3):
            kb.press("Key_Down")
        kb.check(menu.activeAction().text() == "Delete template…", "Down x3 reaches Delete template…")
        said: List[str] = []
        _drive_confirm(kb, "Delete template", said)
        kb.press("Key_Return")
        kb.pump(12)
        kb.check(said[0] == "Delete the template “Shop window”? Forms made from it don't change.", "the confirm says what it deletes")
        kb.check(said[1] == "default=Cancel" and said[2] == "focus=Delete template", "Cancel is the default; Tab reached [Delete template]")
        kb.check(not folder.exists(), "the template folder is gone")
        kb.check(made.read_bytes() == before, "back_office.ui is unchanged")
        kb.check((root / "forms" / "pictures" / "logo.png").is_file(), "the picture the form uses is still there")
        kb.check((other / "keep.txt").is_file(), "only that template's folder went")
        kb.done(guard)
    finally:
        template_store.use_state_root(None)
        _close(window, qapp, guard)
