"""CB-4 stepped drag, rename, cut/paste, missing file."""

from __future__ import annotations

import json

from scenarios.common import open_file, open_project, write_tree
from scenarios.ctx import Ctx

ROOT = "/home/default/verify-files"


def run(ctx: Ctx) -> None:
    ctx.launch(name="verify-cb4")
    write_tree(
        ctx,
        ROOT,
        {
            "report.py": "def report():\n    return 1\n",
            "old_utils.py": "def util():\n    return 2\n",
            "clip_me.py": "def clip():\n    return 3\n",
            "dest_move/keep.txt": "keep\n",
            "dest_paste/keep.txt": "keep\n",
        },
        "verify-files",
        "report.py",
    )
    open_project(ctx, ROOT)
    open_file(ctx, ROOT + "/report.py")
    rects = ctx.eval_json(_RECTS, wait=20)
    src = rects["report.py"]
    dst = rects["dest_move"]
    ctx.adapter.drag(src["x"], src["y"], dst["x"], dst["y"])
    placed = ctx.wait_json(_WHERE, lambda row: row.get("dst") is True, timeout=8)
    ctx.shot("cb4-02-after-drag", selector="#shell.projectTree", kind="crop")
    ctx.check("drag-moved", placed.get("dst") is True and placed.get("src") is False, "report.py is in dest_move", json.dumps(placed))
    ctx.eval(
        "from pathlib import Path\n"
        "path = Path(%s)\n"
        "path.write_text('moved_line = \"after-drag\"\\n', encoding='utf-8')\n"
        "print('saved', path)\n" % json.dumps(ROOT + "/dest_move/report.py"),
        wait=15,
    )
    text = ctx.eval("print(open(%s, encoding='utf-8').read())\n" % json.dumps(ROOT + "/dest_move/report.py"), wait=15)
    ctx.check("saved-after-drag", "after-drag" in text, "moved_line = after-drag", text.strip())
    ctx.shot("cb4-03-saved-after-drag", kind="window")
    _rename(ctx)
    renamed = ctx.eval("import os\nprint(os.path.isfile(%s))\nprint(open(%s, encoding='utf-8').read())\n" % (
        json.dumps(ROOT + "/renamed_utils.py"),
        json.dumps(ROOT + "/renamed_utils.py"),
    ), wait=15)
    ctx.check("renamed", "True" in renamed and "renamed_line" in renamed, "renamed_utils.py contains renamed_line", renamed.strip()[:200])
    ctx.shot("cb4-05-renamed", kind="crop", selector="#shell.projectTree")
    _cut_paste(ctx)
    pasted = ctx.eval("print(open(%s, encoding='utf-8').read())\n" % json.dumps(ROOT + "/dest_paste/clip_me.py"), wait=15)
    ctx.check("cut-paste", "pasted_line" in pasted, "pasted_line in dest_paste", pasted.strip()[:200])
    ctx.eval("import os\nos.remove(%s)\nprint('removed')\n" % json.dumps(ROOT + "/dest_paste/clip_me.py"), wait=15)
    ctx.eval(
        "from PySide2.QtCore import QTimer\n"
        "path = %s\n"
        "def go():\n"
        "    win = next(w for w in app.topLevelWidgets() if type(w).__name__=='MainWindow')\n"
        "    win._editor_tab_workflow.open_file_at_line(path, 1, preview=False)\n"
        "QTimer.singleShot(0, go)\n"
        "print('reopen')\n" % json.dumps(ROOT + "/dest_paste/clip_me.py"),
        wait=15,
    )
    missing = ctx.wait_json(_TITLE, lambda row: "File Missing" in row.get("title", ""), timeout=12)
    ctx.shot("cb4-07-missing", kind="window")
    ctx.check("file-missing", "File Missing" in missing.get("title", "") and missing.get("default") == "Save As...", "File Missing, Save As default", json.dumps(missing)[:300])


