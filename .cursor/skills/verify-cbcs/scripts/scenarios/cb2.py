"""CB-2. Version-patched startup dialog, real-1.0 warning chip, then Run."""

from __future__ import annotations

import json

from scenarios import faults
from scenarios.common import arm, open_file, open_project, write_tree
from scenarios.ctx import Ctx


def run(ctx: Ctx) -> None:
    try:
        _startup_old(ctx)
        ctx.stop()
        _startup_real(ctx)
        _run_dialog(ctx)
    finally:
        faults.remove(ctx)


def _startup_old(ctx: Ctx) -> None:
    entry = faults.install(ctx, "plugin_old")
    ctx.launch(entry=entry, name="verify-cb2-old", wait_ready=90, allow_unready=True)
    ctx.wait_json(
        _WINDOWS,
        lambda row: len(row.get("titles") or []) >= 1,
        timeout=25,
    )
    dialog = ctx.wait_json(
        _DIALOG,
        lambda row: "FreeCAD 1.0 is required" in str(row.get("text") or ""),
        timeout=20,
    )
    ctx.shot("cb2-1-freecad-dialog", kind="window")
    blob = json.dumps(dialog)
    ctx.check(
        "freecad-required",
        "FreeCAD 1.0 is required" in blob and "shell.freecadRequirementDialog" in blob,
        "FreeCAD 1.0 is required",
        blob[:700],
    )
    ctx.check(
        "freecad-021-sentence",
        "0.21" in blob,
        "body still mentions FreeCAD 0.21",
        blob[:700],
    )
    ctx.eval(
        "for w in app.topLevelWidgets():\n"
        "    if w.objectName()=='shell.freecadRequirementDialog':\n"
        "        w.accept()\n"
        "print('dismissed')\n",
        wait=15,
    )
    host = _host_payload(ctx.eval(_HOST, wait=20))
    ctx.check("host-stopped", host.get("running") is False, "plugin host is not running", json.dumps(host))
    ctx.shot("cb2-1-editor-plugins-off", selector="#shell.mainWindow", kind="crop")


def _startup_real(ctx: Ctx) -> None:
    entry = faults.install(ctx, "plugin")
    ctx.launch(entry=entry, name="verify-cb2", wait_ready=70, allow_unready=True)
    dialog = ctx.wait_json(
        _DIALOG,
        lambda row: "PermissionError" in str(row.get("chip") or ""),
        timeout=25,
    )
    ctx.shot("cb2-3-chip-warning", kind="window")
    chip = str(dialog.get("chip") or "")
    blob = json.dumps(dialog)
    ctx.metric("startup_chip", chip)
    ctx.check(
        "chip-warning",
        "PermissionError" in chip and "Permission denied" in chip and "/opt/freecad/AppRun" in chip and "shell.freecadRequirementDialog" not in blob,
        "warning chip, no FreeCAD dialog",
        blob[:700],
    )
    root = "/home/default/verify-cb2"
    write_tree(ctx, root, {"main.py": "print('cb2')\n"}, "verify-cb2", "main.py")
    open_project(ctx, root)
    open_file(ctx, root + "/main.py")
    ctx.eval(_FOCUS_EDITOR, wait=15)
    ctx.adapter.oskey("q")
    dirty = ctx.eval_json(_DIRTY, wait=15)
    ctx.check(
        "buffer-dirty",
        bool(dirty.get("dirty")) or "q" in str(dirty.get("text") or ""),
        "a typed line marks the buffer dirty",
        json.dumps(dirty)[:300],
    )


def _run_dialog(ctx: Ctx) -> None:
    ctx.eval(_PATCH_RUN, wait=15)
    arm(ctx, "shell.action.run.run")
    dialog = ctx.wait_json(
        _DIALOG,
        lambda row: "Failed to launch runner process" in str(row.get("text") or ""),
        timeout=20,
    )
    ctx.shot("cb2-2-run-dialog", kind="window")
    blob = json.dumps(dialog)
    ctx.check(
        "run-explanation",
        "shell.freecadRequirementDialog" in blob
        and "Failed to launch runner process: [Errno 13] Permission denied: '/opt/freecad/AppRun'" in blob
        and "FreeCAD 0.21.0" in blob
        and "Traceback" not in blob,
        "WHAT CBCS SAW and the FreeCAD 0.21.0 badge",
        blob[:800],
    )


def _host_payload(text: str) -> dict:
    for line in reversed((text or "").splitlines()):
        if line.startswith("JSON:"):
            try:
                payload = json.loads(line[5:])
            except json.JSONDecodeError:
                return {}
            return payload if isinstance(payload, dict) else {}
    return {}


_WINDOWS = r"""
import json
titles = []
for widget in app.topLevelWidgets():
    if widget.isVisible() and type(widget).__name__ == "MainWindow":
        titles.append(widget.windowTitle() or "")
print("JSON:" + json.dumps({"titles": titles}))
"""

_DIALOG = r"""
import json
try:
    from PySide2.QtWidgets import QLabel
except ImportError:
    from PySide6.QtWidgets import QLabel
titles = []
texts = []
names = []
for widget in app.topLevelWidgets():
    if not widget.isVisible():
        continue
    name = widget.objectName() or ""
    if name:
        names.append(name)
    title = widget.windowTitle() or ""
    if title:
        titles.append(title)
    if widget.inherits("QDialog") or widget.inherits("QMessageBox"):
        for lab in widget.findChildren(QLabel):
            if (lab.text() or "").strip():
                texts.append(" ".join(lab.text().split()))
chip = ""
for widget in app.allWidgets():
    if widget.objectName() == "shell.startupStatusLabel":
        chip = widget.text()
print("JSON:" + json.dumps({
    "title": " | ".join(titles),
    "text": "\n".join(texts),
    "names": names,
    "chip": chip,
}))
"""

_HOST = r"""
import json
win = next(w for w in app.topLevelWidgets() if type(w).__name__=='MainWindow')
host = getattr(win, '_plugin_runtime_manager', None)
alive = False if host is None else bool(host.is_running())
print('JSON:' + json.dumps({'running': alive, 'host': type(host).__name__ if host else ''}))
"""

_FOCUS_EDITOR = r"""
win = next(w for w in app.topLevelWidgets() if type(w).__name__=='MainWindow')
ed = win._editor_tab_workflow.active_editor_widget()
ed.setFocus()
print('focused')
"""

_DIRTY = r"""
import json
win = next(w for w in app.topLevelWidgets() if type(w).__name__=='MainWindow')
ed = win._editor_tab_workflow.active_editor_widget()
doc = ed.document()
print('JSON:' + json.dumps({
    'dirty': bool(doc.isModified()),
    'text': ed.toPlainText()[:80],
}))
"""

_PATCH_RUN = r"""
import app.run.process_supervisor as proc
import app.shell.plugin_host_unavailable_dialog as dlg
import app.shell.startup_dialogs as dialogs

def _version():
    return "0.21.0"

def _boom(*args, **kwargs):
    raise PermissionError(13, "Permission denied", "/opt/freecad/AppRun")

dlg.freecad_version_label = _version
dialogs.freecad_version_label = _version
proc.subprocess.Popen = _boom
print("patched", dlg.freecad_version_label(), dialogs.freecad_version_label())
"""
