"""CB-3 latency. The acceptance target is a median to_paint_ms under 150."""

from __future__ import annotations

import json

from scenarios.common import open_file, open_project, write_tree
from scenarios.ctx import Ctx

ROOT = "/home/default/verify-completion"
TARGET_MS = 150


def run(ctx: Ctx) -> None:
    samples = []
    for index in range(5):
        ctx.launch(name="verify-lat%d" % index, home="/home/default")
        if index == 0:
            body = "from PySide2.QtWidgets import QPushButton\nbtn = QPushButton()\n"
            write_tree(ctx, ROOT, {"main.py": body}, "verify-completion", "main.py")
        open_project(ctx, ROOT)
        open_file(ctx, ROOT + "/main.py")
        ctx.eval(
            "from PySide2.QtGui import QTextCursor\n"
            "win = next(w for w in app.topLevelWidgets() if type(w).__name__=='MainWindow')\n"
            "ed = win._editor_tab_workflow.active_editor_widget()\n"
            "text = ed.toPlainText()\n"
            "if 'btn.' not in text:\n"
            "    ed.appendPlainText('btn.')\n"
            "cursor = ed.textCursor()\n"
            "cursor.movePosition(QTextCursor.End)\n"
            "ed.setTextCursor(cursor)\n"
            "print('ready')\n",
            wait=20,
        )
        import time
        time.sleep(5)
        measured = ctx.eval_json(MEASURE, wait=20)
        paint = measured.get("to_paint_ms")
        if paint is not None:
            samples.append(paint)
        ctx.metric("sample_%d" % index, measured)
        if index == 4:
            ctx.shot("cb3-latency", selector="#shell.mainWindow", kind="crop")
        ctx.stop()
    ctx.metric("samples", samples)
    median = _median(samples)
    ctx.metric("median_to_paint_ms", median)
    ctx.metric("target_ms", TARGET_MS)
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


MEASURE = r"""
import json
from PySide2.QtCore import QEventLoop, QTimer
win = next(w for w in app.topLevelWidgets() if type(w).__name__=="MainWindow")
ed = win._editor_tab_workflow.active_editor_widget()
popup = ed._completion_popup
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