def _rename(ctx: Ctx) -> None:
    ctx.eval(
        "from PySide2.QtCore import QTimer\n"
        "from PySide2.QtWidgets import QLineEdit, QPushButton\n"
        "def go():\n"
        "    win = next(w for w in app.topLevelWidgets() if type(w).__name__=='MainWindow')\n"
        "    win._project_tree_ui_workflow.handle_tree_rename(%s)\n"
        "QTimer.singleShot(0, go)\n"
        "print('rename-armed')\n" % json.dumps(ROOT + "/old_utils.py"),
        wait=15,
    )
    ctx.wait_json(_TITLE, lambda row: row.get("edits"), timeout=8)
    ctx.eval(
        "from PySide2.QtWidgets import QLineEdit, QPushButton\n"
        "for widget in app.topLevelWidgets():\n"
        "    if not widget.isVisible() or not widget.inherits('QDialog'):\n"
        "        continue\n"
        "    edit = widget.findChild(QLineEdit)\n"
        "    if edit is not None:\n"
        "        edit.setText('renamed_utils.py')\n"
        "    for button in widget.findChildren(QPushButton):\n"
        "        if button.text().replace('&', '') in ('OK', 'Rename'):\n"
        "            button.click()\n"
        "            print('ok', button.text())\n"
        "            break\n",
        wait=15,
    )
    ctx.eval(
        "from pathlib import Path\n"
        "path = Path(%s)\n"
        "if path.is_file():\n"
        "    path.write_text('renamed_line = 1\\n', encoding='utf-8')\n"
        "print('renamed-write', path.is_file())\n" % json.dumps(ROOT + "/renamed_utils.py"),
        wait=15,
    )


def _cut_paste(ctx: Ctx) -> None:
    moved = ctx.eval(
        "win = next(w for w in app.topLevelWidgets() if type(w).__name__=='MainWindow')\n"
        "src = %s\n"
        "dst = %s\n"
        "win._tree_clipboard_paths = [src]\n"
        "win._tree_clipboard_cut = True\n"
        "win._project_tree_ui_workflow.handle_tree_paste(dst)\n"
        "import os\n"
        "print(os.path.isfile(dst + '/clip_me.py') and not os.path.isfile(src))\n"
        % (json.dumps(ROOT + "/clip_me.py"), json.dumps(ROOT + "/dest_paste")),
        wait=20,
    )
    if "True" not in moved:
        ctx.check("cut-paste", False, "clip_me.py moved into dest_paste", moved.strip()[:200])
        return
    ctx.eval(
        "from pathlib import Path\n"
        "path = Path(%s)\n"
        "path.write_text('pasted_line = 1\\n', encoding='utf-8')\n"
        "print(path)\n" % json.dumps(ROOT + "/dest_paste/clip_me.py"),
        wait=15,
    )


_RECTS = r"""
import json
win = next(w for w in app.topLevelWidgets() if type(w).__name__=="MainWindow")
tree = win._project_tree_widget
presenter = win._project_tree_presenter
rows = {}
for rel in ("report.py", "dest_move"):
    item = presenter._item_by_relative_path.get(rel)
    rect = tree.visualItemRect(item)
    center = tree.viewport().mapToGlobal(rect.center())
    rows[rel] = {"x": int(center.x()), "y": int(center.y())}
print("JSON:" + json.dumps(rows))
"""

_WHERE = r"""
import json, os
print("JSON:" + json.dumps({
    "src": os.path.isfile("/home/default/verify-files/report.py"),
    "dst": os.path.isfile("/home/default/verify-files/dest_move/report.py"),
}))
"""

_TITLE = r"""
import json
try:
    from PySide2.QtWidgets import QLineEdit, QPushButton
except ImportError:
    from PySide6.QtWidgets import QLineEdit, QPushButton
title = ""
default = ""
edits = 0
for widget in app.topLevelWidgets():
    if not widget.isVisible() or not widget.inherits("QDialog"):
        continue
    title = widget.windowTitle()
    edits = len(widget.findChildren(QLineEdit))
    for button in widget.findChildren(QPushButton):
        if button.isDefault():
            default = button.text().replace("&", "")
print("JSON:" + json.dumps({"title": title, "default": default, "edits": edits}))
"""
