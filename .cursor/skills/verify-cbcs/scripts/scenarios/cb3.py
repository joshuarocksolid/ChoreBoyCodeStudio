"""CB-3 completion. Manual, Ctrl+Space, camelCase, tab, docs, off, console."""

from __future__ import annotations

import json
import time

from scenarios.common import arm, open_file, open_project, write_tree
from scenarios.ctx import Ctx

ROOT = "/home/default/verify-completion"


def run(ctx: Ctx) -> None:
    ctx.launch(name="verify-cb3")
    fields = "\n".join("    field_%d = %d" % (i, i) for i in range(663))
    body = (
        "from PySide2.QtWidgets import QPushButton\n"
        "btn = QPushButton()\n"
        "class Record(object):\n" + fields + "\n"
        "record = Record()\n"
    )
    write_tree(ctx, ROOT, {"main.py": body}, "verify-completion", "main.py")
    _set_mode(ctx, "manual")
    open_project(ctx, ROOT)
    open_file(ctx, ROOT + "/main.py")
    _newline(ctx)
    ctx.adapter.oskey("x = 1.5")
    state = _probe(ctx)
    ctx.shot("cb3-01-fraction", selector="#shell.mainWindow", kind="crop")
    ctx.check("manual-fraction", not state.get("visible"), "no popup for a fraction", json.dumps(state)[:240])
    _newline(ctx)
    ctx.adapter.oskey('"hello"')
    state = _probe(ctx)
    ctx.check("manual-string", not state.get("visible"), "no popup in a string", state.get("line"))
    _newline(ctx)
    ctx.adapter.oskey("# comment")
    state = _probe(ctx)
    ctx.check("manual-comment", not state.get("visible"), "no popup in a comment", state.get("line"))
    _newline(ctx)
    ctx.adapter.oskey("btn.")
    state = _probe(ctx)
    ctx.shot("cb3-03-btn-dot", selector="#shell.mainWindow", kind="crop")
    ctx.check("manual-btn-dot", not state.get("visible"), "no popup for btn.", state.get("line"))
    ctx.adapter.ctrl_space()
    opened = ctx.wait_json(PROBE, lambda row: row.get("visible") and row.get("has_setText"), timeout=8)
    ctx.shot("cb3-04-ctrl-space", selector="#shell.mainWindow", kind="crop")
    ctx.check("ctrl-space-setText", bool(opened.get("has_setText")), "list includes setText", "shown %s total %s" % (opened.get("shown"), opened.get("total")))
    ctx.metric("ctrl_space_shown", opened.get("shown"))
    _keys(ctx, "set")
    filtered = _probe(ctx)
    ctx.check("filter-set", filtered.get("current") == "setAcceptDrops", "current item setAcceptDrops", str(filtered.get("current")))
    _hide(ctx)
    _newline(ctx)
    _keys(ctx, "btn.")
    ctx.adapter.ctrl_space()
    ctx.wait_json(PROBE, lambda row: row.get("visible"), timeout=8)
    _keys(ctx, "sT")
    camel = ctx.wait_json(PROBE, lambda row: row.get("current") == "setText", timeout=8)
    docs = ctx.wait_json(
        PROBE,
        lambda row: "Loading" not in str(row.get("summary") or ""),
        timeout=8,
    )
    ctx.shot("cb3-06-camel", selector="#shell.mainWindow", kind="crop")
    ctx.check(
        "camel-sT",
        camel.get("current") == "setText" and "setText" in str(camel.get("signature") or docs.get("signature")),
        "setText first, signature setText(text: str) -> None",
        json.dumps({"current": camel.get("current"), "signature": docs.get("signature")}),
    )
    ctx.shot("cb3-14-docs", selector="#shell.mainWindow", kind="crop")
    ctx.check("docs-signature", "setText" in str(docs.get("signature")), "docs pane shows the signature", str(docs.get("signature")))
    ctx.check("docs-paragraph-empty", not str(docs.get("summary") or "").strip(), "doc paragraph is empty", str(docs.get("summary")))
    _hide(ctx)
    _newline(ctx)
    _keys(ctx, "record.")
    ctx.adapter.ctrl_space()
    big = ctx.wait_json(PROBE, lambda row: row.get("has_field_600"), timeout=10)
    index = big.get("field_600_index")
    shown = int(big.get("shown") or 0)
    ctx.metric("field_600_index", index)
    ctx.metric("field_600_shown", shown)
    ctx.check(
        "field-600",
        bool(big.get("has_field_600")) and isinstance(index, int) and index > 500 and shown > 500,
        "field_600 present and selectable past row 500",
        "index %s row %s shown %s total %s" % (
            index,
            big.get("field_600_row"),
            shown,
            big.get("total"),
        ),
    )
    _hide(ctx)
    _newline(ctx)
    ctx.adapter.oskey("btn.")
    ctx.adapter.ctrl_space()
    ctx.wait_json(PROBE, lambda row: row.get("visible"), timeout=8)
    _keys(ctx, "setzzz")
    typo = _probe(ctx)
    ctx.check("typo-closes", not typo.get("visible"), "typo closes the list", str(typo.get("visible")))
    for _ in range(3):
        ctx.adapter.oskey(keyname="BackSpace")
    time.sleep(0.4)
    reopened = _probe(ctx)
    ctx.check(
        "backspace-reopens",
        bool(reopened.get("visible")),
        "backspace reopens the list",
        json.dumps({"visible": reopened.get("visible"), "line": reopened.get("line"), "shown": reopened.get("shown")}),
    )
    _newline(ctx)
    ctx.adapter.oskey('btn.set("keep")')
    ctx.eval(_CARET, wait=15)
    ctx.adapter.ctrl_space()
    ctx.wait_json(PROBE, lambda row: row.get("visible"), timeout=8)
    ctx.adapter.oskey(keyname="Tab")
    accepted = _probe(ctx)
    ctx.check("tab-accepts", "setText" in str(accepted.get("line")) or "setAcceptDrops" in str(accepted.get("line")), "tab accepts the first set* match", accepted.get("line"))
    _console(ctx)
    _set_mode(ctx, "typing")
    chip = ctx.wait_json(PROBE, lambda row: "While typing" in str(row.get("status") or ""), timeout=8)
    ctx.shot("cb3-20-chip", selector="#shell.mainWindow", kind="crop")
    ctx.check("while-typing-chip", "While typing" in str(chip.get("status")), "Completion: While typing (Global setting)", chip.get("status"))
    _set_mode(ctx, "off")
    _newline(ctx)
    ctx.adapter.oskey("btn.")
    ctx.adapter.ctrl_space()
    off = ctx.wait_json(PROBE, lambda row: "off" in str(row.get("status") or "").lower(), timeout=8)
    ctx.check(
        "off-mode",
        (not off.get("visible")) and "off" in str(off.get("status")).lower(),
        "popup closed and completion is off",
        json.dumps({"visible": off.get("visible"), "status": off.get("status")}),
    )


