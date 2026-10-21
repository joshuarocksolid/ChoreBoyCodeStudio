"""CB-3 completion. Manual, Ctrl+Space, camelCase, tab, docs, off, console."""

from __future__ import annotations

import json

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
    ctx.adapter.oskey("set")
    filtered = _probe(ctx)
    ctx.check("filter-set", filtered.get("current") == "setAcceptDrops", "current item setAcceptDrops", str(filtered.get("current")))
    _newline(ctx)
    ctx.adapter.oskey("btn.")
    ctx.adapter.ctrl_space()
    ctx.wait_json(PROBE, lambda row: row.get("visible"), timeout=8)
    ctx.adapter.oskey("sT")
    camel = _probe(ctx)
    ctx.shot("cb3-06-camel", selector="#shell.mainWindow", kind="crop")
    ctx.check(
        "camel-sT",
        camel.get("current") == "setText" and "setText" in str(camel.get("signature")),
        "setText first, signature setText(text: str) -> None",
        json.dumps({"current": camel.get("current"), "signature": camel.get("signature")}),
    )
    _newline(ctx)
    ctx.adapter.oskey("record.")
    ctx.adapter.ctrl_space()
    big = ctx.wait_json(PROBE, lambda row: row.get("has_field_600"), timeout=10)
    ctx.check("field-600", big.get("field_600_index") == 600, "field_600 index 600", str(big.get("field_600_index")))
    _newline(ctx)
    ctx.adapter.oskey("btn.")
    ctx.adapter.ctrl_space()
    ctx.wait_json(PROBE, lambda row: row.get("visible"), timeout=8)
    ctx.adapter.oskey("setzzz")
    typo = _probe(ctx)
    ctx.check("typo-closes", not typo.get("visible"), "typo closes the list", str(typo.get("visible")))
    ctx.adapter.oskey(keyname="BackSpace")
    ctx.adapter.oskey(keyname="BackSpace")
    ctx.adapter.oskey(keyname="BackSpace")
    reopened = ctx.wait_json(PROBE, lambda row: row.get("visible"), timeout=4)
    ctx.check("backspace-reopens", bool(reopened.get("visible")), "backspace reopens the list", str(reopened.get("visible")))
    _newline(ctx)
    ctx.adapter.oskey('btn.set("keep")')
    ctx.eval(_CARET, wait=15)
    ctx.adapter.ctrl_space()
    ctx.wait_json(PROBE, lambda row: row.get("visible"), timeout=8)
    ctx.adapter.oskey(keyname="Tab")
    accepted = _probe(ctx)
    ctx.check("tab-accepts", "setText" in str(accepted.get("line")) or "setAcceptDrops" in str(accepted.get("line")), "tab accepts the first set* match", accepted.get("line"))
    _newline(ctx)
    ctx.adapter.oskey("btn.")
    ctx.adapter.ctrl_space()
    ctx.wait_json(PROBE, lambda row: row.get("visible"), timeout=8)
    ctx.adapter.oskey("setT")
    docs = _probe(ctx)
    ctx.shot("cb3-14-docs", selector="#shell.mainWindow", kind="crop")
    ctx.check("docs-signature", "setText" in str(docs.get("signature")), "docs pane shows the signature", str(docs.get("signature")))
    ctx.check("docs-paragraph-empty", not str(docs.get("summary") or "").strip(), "doc paragraph is empty", str(docs.get("summary")))
    _set_mode(ctx, "typing")
    chip = _probe(ctx)
    ctx.shot("cb3-20-chip", selector="#shell.mainWindow", kind="crop")
    ctx.check("while-typing-chip", "While typing" in str(chip.get("status")), "Completion: While typing (Global setting)", chip.get("status"))
    _set_mode(ctx, "off")
    _newline(ctx)
    ctx.adapter.oskey("btn.")
    ctx.adapter.ctrl_space()
    off = _probe(ctx)
    ctx.check(
        "off-mode",
        (not off.get("visible")) and "off" in str(off.get("status")).lower(),
        "popup closed and completion is off",
        json.dumps({"visible": off.get("visible"), "status": off.get("status")}),
    )
    _console(ctx)


def _set_mode(ctx: Ctx, mode: str) -> None:
    arm(ctx, "shell.action.file.settings")
    ctx.wait_json(_SETTINGS, lambda row: row.get("open"), timeout=8)
    ctx.eval(_SET_MODE % json.dumps(mode), wait=15)


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


def _console(ctx: Ctx) -> None:
    ctx.eval(
        "win = next(w for w in app.topLevelWidgets() if type(w).__name__=='MainWindow')\n"
        "con = win._python_console_widget\n"
        "con.setFocus()\n"
        "print('console')\n",
        wait=15,
    )
    ctx.adapter.oskey('btn = __import__("PySide2").QtWidgets.QPushButton("OK")')
    ctx.adapter.oskey(keyname="Return")
    ctx.adapter.oskey("btn.")
    state = _probe(ctx)
    ctx.shot("cb3-k01-console", selector="#shell.mainWindow", kind="crop")
    ctx.check("console-dot", not state.get("visible"), "console btn. does not pop", str(state.get("visible")))
    ctx.adapter.ctrl_space()
    opened = ctx.wait_json(PROBE, lambda row: row.get("has_setText"), timeout=8)
    ctx.check("console-ctrl-space", bool(opened.get("has_setText")), "console Ctrl+Space includes setText", str(opened.get("shown")))


_SETTINGS = r"""
import json
open_ = False
for widget in app.topLevelWidgets():
    if widget.isVisible() and widget.objectName()=="shell.settingsDialog":
        open_ = True
print("JSON:" + json.dumps({"open": open_}))
"""

_SET_MODE = r"""
from PySide2.QtWidgets import QComboBox, QPushButton
dlg = next(w for w in app.topLevelWidgets() if w.objectName()=="shell.settingsDialog")
dlg._scope_input._buttons["global"].click()
combo = dlg.findChild(QComboBox, "shell.settingsDialog.completionMode")
wanted = %s
for i in range(combo.count()):
    if combo.itemData(i) == wanted:
        combo.setCurrentIndex(i)
        break
dlg.findChild(QPushButton, "shell.settingsDialog.okBtn").click()
print("saved", wanted)
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
    "line": ed.textCursor().block().text(),
    "status": status,
}))
"""
