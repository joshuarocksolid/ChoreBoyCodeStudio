"""CB-7. Run opens FreeCAD. Log noise format, Keep, and Stop."""

from __future__ import annotations

import json

from scenarios.common import arm, open_file, open_project, set_theme, write_tree
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
    set_theme(ctx, "light")
    write_tree(ctx, ROOT, {"launch_freecad.py": SCRIPT}, "verify-cb7", "launch_freecad.py")
    open_project(ctx, ROOT)
    open_file(ctx, ROOT + "/launch_freecad.py")
    arm(ctx, "shell.action.run.run")
    ctx.wait_json(_LOG, lambda row: "launched FreeCAD" in row.get("text", ""), timeout=25)
    noise = _read_noise(ctx)
    ctx.shot("cb7-run-log", selector="#shell.bottom.runLog", kind="crop")
    ctx.metric("noise", noise)
    bad = [row for row in noise.get("rows") or [] if row.get("noise")]
    formatted = [row for row in bad if row.get("italic") and row.get("tooltip")]
    ctx.check(
        "log-noise-format",
        bool(bad) and len(formatted) == len(bad),
        "noise lines italic with a tooltip",
        json.dumps(bad)[:500],
    )
    arm(ctx, "shell.action.file.exit")
    dialog = ctx.wait_json(_BUTTONS, lambda row: "Keep It Running" in row.get("buttons", []), timeout=15)
    ctx.shot("cb7-close", kind="window")
    ctx.check("close-dialog", "FreeCAD" in dialog.get("text", ""), "dialog says the run opened FreeCAD", dialog.get("text", "")[:300])
    label = "Keep It Running" if keep else "Stop It"
    ctx.check(label, dialog.get("default") == "Keep It Running", "Keep It Running is the default", str(dialog.get("default")))
    ctx.eval(_CLICK % json.dumps(label), wait=15)
    try:
        ctx.shot("cb7-after-" + ("keep" if keep else "stop"), kind="desktop")
    except Exception as exc:
        ctx.note("desktop shot: {}".format(exc))


def _read_noise(ctx: Ctx) -> dict:
    state = ctx.adapter.state(text_formats=["#shell.bottom.runLog.textArea"], max_lines=40)
    blocks = []
    for item in state.get("text_formats") or []:
        if item.get("blocks"):
            blocks = item["blocks"]
    rows = []
    for block in blocks:
        text = str(block.get("text") or "")
        runs = block.get("runs") or []
        color = ""
        for run in runs:
            if run.get("fg"):
                color = str(run.get("fg"))
        rows.append({
            "text": text[:160],
            "noise": ("connect failed" in text) or ("/opt/freecad/usr/lib" in text),
            "italic": any(bool(run.get("italic")) for run in runs),
            "color": color,
            "tooltip": "",
        })
    tips = ctx.eval_json(_TOOLTIPS, wait=20)
    by_text = {str(row.get("text") or ""): str(row.get("tooltip") or "") for row in tips.get("rows") or []}
    if not rows:
        return tips
    for row in rows:
        row["tooltip"] = by_text.get(row["text"], "")
    return {"rows": rows}


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

_TOOLTIPS = r"""
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
    block = log.document().begin()
    while block.isValid():
        text = block.text()
        noise = ("connect failed" in text) or ("/opt/freecad/usr/lib" in text)
        if noise or text.startswith("tick") or text.startswith("launched"):
            italic = False
            color = ""
            tooltip = ""
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                if frag.isValid():
                    fmt = frag.charFormat()
                    italic = italic or bool(fmt.fontItalic())
                    color = color or fmt.foreground().color().name()
                    tooltip = tooltip or fmt.toolTip()
                it += 1
            rows.append({"text": text[:160], "noise": noise, "italic": italic, "color": color, "tooltip": tooltip})
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