def _set_mode(ctx: Ctx, mode: str) -> None:
    arm(ctx, "shell.action.file.settings")
    ctx.wait_json(_SETTINGS, lambda row: row.get("open"), timeout=8)
    ctx.eval(_SET_MODE % json.dumps(mode), wait=15)


def _keys(ctx: Ctx, text: str) -> None:
    for ch in text:
        ctx.adapter.oskey(ch)


def _hide(ctx: Ctx) -> None:
    ctx.eval(
        "win = next(w for w in app.topLevelWidgets() if type(w).__name__=='MainWindow')\n"
        "ed = win._editor_tab_workflow.active_editor_widget()\n"
        "pop = getattr(ed, '_completion_popup', None)\n"
        "if pop is not None:\n"
        "    pop.hide()\n"
        "print('hidden')\n",
        wait=15,
    )


def _newline(ctx: Ctx) -> None:
    ctx.eval(
        "from PySide2.QtGui import QTextCursor\n"
        "win = next(w for w in app.topLevelWidgets() if type(w).__name__=='MainWindow')\n"
        "ed = win._editor_tab_workflow.active_editor_widget()\n"
        "ed.setFocus()\n"
        "cursor = ed.textCursor()\n"
        "cursor.movePosition(QTextCursor.End)\n"
        "ed.setTextCursor(cursor)\n"
        "print('end')\n",
        wait=15,
    )
    ctx.adapter.oskey(keyname="Return")


def _probe(ctx: Ctx) -> dict:
    return ctx.eval_json(PROBE, wait=20)


def _newline_focus(ctx: Ctx) -> None:
    ctx.eval(
        "win = next(w for w in app.topLevelWidgets() if type(w).__name__=='MainWindow')\n"
        "ed = win._editor_tab_workflow.active_editor_widget()\n"
        "ed.setFocus()\n"
        "print('focus')\n",
        wait=15,
    )


def _console(ctx: Ctx) -> None:
    ctx.eval(_CONSOLE_FOCUS, wait=15)
    ctx.adapter.ctrl_space()
    opened = ctx.wait_json(
        CONSOLE_PROBE,
        lambda row: row.get("visible") and _has_builtins(row),
        timeout=8,
    )
    ctx.shot("cb3-11-console", selector="#shell.mainWindow", kind="crop")
    head = [str(item) for item in (opened.get("head") or [])]
    ctx.check(
        "console-ctrl-space",
        bool(opened.get("visible")) and _has_builtins(opened),
        "console Ctrl+Space lists abs, all, and",
        json.dumps({"shown": opened.get("shown"), "visible": opened.get("visible"), "head": head, "line": opened.get("line")}),
    )


