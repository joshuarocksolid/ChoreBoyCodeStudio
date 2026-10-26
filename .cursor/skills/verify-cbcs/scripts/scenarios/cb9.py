"""CB-9 shop pointer. Final-fc10 contract: missing parent is not created."""

from __future__ import annotations

import json

from scenarios.common import arm
from scenarios.ctx import Ctx

POINTER = "/home/default/share/Chore_Boy/CBCS/cbcs_state_root"
SHARED = "/home/default/share/verify-shared"
LEAF = "/home/default/share/verify-parent/leaf"
MISSING = "/home/default/share/verify-no-such-parent/leaf"


def run(ctx: Ctx) -> None:
    try:
        _pointer(ctx, SHARED)
        ctx.guest(_mkdir(SHARED))
        ctx.guest(_mkdir("/home/default/share/verify-parent"))
        ctx.launch(name="verify-cb9")
        arm(ctx, "shell.action.view.theme.dark")
        seen = ctx.wait_json(_settings(), lambda row: "dark" in row.get("text", ""), timeout=20)
        ctx.shot("cb9-1-shared-dark", selector="#shell.mainWindow", kind="crop")
        ctx.check("shared-dark", "dark" in seen.get("text", ""), "shared settings theme dark", seen.get("text", "")[:200])
        ctx.eval(
            "from app.shell.python_console_history import save_python_console_history\n"
            "win = next(w for w in app.topLevelWidgets() if type(w).__name__=='MainWindow')\n"
            "save_python_console_history(win._python_console_history_path, ['verify-shared'], max_entries=50)\n"
            "print('saved')\n",
            wait=15,
        )
        names = ctx.eval(_listdir(SHARED), wait=15)
        ctx.check(
            "json-only",
            "settings.json" in names and "sqlite" not in names,
            "shared dir is JSON only",
            names.strip(),
        )
        hist = ctx.eval(
            "import os\n"
            "p='/home/default/FreeCAD/CBCS/state/history/index.sqlite3'\n"
            "print(os.path.getsize(p) if os.path.isfile(p) else -1)\n",
            wait=15,
        )
        ctx.check("sqlite-stayed", "98304" in hist, "history sqlite stays 98304", hist.strip())
        ctx.stop()
        _pointer(ctx, LEAF)
        ctx.launch(name="verify-cb9b")
        created = ctx.eval(_listdir(LEAF), wait=15)
        ctx.shot("cb9-2-leaf-created", kind="window")
        ctx.check("leaf-created", "settings.json" in created or "ABSENT" not in created, "leaf under an existing parent is created", created.strip()[:240])
        ctx.stop()
        _pointer(ctx, MISSING)
        ctx.launch(name="verify-cb9c", allow_unready=True)
        label = ctx.wait_chip("Shared settings are not available", timeout=25)
        ctx.shot("cb9-3-chip", selector="#shell.startupStatusLabel", kind="crop")
        ctx.check("missing-parent", "Shared settings are not available" in label, "chip says shared settings are not available", label)
        parent = MISSING.rsplit("/", 1)[0]
        made = ctx.eval("import os\nprint('ABSENT' if not os.path.exists(%s) else 'CREATED')\n" % json.dumps(parent), wait=15)
        ctx.check("created-nothing", "ABSENT" in made, "missing parent is not created", made.strip())
    finally:
        ctx.guest(_clean())


def _pointer(ctx: Ctx, target: str) -> None:
    code = (
        "import os\n"
        "path = %s\n"
        "os.makedirs(os.path.dirname(path), exist_ok=True)\n"
        "open(path, 'w', encoding='utf-8').write(%s + '\\n')\n"
        "root = os.path.dirname(os.path.abspath(__file__))\n"
        "open(os.path.join(root, 'results', 'report.txt'), 'w').write('pointer\\n')\n"
        "print('pointer')\n"
    ) % (json.dumps(POINTER), json.dumps(target))
    ctx.guest(code)


def _mkdir(path: str) -> str:
    return (
        "import os\n"
        "os.makedirs(%s, exist_ok=True)\n"
        "root = os.path.dirname(os.path.abspath(__file__))\n"
        "open(os.path.join(root, 'results', 'report.txt'), 'w').write('mkdir\\n')\n"
        "print('mkdir')\n"
    ) % json.dumps(path)


def _settings() -> str:
    return (
        "import json, os\n"
        "path = %s\n"
        "text = open(path, encoding='utf-8').read() if os.path.isfile(path) else ''\n"
        "print('JSON:' + json.dumps({'text': text}))\n"
    ) % json.dumps(SHARED + "/settings.json")


def _listdir(path: str) -> str:
    return (
        "import os\n"
        "path = %s\n"
        "print(' '.join(sorted(os.listdir(path))) if os.path.isdir(path) else ('FILE' if os.path.isfile(path) else 'ABSENT'))\n"
    ) % json.dumps(path)


def _clean() -> str:
    return r"""
import os, shutil
paths = [
    "/home/default/share/Chore_Boy/CBCS/cbcs_state_root",
    "/home/default/share/verify-shared",
    "/home/default/share/verify-parent",
    "/home/default/share/verify-no-such-parent",
]
for path in paths:
    if os.path.isdir(path) and not os.path.islink(path):
        shutil.rmtree(path)
    elif os.path.lexists(path):
        os.remove(path)
root = os.path.dirname(os.path.abspath(__file__))
open(os.path.join(root, "results", "report.txt"), "w").write("cleaned\n")
print("cleaned")
"""
