# pyright: reportAttributeAccessIssue=false
"""K19 Your own class (UX_SPEC 12.3, M5.4): keys only, in a real main window and a real preview child.

Shift+F10, "Use my own class…", the popover, the inspector header, the editor
importing nothing from ``widgets/`` (an import hook), the preview child building
the real class, the stand-in toast and FB602 for a class that raises, F2, "Back
to label", and Undo all back to the original bytes.

N/A here, with the owner: Ctrl+Shift+R and Esc on the preview window are
M5.5a's (the form tab's Preview key is a status sentence until then); the
script sends the same preview request the key will send
(``surface.request_preview``).
"""

from __future__ import annotations

import importlib.abc
import json
import sys
import time
from pathlib import Path
from typing import List, Optional

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.features.form_builder.engine.ipc.timing import DirectorConfig  # noqa: E402
from app.features.form_builder.integration import preview_notice  # noqa: E402
from app.features.form_builder.integration.custom_registry import registry_for  # noqa: E402
from app.features.form_builder.qtside.preview.launch import (  # noqa: E402
    current_runtime_python,
    python_preview_command,
    repo_root,
)
from app.features.form_builder.qtside.preview.pool import PreviewPool  # noqa: E402
from app.qt.QtTest import QTest  # noqa: E402
from app.qt.QtWidgets import QApplication, QLabel, QMenu, QPushButton, QWidget  # noqa: E402
from tests.form_builder.qtside.test_m3_keyboard_scripts import Kb, _close, _key, _NoMouse, _session  # noqa: E402

pytestmark = [pytest.mark.unit, pytest.mark.timeout(300)]

_SHOP = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Till</class>
 <widget class="QWidget" name="Till">
  <property name="geometry"><rect><x>0</x><y>0</y><width>480</width><height>320</height></rect></property>
  <layout class="QVBoxLayout" name="mainLayout">
   <item>
    <widget class="QLabel" name="totalLabel">
     <property name="text"><string>Total</string></property>
    </widget>
   </item>
   <item>
    <widget class="QLabel" name="noteLabel">
     <property name="text"><string>Note</string></property>
    </widget>
   </item>
   <item>
    <widget class="QPushButton" name="payButton">
     <property name="text"><string>Pay</string></property>
    </widget>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""

_TILL = '''import os

from PySide6.QtWidgets import QLabel

os.environ["CBCS_TILL_IMPORTED"] = "in the editor"


class TillDisplay(QLabel):
    def text(self):
        return "till:" + super().text()
'''

_BROKEN = '''from PySide6.QtWidgets import QLabel


class Broken(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        raise RuntimeError("the till is closed")
'''


class _ImportRecorder(importlib.abc.MetaPathFinder):
    """The import hook of K19: records any import of a project module and finds nothing."""

    def __init__(self) -> None:
        self.seen: List[str] = []

    def find_spec(self, fullname, path=None, target=None):  # noqa: ANN001, ANN201
        if fullname.split(".")[0] in ("widgets", "till_display", "broken"):
            self.seen.append(fullname)
        return None


def _project_files(tmp_path: Path) -> None:
    folder = tmp_path / "shop" / "widgets"
    folder.mkdir(parents=True)
    (folder / "__init__.py").write_text("", encoding="utf-8")
    (folder / "till_display.py").write_text(_TILL, encoding="utf-8")
    (folder / "broken.py").write_text(_BROKEN, encoding="utf-8")


def _pump_until(qapp: QApplication, predicate, seconds: float = 20.0) -> bool:  # noqa: ANN001
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        qapp.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return False


def _menu_pick(kb: Kb, sentence: str) -> None:
    """Down until the highlighted row starts with ``sentence``, then Enter."""
    menu = QApplication.activePopupWidget()
    assert isinstance(menu, QMenu), "a context menu is open"
    for _ in range(60):
        active = menu.activeAction()
        if active is not None and active.text().startswith(sentence):
            kb.press("Key_Return")
            return
        kb.press("Key_Down")
    raise AssertionError("no menu row %r in %s" % (sentence, [a.text() for a in menu.actions()]))


