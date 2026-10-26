"""CB-5 tab drag, split, close group. Restore after restart is the expected failure."""

from __future__ import annotations

import json
import time

from scenarios.common import arm, open_project, write_tree
from scenarios.ctx import Ctx

ROOT = "/home/default/verify-groups"


def run(ctx: Ctx) -> None:
    ctx.launch(name="verify-cb5")
    write_tree(
        ctx,
        ROOT,
        {
            "report.py": "report = 1\n",
            "clip_me.py": "clip = 2\n",
            "keep.txt": "keep\n",
        },
        "verify-groups",
        "report.py",
    )
    open_project(ctx, ROOT)
    for name in ("report.py", "clip_me.py", "keep.txt"):
        ctx.eval(
            "win = next(w for w in app.topLevelWidgets() if type(w).__name__=='MainWindow')\n"
            "win._editor_tab_workflow.open_file_at_line(%s, 1, preview=False)\n"
            "print('opened')\n" % json.dumps(ROOT + "/" + name),
            wait=15,
        )
    before = ctx.eval_json(LAYOUT, wait=20)
    tabs = before["groups"][0]["tabs"]
    ctx.adapter.drag(tabs[-1]["x"], tabs[-1]["y"], tabs[0]["x"], tabs[0]["y"])
    after = ctx.eval_json(LAYOUT, wait=20)
    ctx.shot("cb5-01-tab-drag", selector="#shell.editorTabs", kind="crop")
    order = [tab["text"] for tab in after["groups"][0]["tabs"]]
    ctx.check("reorder", order and order[0].startswith("keep"), "keep.txt moved to first", " ".join(order))
    ctx.eval(
        "win = next(w for w in app.topLevelWidgets() if type(w).__name__=='MainWindow')\n"
        "print(win._editor_groups.split_right(), len(win._editor_groups._groups))\n",
        wait=15,
    )
    split = ctx.eval_json(LAYOUT, wait=20)
    ctx.shot("cb5-05-split", kind="window")
    ctx.check("split", split.get("n", 0) >= 2, "Split Right makes two groups", str(split.get("n")))
    armed = ctx.eval_json(_ARM_UNIQUE, wait=20)
    ctx.metric("close_target", armed)
    if armed.get("found"):
        ctx.adapter.oskey("Q")
        time.sleep(0.3)
    group_index = armed.get("group")
    group_literal = "None" if group_index is None else str(int(group_index))
    ctx.eval(_CLOSE_GROUP % group_literal, wait=15)
    state = {}
    prompt = ""
    deadline = time.time() + 8
    while time.time() < deadline:
        state = ctx.adapter.state()
        prompt = _dialog_text(state)
        if "editor group" in prompt.lower():
            break
        time.sleep(0.4)
    (ctx.artifacts / "close-state.json").write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    ctx.shot("cb5-08-close-group", kind="window")
    tab_note = ""
    for row in (state.get("tabs") or []):
        if row.get("objectName") == "shell.editorTabs":
            tab_note = " ".join(str(item) for item in (row.get("tabs") or []))
    ctx.check(
        "close-prompt",
        "editor group" in prompt.lower(),
        "Save changes before closing this editor group?",
        (prompt or ("dialogs empty; tabs " + tab_note))[:400],
    )
    ctx.eval(_CLICK_BUTTON % json.dumps("Cancel"), wait=15)
    arm(ctx, "shell.action.view.theme.dark")
    ctx.shot("cb5-11-dark", selector="#shell.mainWindow", kind="crop")
    theme = ctx.eval(
        "import json\n"
        "print(open('/home/default/FreeCAD/CBCS/state/settings.json', encoding='utf-8').read())\n",
        wait=15,
    )
    ctx.check("dark", '"dark"' in theme, "dark theme applied", theme[:180])
    ctx.eval(_EXIT, wait=15)
    deadline = time.time() + 10
    while time.time() < deadline:
        state = ctx.adapter.state()
        if "discard" in _dialog_text(state).lower():
            ctx.eval(_CLICK_BUTTON % json.dumps("Discard"), wait=15)
            break
        time.sleep(0.4)
    ctx.stop()
    ctx.launch(name="verify-cb5b")
    loaded = ctx.wait_json(LOADED, lambda row: row.get("root") == ROOT, timeout=20)
    if loaded.get("root") != ROOT:
        open_project(ctx, ROOT)
    state = {}
    texts = []
    deadline = time.time() + 15
    while time.time() < deadline:
        state = ctx.adapter.state()
        texts = _editor_tabs(state)
        if texts:
            break
        time.sleep(0.5)
    (ctx.artifacts / "restore-state.json").write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    ctx.shot("cb5-04-order-restored", kind="window")
    ctx.metric("restored_tabs", texts)
    ctx.check(
        "restore-split",
        len(texts) >= 2 and any("clip" in " ".join(row) for row in texts),
        "split and clip_me.py restored",
        json.dumps(texts),
    )


