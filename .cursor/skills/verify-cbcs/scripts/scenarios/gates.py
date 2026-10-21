"""Fresh install gates. The zip was installed once before this scenario."""

from __future__ import annotations

from scenarios.common import open_file, open_project, write_tree
from scenarios.ctx import Ctx


def run(ctx: Ctx) -> None:
    ctx.launch(name="verify-gates", wait_ready=90)
    label = ctx.wait_chip("9/9", timeout=40)
    ctx.shot("gates-1-window", selector="#shell.mainWindow", kind="window")
    ctx.check(
        "runtime-ready",
        "Runtime ready" in label and "9/9" in label,
        "Startup: Runtime ready (9/9 checks)",
        label,
    )
    from scenarios.common import arm

    arm(ctx, "shell.action.tools.runtimeCenter")
    dialog = ctx.wait_json(DIALOG_SNIPPET, lambda row: "healthy" in row.get("text", "").lower() or row.get("title"), timeout=15)
    ctx.shot("gates-2-runtime-center", kind="window")
    blob = (dialog.get("title") or "") + "\n" + (dialog.get("text") or "")
    ctx.check(
        "runtime-center",
        "healthy" in blob.lower(),
        "Runtime looks healthy",
        blob[:400],
    )
    ctx.eval(
        "for w in app.topLevelWidgets():\n"
        "    if w.isVisible() and w.inherits('QDialog'):\n"
        "        w.reject()\n"
        "print('closed')\n",
        wait=15,
    )
    root = "/home/default/verify-gates"
    write_tree(ctx, root, {"main.py": "def hello():\n    return 1\n"}, "verify-gates", "main.py")
    open_project(ctx, root)
    open_file(ctx, root + "/main.py")
    described = ctx.eval(DESCRIBE, wait=20)
    ctx.shot("gates-3-py-highlight", selector="#shell.mainWindow", kind="crop")
    ctx.check("python-keyword", "keyword" in described.lower() and "#0000ff" in described.lower(), "keyword #0000ff", described[-500:])
    log = ctx.eval(
        "print(open('/home/default/FreeCAD/CBCS/state/logs/app.log', encoding='utf-8', errors='replace').read()[-4000:])\n",
        wait=20,
    )
    ctx.check("window-telemetry", "Window shown telemetry" in log and "elapsed_ms=" in log, "elapsed_ms in app.log", _telemetry_line(log))


def _telemetry_line(log: str) -> str:
    for line in log.splitlines():
        if "Window shown telemetry" in line or "elapsed_ms=" in line:
            return line.strip()
    return log[-200:]


DIALOG_SNIPPET = r"""
import json
title = ""
texts = []
for widget in app.topLevelWidgets():
    if not widget.isVisible() or not widget.inherits("QDialog"):
        continue
    title = widget.windowTitle()
    try:
        from PySide2.QtWidgets import QLabel
    except ImportError:
        from PySide6.QtWidgets import QLabel
    for lab in widget.findChildren(QLabel):
        if (lab.text() or "").strip():
            texts.append(lab.text())
print("JSON:" + json.dumps({"title": title, "text": "\n".join(texts)}))
"""

DESCRIBE = r"""
win = next(w for w in app.topLevelWidgets() if type(w).__name__ == "MainWindow")
ed = win._editor_tab_workflow.active_editor_widget()
hl = getattr(ed, "_highlighter", None)
print(type(hl).__name__ if hl is not None else "none")
if hl is not None and hasattr(hl, "describe_position"):
    print(hl.describe_position(0, 0))
"""
