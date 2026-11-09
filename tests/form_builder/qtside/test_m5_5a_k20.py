# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportOptionalMemberAccess=false, reportOptionalCall=false, reportIndexIssue=false
"""K20 Preview options and code (UX_SPEC 12.3, M5.5a): keys only, in a real main window and a real preview child.

Form > Preview options > Screen > "Small screen", Ctrl+Shift+R (the window title ends
"· Small screen", size at most 1024 x 600), Form > Save image… and Enter on the default
name, Ctrl+K C (the code split), Alt+1 and Down (the code scrolls to the selected widget's
lines), Ctrl+K C (closed, focus on the canvas). The undo stack and the file bytes never change.

N/A with owner: the Esc that closes the preview window is a key press inside the preview
child process, which a test in this process cannot send. The script closes the window with the
host's ``close_view`` instead (the editor sees the same ``view_closed``); the child's Esc is
proved in ``test_m5_5a_child.py``.
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.features.form_builder.engine.ipc.protocol import CloseView  # noqa: E402
from app.features.form_builder.engine.ipc.timing import DirectorConfig  # noqa: E402
from app.features.form_builder.integration.memory import PreviewOptionsStore  # noqa: E402
from app.features.form_builder.qtside.preview.launch import (  # noqa: E402
    current_runtime_python,
    python_preview_command,
    repo_root,
)
from app.features.form_builder.qtside.preview.pool import PreviewPool  # noqa: E402
from app.qt.QtCore import QPoint  # noqa: E402
from app.qt.QtGui import QImage  # noqa: E402
from app.qt.QtWidgets import QApplication, QFileDialog, QLineEdit, QMenu  # noqa: E402
from tests.form_builder.qtside.test_m3_keyboard_scripts import Kb, _close, _session  # noqa: E402

pytestmark = [pytest.mark.unit, pytest.mark.timeout(300)]


def _long_form() -> str:
    rows = "\n".join(
        '   <item><widget class="QLabel" name="row%02dLabel"><property name="text"><string>Row %d</string></property></widget></item>'
        % (number, number)
        for number in range(1, 25)
    )
    return """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Customer</class>
 <widget class="QWidget" name="Customer">
  <property name="geometry"><rect><x>0</x><y>0</y><width>480</width><height>420</height></rect></property>
  <layout class="QVBoxLayout" name="mainLayout">