def _editor_tabs(state: dict) -> list:
    rows = []
    for row in state.get("tabs") or []:
        labels = [str(item) for item in (row.get("tabs") or [])]
        if row.get("objectName") == "shell.editorTabs" or any(
            token in " ".join(labels) for token in ("keep", "report", "clip")
        ):
            if labels:
                rows.append(labels)
    return rows


def _dialog_text(state: dict) -> str:
    chunks = []
    for row in state.get("dialogs") or []:
        chunks.append(str(row.get("title") or ""))
        chunks.extend(str(item) for item in (row.get("labels") or []))
        chunks.extend(str(item) for item in (row.get("buttons") or []))
    return "\n".join(chunks)


_ARM_UNIQUE = r"""
import json
from PySide2.QtWidgets import QPlainTextEdit
win = next(w for w in app.topLevelWidgets() if type(w).__name__=="MainWindow")
groups = list(win._editor_groups._groups)
found = False
group_index = None
sample = ""
for index, group in enumerate(groups):
    others = [item for item in groups if item is not group]
    for page in group.pages():
        shared = any(other.index_of_buffer(page.buffer_id) >= 0 for other in others)
        if shared:
            continue
        editor = page.findChild(QPlainTextEdit)
        if editor is None:
            continue
        group.tabs.setCurrentWidget(page)
        editor.setFocus()
        found = True
        group_index = index
        sample = editor.toPlainText()[:40]
        break
    if found:
        break
print("JSON:" + json.dumps({"found": found, "group": group_index, "sample": sample, "groups": len(groups)}))
"""

_CLOSE_GROUP = r"""
from PySide2.QtCore import QTimer
from PySide2.QtWidgets import QAction
win = next(w for w in app.topLevelWidgets() if type(w).__name__=="MainWindow")
groups = list(win._editor_groups._groups)
index = %s
if isinstance(index, int) and 0 <= index < len(groups):
    win._editor_groups._set_focused(groups[index])
act = next(a for a in win.findChildren(QAction) if a.objectName()=="shell.action.view.closeEditorGroup")
QTimer.singleShot(0, act.trigger)
print("scheduled", index)
"""

_CLICK_BUTTON = r"""
from PySide2.QtWidgets import QPushButton
needle = %s
clicked = ""
for widget in app.topLevelWidgets():
    if not widget.isVisible() or not widget.inherits("QDialog"):
        continue
    for button in widget.findChildren(QPushButton):
        if needle.lower() in (button.text() or "").lower():
            button.click()
            clicked = button.text()
            break
    if clicked:
        break
print(clicked or "none")
"""

_EXIT = r"""
from PySide2.QtCore import QTimer
from PySide2.QtWidgets import QAction
win = next(w for w in app.topLevelWidgets() if type(w).__name__=="MainWindow")
act = next(a for a in win.findChildren(QAction) if a.objectName()=="shell.action.file.exit")
QTimer.singleShot(0, act.trigger)
print("exit-armed")
"""

LOADED = r"""
import json
win = next(w for w in app.topLevelWidgets() if type(w).__name__=="MainWindow")
loaded = getattr(win, "_loaded_project", None)
root = "" if loaded is None else str(getattr(loaded, "project_root", "") or "")
print("JSON:" + json.dumps({"root": root, "title": win.windowTitle()}))
"""

LAYOUT = r"""
import json
win = next(w for w in app.topLevelWidgets() if type(w).__name__=="MainWindow")
groups = win._editor_groups._groups
payload = {"n": len(groups), "groups": []}
for group in groups:
    bar = group.tabs.tabBar()
    tabs = []
    for index in range(bar.count()):
        rect = bar.tabRect(index)
        center = bar.mapToGlobal(rect.center())
        tabs.append({"text": bar.tabText(index), "x": int(center.x()), "y": int(center.y())})
    payload["groups"].append({"tabs": tabs})
print("JSON:" + json.dumps(payload))
"""

_LABELS = r"""
import json
try:
    from PySide2.QtWidgets import QLabel
except ImportError:
    from PySide6.QtWidgets import QLabel
texts = []
for widget in app.topLevelWidgets():
    if not widget.isVisible() or not widget.inherits("QDialog"):
        continue
    for lab in widget.findChildren(QLabel):
        if (lab.text() or "").strip():
            texts.append(" ".join(lab.text().split()))
print("JSON:" + json.dumps({"text": "\n".join(texts)}))
"""
