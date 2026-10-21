"""CB-7. Run opens FreeCAD. Log noise format, Keep, and Stop."""

from __future__ import annotations

import json

from scenarios.common import arm, open_file, open_project, write_tree
from scenarios.ctx import Ctx

ROOT = "/home/default/verify-cb7"
SCRIPT = (
    "import subprocess, time\n"
    "proc = subprocess.Popen(['/opt/freecad/AppRun'])\n"
    "print('launched FreeCAD pid', proc.pid)\n"
    "for i in range(3):\n"
    "    print('tick', i)\n"
    "    time.sleep(1)\n"
    "time.sleep(30)\n"
)


def run(ctx: Ctx) -> None:
    try:
        _session(ctx, "verify-cb7", keep=True)
        ctx.stop()
        _close_freecad(ctx)
        _session(ctx, "verify-cb7b", keep=False)
    finally:
        _close_freecad(ctx)


def _session(ctx: Ctx, name: str, keep: bool) -> None:
    ctx.launch(name=name)
    write_tree(ctx, ROOT, {"launch_freecad.py": SCRIPT}, "verify-cb7", "launch_freecad.py")
    open_project(ctx, ROOT)
    open_file(ctx, ROOT + "/launch_freecad.py")
    arm(ctx, "shell.action.run.run")
    ctx.wait_json(_LOG, lambda row: "launched FreeCAD" in row.get("text", ""), timeout=25)
    noise = ctx.eval_json(_NOISE, wait=20)
    ctx.shot("cb7-run-log", selector="#shell.bottom.runLog", kind="crop")
    ctx.metric("noise", noise)
    bad = [row for row in noise.get("rows") or [] if row.get("noise")]
    formatted = [row for row in bad if row.get("italic") and row.get("color") == "#5a6168" and row.get("tooltip")]
    ctx.check(
        "log-noise-format",
        bool(bad) and len(formatted) == len(bad),
        "noise lines italic #5a6168 with a tooltip",
        json.dumps(bad)[:500],
    )
    arm(ctx, "shell.action.file.exit")
    dialog = ctx.wait_json(_BUTTONS, lambda row: "Keep It Running" in row.get("buttons", []), timeout=15)
    ctx.shot("cb7-close", kind="window")
    ctx.check("close-dialog", "FreeCAD" in dialog.get("text", ""), "dialog says the run opened FreeCAD", dialog.get("text", "")[:300])
    label = "Keep It Running" if keep else "Stop It"
    ctx.check(label, dialog.get("default") == "Keep It Running", "Keep It Running is the default", str(dialog.get("default")))
    ctx.eval(_CLICK % json.dumps(label), wait=15)
    ctx.shot("cb7-after-" + ("keep" if keep else "stop"), kind="desktop")


def _close_freecad(ctx: Ctx) -> None:
    ctx.guest(
        "import os, signal\n"
        "os.system('pkill -u default -f launch_freecad.py || true')\n"
        "root = os.path.dirname(os.path.abspath(__file__))\n"
        "open(os.path.join(root, 'results', 'report.txt'), 'w').write('pkill\\n')\n"
        "print('pkill')\n"
    )


_LOG = r"""
import json
win = next(w for w in app.topLevelWidgets() if type(w).__name__=="MainWindow")
log = None
for widget in app.allWidgets():
    if widget.objectName()=="shell.bottom.runLog":
        log = widget
        break
text = ""
if log is not None and hasattr(log, "toPlainText"):
    text = log.toPlainText()
print("JSON:" + json.dumps({"text": text[-500:]}))
"""

_NOISE = r"""
import json
log = None
for widget in app.allWidgets():
    if widget.objectName()=="shell.bottom.runLog.textArea":
        log = widget
        break
if log is None:
    for widget in app.allWidgets():
        if widget.objectName()=="shell.bottom.runLog" and hasattr(widget, "document"):
            log = widget
            break
rows = []
if log is not None and hasattr(log, "document"):
    doc = log.document()
    block = doc.begin()
    while block.isValid():
        text = block.text()
        noise = ("connect failed" in text) or ("/opt/freecad/usr/lib" in text)
        if noise or text.startswith("tick") or text.startswith("launched"):
            fmt = block.begin().charFormat() if block.begin().isValid() else None
            rows.append({
                "text": text[:160],
                "noise": noise,
                "italic": bool(fmt.fontItalic()) if fmt is not None else False,
                "color": fmt.foreground().color().name() if fmt is not None else "",
                "tooltip": fmt.toolTip() if fmt is not None else "",
            })
        block = block.next()
print("JSON:" + json.dumps({"rows": rows}))
"""

_BUTTONS = r"""
import json
try:
    from PySide2.QtWidgets import QLabel, QPushButton
except ImportError:
    from PySide6.QtWidgets import QLabel, QPushButton
title = ""
text = []
buttons = []
default = ""
for widget in app.topLevelWidgets():
    if not widget.isVisible() or not widget.inherits("QDialog"):
        continue
    title = widget.windowTitle()
    for lab in widget.findChildren(QLabel):
        if (lab.text() or "").strip():
            text.append(" ".join(lab.text().split()))
    for button in widget.findChildren(QPushButton):
        buttons.append(button.text().replace("&", ""))
        if button.isDefault():
            default = button.text().replace("&", "")
print("JSON:" + json.dumps({"title": title, "text": "\n".join(text), "buttons": buttons, "default": default}))
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
            print("clicked")
"""
