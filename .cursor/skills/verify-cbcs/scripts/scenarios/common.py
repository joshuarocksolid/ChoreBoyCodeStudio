"""Shared editor actions. One structural change, then a state wait."""

from __future__ import annotations

import json

from scenarios.ctx import Ctx


def write_tree(ctx: Ctx, root: str, files: dict, project_name: str, entry: str) -> None:
    meta = {
        "schema_version": 2,
        "name": project_name,
        "project_id": "proj_" + project_name.replace("-", "_"),
        "default_entry": entry,
        "default_argv": [],
        "env_overrides": {},
        "exclude_patterns": ["vendor"],
        "run_configs": [],
        "project_notes": "",
        "template": "blank_project",
        "working_directory": ".",
    }
    payload = {"root": root, "files": files, "meta": meta}
    ctx.eval(
        "import json, os\n"
        "from pathlib import Path\n"
        "spec = json.loads(%s)\n"
        "root = Path(spec['root'])\n"
        "(root / 'cbcs').mkdir(parents=True, exist_ok=True)\n"
        "(root / 'cbcs' / 'project.json').write_text(json.dumps(spec['meta'], indent=2) + '\\n', encoding='utf-8')\n"
        "for name, body in spec['files'].items():\n"
        "    path = root / name\n"
        "    path.parent.mkdir(parents=True, exist_ok=True)\n"
        "    path.write_text(body, encoding='utf-8')\n"
        "print('WROTE', root)\n" % json.dumps(json.dumps(payload)),
        wait=30,
    )


def open_project(ctx: Ctx, root: str, timeout: float = 25) -> dict:
    ctx.eval(
        "from PySide2.QtCore import QTimer\n"
        "root = %s\n"
        "def go():\n"
        "    win = next(w for w in app.topLevelWidgets() if type(w).__name__ == 'MainWindow')\n"
        "    win._file_project_commands_workflow.open_project_by_path(root)\n"
        "QTimer.singleShot(0, go)\n"
        "print('armed')\n" % json.dumps(root),
        wait=15,
    )
    return ctx.wait_json(LOADED_SNIPPET, lambda row: row.get("root") == root, timeout=timeout)


def open_file(ctx: Ctx, path: str) -> None:
    ctx.eval(
        "path = %s\n"
        "win = next(w for w in app.topLevelWidgets() if type(w).__name__ == 'MainWindow')\n"
        "win._editor_tab_workflow.open_file_at_line(path, 1, preview=False)\n"
        "print(win.windowTitle())\n" % json.dumps(path),
        wait=20,
    )


def set_theme(ctx: Ctx, mode: str) -> None:
    arm(ctx, "shell.action.view.theme." + mode)
    ctx.wait_json(
        "import json\n"
        "data = json.loads(open('/home/default/FreeCAD/CBCS/state/settings.json', encoding='utf-8').read())\n"
        "theme = data.get('theme') or {}\n"
        "print('JSON:' + json.dumps({'mode': theme.get('mode')}))\n",
        lambda row: row.get("mode") == mode,
        timeout=8,
    )


def arm(ctx: Ctx, action_id: str) -> None:
    ctx.eval(
        "from PySide2.QtWidgets import QAction\n"
        "from PySide2.QtCore import QTimer\n"
        "act = None\n"
        "for w in app.allWidgets():\n"
        "    found = w.findChild(QAction, %s)\n"
        "    if found:\n"
        "        act = found\n"
        "        break\n"
        "if act is None:\n"
        "    raise RuntimeError('action not found')\n"
        "QTimer.singleShot(0, act.trigger)\n"
        "print(act.objectName())\n" % json.dumps(action_id),
        wait=15,
    )


def write_text(ctx: Ctx, path: str, body: str) -> None:
    ctx.eval(
        "open(%s, 'w', encoding='utf-8').write(%s)\nprint('wrote')\n"
        % (json.dumps(path), json.dumps(body)),
        wait=15,
    )


def read_text(ctx: Ctx, path: str) -> str:
    return ctx.eval("print(open(%s, encoding='utf-8').read())\n" % json.dumps(path), wait=15)


LOADED_SNIPPET = r"""
import json
win = next(w for w in app.topLevelWidgets() if type(w).__name__ == "MainWindow")
loaded = getattr(win, "_loaded_project", None)
root = "" if loaded is None else str(getattr(loaded, "project_root", "") or "")
print("JSON:" + json.dumps({"root": root, "title": win.windowTitle()}))
"""
