"""External reload. Clean Yes/No, stale Save Changes, dirty Keep My Version."""

from __future__ import annotations

import json

from scenarios.common import open_file, open_project, write_tree
from scenarios.ctx import Ctx

ROOT = "/home/default/verify-reload"
PATH = ROOT + "/report.py"


def run(ctx: Ctx) -> None:
    ctx.launch(name="verify-reload")
    write_tree(ctx, ROOT, {"report.py": "value = 'original'\n"}, "verify-reload", "report.py")
    open_project(ctx, ROOT)
    open_file(ctx, PATH)
    ctx.eval("open(%s, 'w', encoding='utf-8').write(%s)\nprint('wrote')\n" % (json.dumps(PATH), json.dumps("value = 'from-disk'\n")), wait=15)
    _arm_check(ctx, PATH)
    dialog = ctx.wait_json(_BUTTONS, lambda row: "Yes" in row.get("buttons", []), timeout=15)
    ctx.shot("reload-01-clean-prompt", kind="window")
    buttons = dialog.get("buttons") or []
    default = dialog.get("default") or ""
    ctx.check("clean-default-yes", default == "Yes" or (buttons and buttons[0] == "&Yes"), "default Yes", json.dumps(dialog)[:300])
    ctx.adapter.click("text:No") if False else ctx.eval(_CLICK % json.dumps("No"), wait=15)
    body = ctx.eval(_BUFFER, wait=15)
    ctx.shot("reload-02-kept-stale", selector="#shell.mainWindow", kind="crop")
    ctx.check("kept-buffer", "original" in body, "No leaves the buffer", body.strip()[:200])
    status = ctx.eval(_STATUS, wait=15)
    ctx.check("changed-on-disk", "changed on disk" in status.lower(), "saved | changed on disk", status.strip()[:300])
    from scenarios.common import arm
    arm(ctx, "shell.action.file.save")
    stale = ctx.wait_json(_BUTTONS, lambda row: "Save My Version" in row.get("buttons", []), timeout=15)
    ctx.shot("reload-03-stale-save", kind="window")
    ctx.check(
        "stale-save",
        "Save Changes" in (stale.get("title") or "") and stale.get("default") == "Save My Version",
        "Save Changes / Save My Version",
        json.dumps(stale)[:400],
    )
    ctx.eval(_CLICK % json.dumps("Cancel"), wait=15)
    ctx.eval(_DIRTY, wait=15)
    ctx.eval("open(%s, 'w', encoding='utf-8').write(%s)\nprint('wrote')\n" % (json.dumps(PATH), json.dumps("value = 'again'\n")), wait=15)
    _arm_check(ctx, PATH)
    dirty = ctx.wait_json(_BUTTONS, lambda row: "Keep My Version" in row.get("buttons", []), timeout=15)
    ctx.shot("reload-04-dirty-keep", kind="window")
    ctx.check(
        "dirty-keep",
        "File Changed on Disk" in (dirty.get("title") or "") and dirty.get("default") == "Keep My Version",
        "File Changed on Disk / Keep My Version",
        json.dumps(dirty)[:400],
    )


def _arm_check(ctx: Ctx, path: str) -> None:
    ctx.eval(
        "from PySide2.QtCore import QTimer\n"
        "path = %s\n"
        "def go():\n"
        "    win = next(w for w in app.topLevelWidgets() if type(w).__name__=='MainWindow')\n"
        "    win._external_file_change_workflow.check_and_handle(path)\n"
        "QTimer.singleShot(0, go)\n"
        "print('armed')\n" % json.dumps(path),
        wait=15,
    )


_BUTTONS = r"""
import json
try:
    from PySide2.QtWidgets import QPushButton
except ImportError:
    from PySide6.QtWidgets import QPushButton
title = ""
buttons = []
default = ""
for widget in app.topLevelWidgets():
    if not widget.isVisible():
        continue
    if not (widget.inherits("QDialog") or widget.inherits("QMessageBox")):
        continue
    title = widget.windowTitle()
    for button in widget.findChildren(QPushButton):
        buttons.append(button.text().replace("&", ""))
        if button.isDefault():
            default = button.text().replace("&", "")
print("JSON:" + json.dumps({"title": title, "buttons": buttons, "default": default}))
"""

_CLICK = r"""
try:
    from PySide2.QtWidgets import QPushButton
except ImportError:
    from PySide6.QtWidgets import QPushButton
wanted = %s
for widget in app.topLevelWidgets():
    if not widget.isVisible():
        continue
    for button in widget.findChildren(QPushButton):
        if button.text().replace("&", "") == wanted:
            button.click()
            print("clicked", wanted)
            break
"""

_BUFFER = r"""
win = next(w for w in app.topLevelWidgets() if type(w).__name__=="MainWindow")
ed = win._editor_tab_workflow.active_editor_widget()
print(ed.toPlainText())
"""

_STATUS = r"""
win = next(w for w in app.topLevelWidgets() if type(w).__name__=="MainWindow")
print(win.statusBar().currentMessage())
for w in app.allWidgets():
    if w.objectName()=="shell.editorStatusLabel":
        print(w.text())
"""

_DIRTY = r"""
win = next(w for w in app.topLevelWidgets() if type(w).__name__=="MainWindow")
ed = win._editor_tab_workflow.active_editor_widget()
ed.insertPlainText(" dirty")
print("dirty", ed.document().isModified())
"""