def _popover(kb: Kb) -> QWidget:
    found = None
    for widget in QApplication.topLevelWidgets():
        if widget.objectName() == "formBuilder.ownClassPopover" and widget.isVisible():
            found = widget
    assert found is not None, "the popover is open"
    # The offscreen platform has no window manager to activate a new tool window,
    # and Kb.pump hands the active window back to the main window. A real desktop activates it.
    found.activateWindow()
    kb.qapp.processEvents()
    focus = found.focusWidget()
    if focus is not None:
        focus.setFocus()
    kb.qapp.processEvents()
    return found


def _ptype(kb: Kb, popover: QWidget, text: str) -> None:
    """Keys to the popover's focus widget (the offscreen platform cannot make a tool window active)."""
    QTest.keyClicks(popover.focusWidget(), text)
    kb.pump()
    kb.log.append("popover type %r -> %s" % (text, popover.focusWidget().objectName()))


def _ppress(kb: Kb, popover: QWidget, key: str) -> None:
    if key == "Key_Tab":
        # A tool window that is not the active window gets no Tab handling from Qt's key path
        # on the offscreen platform; the popover's own tab chain is what Tab walks on a desktop.
        popover.focusNextChild()
    else:
        QTest.keyClick(popover.focusWidget(), _key(key))
    kb.pump()
    kb.log.append("popover %s -> %s" % (key, popover.focusWidget().objectName() if popover.focusWidget() else "(closed)"))


def _check_line(kb: Kb, popover: QWidget, expected: str) -> None:
    # The line follows typing after 150 ms.
    assert _pump_until(kb.qapp, lambda: popover.check_text == expected, 3.0), popover.check_text  # type: ignore[attr-defined]


def _select(kb: Kb, name: str) -> None:
    kb.press("Key_3", "Alt")
    for _ in range(12):
        if kb.current() == name:
            return
        kb.press("Key_Tab")
    raise AssertionError("Tab does not reach %s" % name)