_SETTINGS = r"""
import json
open_ = False
for widget in app.topLevelWidgets():
    if widget.isVisible() and widget.objectName()=="shell.settingsDialog":
        open_ = True
print("JSON:" + json.dumps({"open": open_}))
"""

_SET_MODE = r"""
from dataclasses import replace
from PySide2.QtWidgets import QComboBox
dlg = next(w for w in app.topLevelWidgets() if w.isVisible() and w.objectName()=="shell.settingsDialog")
dlg._set_scope("global", apply_snapshot=True)
app.processEvents()
combo = dlg.findChild(QComboBox, "shell.settingsDialog.completionMode")
wanted = %s
index = combo.findData(wanted)
if index < 0:
    raise RuntimeError("completion mode missing: " + wanted)
combo.setCurrentIndex(index)
app.processEvents()
snap = dlg._scope_snapshots.get("global")
if snap is not None:
    dlg._scope_snapshots["global"] = replace(snap, completion_mode=wanted)
dlg._active_scope = "global"
combo.setCurrentIndex(index)
dlg.accept()
print("saved", wanted, combo.currentData())
"""

_CARET = r"""
from PySide2.QtGui import QTextCursor
win = next(w for w in app.topLevelWidgets() if type(w).__name__=="MainWindow")
ed = win._editor_tab_workflow.active_editor_widget()
cursor = ed.textCursor()
block = cursor.block()
text = block.text()
idx = text.rfind("set")
cursor.setPosition(block.position() + idx + 3)
ed.setTextCursor(cursor)
print(text)
"""

PROBE = r"""
import json
from PySide2.QtWidgets import QLabel
win = next(w for w in app.topLevelWidgets() if type(w).__name__=="MainWindow")
focus = app.focusWidget()
ed = focus if getattr(focus, "_completion_popup", None) is not None else win._editor_tab_workflow.active_editor_widget()
pop = ed._completion_popup
item = pop.current_item()
docs = pop._popup.docs_panel()
labels = list(pop._model.labels())
status = ""
for lab in win.findChildren(QLabel):
    if lab.objectName()=="shell.completionModeStatusLabel":
        status = lab.text()
print("JSON:" + json.dumps({
    "visible": bool(pop.is_visible()),
    "current": None if item is None else item.label,
    "has_setText": "setText" in labels,
    "shown": len(labels),
    "total": pop.total_count(),
    "signature": docs.signature_text(),
    "summary": docs.summary_text()[:180],
    "has_field_600": "field_600" in labels,
    "field_600_index": labels.index("field_600") if "field_600" in labels else -1,
    "field_600_row": pop._model.row_of_label("field_600") if hasattr(pop._model, "row_of_label") else -1,
    "line": ed.textCursor().block().text(),
    "status": status,
}))
"""

def _has_builtins(row: dict) -> bool:
    labels = [str(item) for item in (row.get("head") or [])]
    return all(name in labels for name in ("abs", "all", "and"))


_CONSOLE_FOCUS = r"""
from PySide2.QtWidgets import QWidget
win = next(w for w in app.topLevelWidgets() if type(w).__name__=="MainWindow")
win.activateWindow()
win.raise_()
editor = win._editor_tab_workflow.active_editor_widget()
editor_pop = getattr(editor, "_completion_popup", None)
if editor_pop is not None:
    editor_pop.hide()
target = None
for widget in win.findChildren(QWidget):
    if widget.objectName() == "shell.bottom.pythonConsole":
        target = widget
        break
if target is None:
    target = win._python_console_widget
target.setFocus()
target.raise_()
print("FOCUSED", type(target).__name__, target.objectName())
"""

CONSOLE_PROBE = r"""
import json
from PySide2.QtWidgets import QWidget
win = next(w for w in app.topLevelWidgets() if type(w).__name__=="MainWindow")
target = None
for widget in win.findChildren(QWidget):
    if widget.objectName() == "shell.bottom.pythonConsole":
        target = widget
        break
if target is None:
    target = win._python_console_widget
pop = getattr(target, "_completion_popup", None)
labels = [] if pop is None else list(pop._model.labels())
print("JSON:" + json.dumps({
    "visible": False if pop is None else bool(pop.is_visible()),
    "shown": len(labels),
    "head": labels[:12],
    "line": target.textCursor().block().text() if hasattr(target, "textCursor") else "",
}))
"""