%s
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
""" % rows


def _pump_until(qapp: QApplication, predicate, seconds: float = 25.0) -> bool:  # noqa: ANN001
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        qapp.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return False


def _menu_path(kb: Kb, titles) -> None:  # noqa: ANN001
    """Open Form (Alt+O on Linux; Qt has no menu mnemonics on macOS, so the menu is popped up, as in K1),
    then keys: Down to each title, Right opens a submenu, Enter on the last."""
    form = kb.window.findChild(QMenu, "formBuilder.menu")
    assert form is not None
    form.popup(kb.window.mapToGlobal(QPoint(40, 40)))
    kb.pump()
    for position, title in enumerate(titles):
        menu = QApplication.activePopupWidget()
        assert isinstance(menu, QMenu), "a menu is open for %r" % title
        found = False
        for _ in range(80):
            active = menu.activeAction()
            if active is not None and active.text().split("\t")[0].startswith(title) and active.isVisible():
                found = True
                break
            kb.press("Key_Down")
        assert found, "no menu row %r in %s" % (title, [a.text() for a in menu.actions()])
        kb.press("Key_Right" if position < len(titles) - 1 else "Key_Return")


@pytest.mark.parity("R3-177", "R3-178", "R3-179", "R3-180", "R3-181")
@pytest.mark.pain("P-6", "P-11", "P-12", "P-23")
def test_k20_preview_options_and_code(tmp_path: Path, qapp: QApplication) -> None:
    window, kb, guard = _session(tmp_path, qapp, _long_form())
    # Setup, not a key: the canvas keeps 360 px beside the code only in a wide window (UX-PREV-004).
    window.resize(1900, 900)
    kb.pump()
    pool = PreviewPool(
        command=python_preview_command(current_runtime_python(), repo_root()),
        config=DirectorConfig(handshake_timeout=20.0, request_timeout=15.0, shutdown_grace=0.4, ping_interval=30.0, prewarm=True),
        root=repo_root(),
    )
    PreviewPool._shared = pool
    try:
        surface = kb.surface
        notices = surface.own_class_preview
        control = surface.preview_control
        original = kb.text()
        file_bytes = kb.path.read_bytes()
        steps = len(kb.session.log.entries())
        # --- Form > Preview options > Screen > Small screen
        _menu_path(kb, ("Preview options", "Screen", "Small screen"))
        kb.check(control.choices.screen == "Small screen", "the Small screen row was chosen: %s" % control.choices.screen)
        saved = PreviewOptionsStore(str(tmp_path / "state")).load()[0]
        kb.check(saved.screen == "Small screen", "the choice is kept per user, outside the form")
        # --- Ctrl+Shift+R: the window title and size
        kb.press("Key_R", "Control", "Shift")
        kb.check(_pump_until(qapp, lambda: notices.last_response is not None), "the preview child answered")
        response = notices.last_response
        kb.check(response.ok, "preview opened: %s" % response.detail)
        kb.check(response.result["title"] == "Preview · customer.ui · Small screen", response.result["title"])
        width, height = response.result["size"]
        kb.check(width <= 1024 and height <= 600, "the window fits the small screen: %s x %s" % (width, height))
        kb.check(control.is_open, "the editor knows the preview is open")
        # --- Esc closes the window (host close here; see the module docstring)
        closed = []
        pool.subscribe(notices.view_id, lambda message: closed.append(message))
        pool.request(CloseView(request_id=uuid.uuid4().hex, view_id=notices.view_id), lambda _r: None)
        kb.check(_pump_until(qapp, lambda: not control.is_open), "the preview window closed")
        # --- Form > Save image… and Enter on the default name
        _menu_path(kb, ("Save image",))
        dialog = next(
            (w for w in QApplication.topLevelWidgets() if w.objectName() == "formBuilder.saveImageDialog" and w.isVisible()),
            None,
        )
        kb.check(dialog is not None, "the save dialog is open")
        kb.check(isinstance(dialog, QFileDialog), "it is the shell file dialog")
        kb.check(dialog.directory().absolutePath() == str((tmp_path / "shop" / "forms").resolve()), "it opens in the form's folder: %s" % dialog.directory().absolutePath())
        dialog.activateWindow()
        qapp.processEvents()
        field = dialog.findChild(QLineEdit, "fileNameEdit")
        kb.check(field is not None and field.text() == "customer.png", "the default name is customer.png")
        field.setFocus()
        kb.press("Key_Return")
        target = tmp_path / "shop" / "forms" / "customer.png"
        kb.check(_pump_until(qapp, target.exists, 8.0), "customer.png exists")
        image = QImage(str(target))
        page = surface.page_widget()
        ratio = image.devicePixelRatio() or 1.0
        kb.check(
            (image.width(), image.height()) == (page.width(), page.height())
            or (round(image.width() / ratio), round(image.height() / ratio)) == (page.width(), page.height()),
            "the image has the page's size: %sx%s vs %sx%s" % (image.width(), image.height(), page.width(), page.height()),
        )
        toast = surface._command_toast
        kb.check(toast.isVisible() and "Saved customer.png." in toast._text.text(), "the saved toast shows")
        kb.check(toast._action.text() == "Show", "the toast offers Show")
        # --- Ctrl+K, C: the code split
        kb.press("Key_K", "Control")
        kb.press("Key_C")
        workbench = surface._workbench
        kb.check(workbench.beside_canvas_key() == "code", "the code split is open")
        view = workbench.code_view
        panel = view.panel
        kb.check(_pump_until(qapp, lambda: "class Ui_Customer" in panel.text()), "the generated module is shown")
        kb.check(panel.editor.isReadOnly(), "the code is read only")
        kb.check(panel._title.text() == "ui_customer.py · as it will be saved", panel._title.text())
        # --- Alt+1, Down: the code scrolls to the selected widget's lines
        kb.press("Key_1", "Alt")
        kb.press("Key_End")
        selected = kb.selected()
        kb.check(len(selected) == 1 and selected[0].startswith("row"), "a row widget is selected: %s" % (selected,))
        line = view._index.first_line(selected[0])
        kb.check(line is not None, "the generated code creates %s" % selected[0])
        kb.check(_pump_until(qapp, lambda: panel.first_visible_line() <= line <= panel.last_visible_line()), "the code scrolled to line %s (shows %s-%s)" % (line, panel.first_visible_line(), panel.last_visible_line()))
        kb.check(line in panel.marked_lines(), "the widget's lines are marked")
        kb.press("Key_Up")
        previous = kb.selected()[0]
        kb.check(previous != selected[0], "Up selects another widget")
        kb.check(view._index.first_line(previous) in panel.marked_lines(), "the marks follow the selection")
        # --- Ctrl+K, C: closed, focus on the canvas
        kb.press("Key_K", "Control")
        kb.press("Key_C")
        kb.check(workbench.beside_canvas_key() == "", "the split is closed")
        kb.check(kb.focus_in("formBuilder.canvas"), "focus is back on the canvas: %s" % kb.focus_name())
        # --- nothing changed
        kb.check(len(kb.session.log.entries()) == steps, "the undo stack did not change")
        kb.check(kb.text() == original, "the form did not change")
        kb.check(kb.path.read_bytes() == file_bytes, "the file bytes did not change")
        kb.done(guard)
    finally:
        PreviewPool.reset_shared()
        _close(window, qapp, guard)