def test_k19_your_own_class(tmp_path: Path, qapp: QApplication) -> None:
    _project_files(tmp_path)
    window, kb, guard = _session(tmp_path, qapp, _SHOP)
    recorder = _ImportRecorder()
    sys.meta_path.insert(0, recorder)
    pool = PreviewPool(
        command=python_preview_command(current_runtime_python(), repo_root()),
        config=DirectorConfig(handshake_timeout=20.0, request_timeout=15.0, shutdown_grace=0.4, ping_interval=30.0, prewarm=True),
        root=repo_root(),
    )
    PreviewPool._shared = pool
    preview_notice.forget_noted()
    try:
        original = kb.text()
        surface = kb.surface
        notices = surface.own_class_preview
        # --- a label, Shift+F10, "Use my own class…", Enter: focus on Class
        _select(kb, "totalLabel")
        kb.press("Key_F10", "Shift")
        _menu_pick(kb, "Use my own class")
        popover = _popover(kb)
        kb.check(popover.focusWidget().objectName() == "formBuilder.ownClassName", "the popover opens with focus on Class")
        _ptype(kb, popover, "TillDisplay")
        _ppress(kb, popover, "Key_Tab")
        kb.check(popover.focusWidget().objectName() == "formBuilder.ownClassModule", "Tab goes to the module")
        _ptype(kb, popover, "widgets.till_display")
        _check_line(kb, popover, "Found TillDisplay in widgets/till_display.py.")
        _ppress(kb, popover, "Key_Tab")
        kb.check(popover.focusWidget().objectName() == "formBuilder.ownClassUse", "Tab goes to [Use TillDisplay]")
        kb.check(popover._use.text() == "Use TillDisplay", "the button names the class")  # type: ignore[attr-defined]
        _ppress(kb, popover, "Key_Return")
        text = kb.text()
        kb.check('<widget class="TillDisplay" name="totalLabel">' in text, "the label now has the class")
        kb.check('<header location="local">widgets/till_display.h</header>' in text, "the header is the module as a path")
        kb.check(kb.session.log.undo_label() == "Use class TillDisplay for totalLabel", "one step with its name")
        header = kb.pane("formBuilder.inspectorHeader")
        kb.check(
            header._class_full == "TillDisplay \u00b7 your class, based on Label" and header._class_short == "TillDisplay (QLabel)",
            "the inspector header names the base: %r / %r" % (header._class_full, header._class_short),
        )
        kb.check(recorder.seen == [], "no module of widgets/ was imported in the editor: %s" % recorder.seen)
        kb.check(not any(name.split(".")[0] in ("widgets", "till_display") for name in sys.modules), "sys.modules has none")
        kb.check("CBCS_TILL_IMPORTED" not in __import__("os").environ, "the module did not run")
        kb.check(
            [entry.class_name for entry in registry_for(str((tmp_path / "shop").resolve())).entries()] == ["TillDisplay"],
            "the class is saved for the project's other forms",
        )
        # --- Preview: the child builds the real class; the security note shows
        surface.request_preview(str(kb.path))
        kb.check(_pump_until(qapp, lambda: notices.last_response is not None), "the preview child answered")
        response = notices.last_response
        kb.check(response.ok, "preview opened: %s" % response.detail)
        kb.check(response.result["texts"]["totalLabel"] == "till:Total", "the child built the real TillDisplay")
        kb.check("totalLabel" not in response.result["stubs"], "no stand-in for TillDisplay")
        bar = surface._notice
        kb.check(bar.isVisible(), "the security info bar shows")
        kb.check(
            bar._label.text()
            == "Preview runs code from this project: TillDisplay (widgets/till_display.py). "
            "Code Studio runs it only in the preview window, never in the editor.",
            bar._label.text(),
        )
        kb.check([b.text() for b in bar._buttons] == ["Got it"], "the bar has [Got it]")
        bar._buttons[0].click()
        kb.pump()
        kb.check(not bar.isVisible(), "Got it closes the bar")
        kb.check(recorder.seen == [], "still nothing imported in the editor after Preview")
        # --- a second label with a class that raises
        _select(kb, "noteLabel")
        kb.press("Key_F10", "Shift")
        _menu_pick(kb, "Use my own class")
        popover = _popover(kb)
        _ptype(kb, popover, "Broken")
        _ppress(kb, popover, "Key_Tab")
        _ptype(kb, popover, "widgets.broken")
        _check_line(kb, popover, "Found Broken in widgets/broken.py.")
        _ppress(kb, popover, "Key_Tab")
        _ppress(kb, popover, "Key_Return")
        kb.check('<widget class="Broken" name="noteLabel">' in kb.text(), "noteLabel uses Broken")
        surface.request_preview(str(kb.path))
        kb.check(_pump_until(qapp, lambda: notices.last_response is not None and "noteLabel" in notices.last_response.result.get("stubs", [])), "the stand-in shows in the answer")
        kb.check(notices.last_response.ok, "the preview opens although Broken raises")
        kb.check(notices.last_response.result["texts"]["totalLabel"] == "till:Total", "TillDisplay is still the real class")
        rows = [d for d in kb.session.diagnostics.all() if d.code == "FB602"]
        kb.check(len(rows) == 1, "one FB602 row: %s" % [d.message for d in kb.session.diagnostics.all()])
        kb.check(
            rows[0].message == "Preview used a stand-in for Broken: RuntimeError in widgets/broken.py line 7.",
            rows[0].message,
        )
        toast = surface._command_toast
        kb.check(toast.isVisible() and "Preview used a plain label for Broken." in toast._text.text(), "the stand-in toast shows")
        kb.check(toast._action.text() == "Show problem", "the toast offers Show problem")
        kb.check(not kb.surface._notice.isVisible(), "the security note is not shown twice in a session")
        kb.check(recorder.seen == [], "the editor still imported nothing")
        # --- F2 renames while the class is broken
        _select(kb, "noteLabel")
        kb.press("Key_F2")
        kb.press("Key_A", "Control")
        kb.type("receiptLabel")
        kb.press("Key_Return")
        kb.check('name="receiptLabel"' in kb.text() and 'name="noteLabel"' not in kb.text(), "the rename works")
        # --- Back to label
        kb.press("Key_F10", "Shift")
        _menu_pick(kb, "Back to label")
        text = kb.text()
        kb.check("<class>Broken</class>" not in text, "the Broken declaration is gone")
        kb.check("<class>TillDisplay</class>" in text, "the TillDisplay declaration stays")
        kb.check('<widget class="QLabel" name="receiptLabel">' in text, "the label is a label again")
        # --- Undo all: the original bytes
        for _ in range(20):
            if not kb.session.log.can_undo():
                break
            kb.press("Key_Z", "Control")
        kb.check(kb.text() == original, "undo all gives the original bytes")
        kb.done(guard)
    finally:
        sys.meta_path.remove(recorder)
        PreviewPool.reset_shared()
        _close(window, qapp, guard)
