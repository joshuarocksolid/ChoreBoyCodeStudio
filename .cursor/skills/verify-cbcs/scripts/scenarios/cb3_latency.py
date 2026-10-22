"""CB-3 latency. The acceptance target is a median to_paint_ms under 150."""

from __future__ import annotations

import json

from scenarios.ctx import Ctx

ROOT = "/home/default/verify-completion"
TARGET_MS = 150


def run(ctx: Ctx) -> None:
    import time
    ctx.guest(_TREE)
    samples = []
    discarded = []
    shot = False
    attempt = 0
    while len(samples) < 5 and attempt < 8:
        ctx.launch(name="verify-lat%d" % attempt, home="/home/default")
        try:
            ready = ctx.wait_json(_FILE, lambda row: row.get("ready"), timeout=5)
        except RuntimeError as exc:
            discarded.append({"index": attempt, "stage": "restore", "error": str(exc)[-180:]})
            ctx.stop()
            attempt += 1
            continue
        if not ready.get("ready"):
            try:
                ready = ctx.eval_json(_OPEN_FILE % json.dumps(ROOT + "/main.py"), wait=30)
            except RuntimeError as exc:
                discarded.append({"index": attempt, "stage": "open", "error": str(exc)[-180:]})
                ctx.stop()
                attempt += 1
                continue
        if not ready.get("ready"):
            discarded.append({"index": attempt, "stage": "open", "tail": ready.get("tail"), "title": ready.get("title")})
            ctx.stop()
            attempt += 1
            continue
        try:
            ctx.eval_json(_PREP, wait=20)
        except RuntimeError as exc:
            discarded.append({"index": attempt, "stage": "prep", "error": str(exc)[-180:]})
            ctx.stop()
            attempt += 1
            continue
        time.sleep(5)
        try:
            measured = ctx.eval_json(MEASURE, wait=25)
        except RuntimeError as exc:
            discarded.append({"index": attempt, "stage": "measure", "error": str(exc)[-180:]})
            ctx.stop()
            attempt += 1
            continue
        paint = measured.get("to_paint_ms")
        ctx.metric("sample_%d" % attempt, measured)
        if paint is None:
            discarded.append({"index": attempt, "stage": "measure", "measured": measured})
            ctx.stop()
            attempt += 1
            continue
        samples.append(paint)
        if not shot:
            ctx.shot("cb3-latency", selector="#shell.mainWindow", kind="crop")
            shot = True
        ctx.stop()
        attempt += 1
    ctx.metric("samples", samples)
    ctx.metric("discarded", discarded)
    ctx.metric("n", len(samples))
    if not samples:
        raise RuntimeError("no to_paint_ms samples " + json.dumps(discarded)[:1500])
    median = _median(samples)
    ctx.metric("median_to_paint_ms", median)
    ctx.metric("target_ms", TARGET_MS)
    ctx.metric("event", "open")
    ctx.check(
        "median-under-150",
        median is not None and median < TARGET_MS,
        "median to_paint_ms < 150",
        str(median),
    )


def _median(samples):
    if not samples:
        return None
    ordered = sorted(samples)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


_TREE = r"""
import json, os
from pathlib import Path
root = Path("/home/default/verify-completion")
(root / "cbcs").mkdir(parents=True, exist_ok=True)
meta = {
    "schema_version": 2, "name": "verify-completion", "project_id": "proj_verify_completion",
    "default_entry": "main.py", "default_argv": [], "env_overrides": {},
    "exclude_patterns": ["vendor"], "run_configs": [], "project_notes": "",
    "template": "blank_project", "working_directory": ".",
}
(root / "cbcs" / "project.json").write_text(json.dumps(meta), encoding="utf-8")
(root / "main.py").write_text("from PySide2.QtWidgets import QPushButton\nbtn = QPushButton()\n", encoding="utf-8")
report = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "report.txt")
open(report, "w").write("wrote\n")
print("wrote")
"""

_FILE = r"""
import json
win = next(w for w in app.topLevelWidgets() if type(w).__name__=="MainWindow")
ed = win._editor_tab_workflow.active_editor_widget()
text = "" if ed is None else ed.toPlainText()
loaded = getattr(win, "_loaded_project", None)
root = "" if loaded is None else str(getattr(loaded, "project_root", "") or "")
print("JSON:" + json.dumps({
    "ready": root == "/home/default/verify-completion" and ("QPushButton" in text or "btn" in text),
    "title": win.windowTitle(),
    "tail": text[-80:],
}))
"""

_OPEN_FILE = r"""
import json
path = %s
win = next(w for w in app.topLevelWidgets() if type(w).__name__=="MainWindow")
ed = win._editor_tab_workflow.active_editor_widget()
text = "" if ed is None else ed.toPlainText()
if "QPushButton" not in text and "btn" not in text:
    win._editor_tab_workflow.open_file_at_line(path, 1, preview=False)
    ed = win._editor_tab_workflow.active_editor_widget()
    text = "" if ed is None else ed.toPlainText()
loaded = getattr(win, "_loaded_project", None)
root = "" if loaded is None else str(getattr(loaded, "project_root", "") or "")
print("JSON:" + json.dumps({
    "ready": ("QPushButton" in text or "btn" in text),
    "title": win.windowTitle(),
    "root": root,
    "tail": text[-80:],
}))
"""

_PREP = r"""
import json
from PySide2.QtGui import QTextCursor
win = next(w for w in app.topLevelWidgets() if type(w).__name__=="MainWindow")
ed = win._editor_tab_workflow.active_editor_widget()
text = "" if ed is None else ed.toPlainText()
if ed is not None and "btn." not in text:
    ed.appendPlainText("btn.")
    cursor = ed.textCursor()
    cursor.movePosition(QTextCursor.End)
    ed.setTextCursor(cursor)
    text = ed.toPlainText()
popup = None if ed is None else ed._completion_popup
mode = ""
if popup is not None:
    popup.set_mode("manual")
    mode = str(popup._mode)
print("JSON:" + json.dumps({"mode": mode, "tail": text[-40:]}))
"""

_LOADED = r"""
import json
win = next(w for w in app.topLevelWidgets() if type(w).__name__=="MainWindow")
loaded = getattr(win, "_loaded_project", None)
root = "" if loaded is None else str(getattr(loaded, "project_root", "") or "")
print("JSON:" + json.dumps({"root": root, "title": win.windowTitle()}))
"""

MEASURE = r"""
import json
from PySide2.QtCore import QEventLoop, QTimer
win = next(w for w in app.topLevelWidgets() if type(w).__name__=="MainWindow")
ed = win._editor_tab_workflow.active_editor_widget()
popup = ed._completion_popup
popup.set_mode("manual")
before = len(popup.metrics)
popup.open_manual()
loop = QEventLoop()
QTimer.singleShot(5000, loop.quit)
loop.exec_()
rows = []
for entry in popup.metrics[before:]:
    if entry.get("event") in ("open", "open_cached"):
        rows.append({
            "event": entry.get("event"),
            "to_paint_ms": entry.get("to_paint_ms"),
            "delivered_ms": entry.get("delivered_ms"),
            "rows": entry.get("rows"),
        })
paint = None
for row in rows:
    if row.get("event") == "open" and row.get("to_paint_ms") is not None:
        paint = row.get("to_paint_ms")
print("JSON:" + json.dumps({"to_paint_ms": paint, "rows": rows, "visible": bool(popup.is_visible())}))
"""
