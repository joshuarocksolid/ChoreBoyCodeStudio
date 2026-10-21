"""CB-5 tab drag, split, close group. Restore after restart is the expected failure."""

from __future__ import annotations

import json

from scenarios.common import open_project, write_tree
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
    from scenarios.common import arm
    arm(ctx, "shell.action.view.closeEditorGroup")
    prompt = ctx.wait_json(_LABELS, lambda row: "closing this editor group" in row.get("text", "").lower(), timeout=8)
    ctx.shot("cb5-08-close-group", kind="window")
    ctx.check("close-prompt", "editor group" in prompt.get("text", "").lower(), "Save changes before closing this editor group?", prompt.get("text", "")[:240])
    ctx.eval(
        "for w in app.topLevelWidgets():\n"
        "    if w.isVisible() and w.inherits('QDialog'):\n"
        "        w.reject()\n"
        "print('cancel')\n",
        wait=15,
    )
    arm(ctx, "shell.action.view.theme.dark")
    ctx.shot("cb5-11-dark", selector="#shell.mainWindow", kind="crop")
    theme = ctx.eval(
        "import json\n"
        "print(open('/home/default/FreeCAD/CBCS/state/settings.json', encoding='utf-8').read())\n",
        wait=15,
    )
    ctx.check("dark", '"dark"' in theme, "dark theme applied", theme[:180])
    ctx.stop()
    ctx.launch(name="verify-cb5b")
    open_project(ctx, ROOT)
    restored = ctx.eval_json(LAYOUT, wait=20)
    ctx.shot("cb5-04-order-restored", kind="window")
    texts = []
    for group in restored.get("groups") or []:
        texts.append([tab["text"] for tab in group.get("tabs") or []])
    ctx.metric("restored_tabs", texts)
    ctx.check(
        "restore-split",
        restored.get("n", 0) >= 2 and any("clip_me" in " ".join(row) for row in texts),
        "split and clip_me.py restored",
        json.dumps(texts),
    )


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
