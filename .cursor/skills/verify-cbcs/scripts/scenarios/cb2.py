"""CB-2. PermissionError on the plugin host, then the same error on Run."""

from __future__ import annotations

import json

from scenarios import faults
from scenarios.common import arm, open_file, write_tree
from scenarios.ctx import Ctx
from scenarios.cb1 import _DIALOG


def run(ctx: Ctx) -> None:
    entry = faults.install(ctx, "plugin")
    try:
        ctx.launch(entry=entry, name="verify-cb2", wait_ready=90, allow_unready=True)
        dialog = ctx.wait_json(_DIALOG, lambda row: "FreeCAD" in row.get("text", "") or "FreeCAD" in row.get("title", ""), timeout=30)
        ctx.shot("cb2-1-freecad-dialog", kind="window")
        blob = json.dumps(dialog)
        ctx.check("freecad-required", "FreeCAD 1.0 is required" in blob, "FreeCAD 1.0 is required", blob[:500])
        ctx.check("freecad-021-sentence", "0.21" in blob, "body still mentions FreeCAD 0.21", blob[:500])
        ctx.eval(
            "for w in app.topLevelWidgets():\n"
            "    if w.isVisible() and (w.inherits('QDialog') or w.inherits('QMessageBox')):\n"
            "        w.accept()\n"
            "print('dismissed')\n",
            wait=15,
        )
        running = ctx.eval(
            "import json\n"
            "win = next(w for w in app.topLevelWidgets() if type(w).__name__=='MainWindow')\n"
            "host = getattr(win, '_plugin_runtime_manager', None)\n"
            "alive = False if host is None else bool(host.is_running())\n"
            "print('JSON:' + json.dumps({'running': alive, 'host': type(host).__name__ if host else ''}))\n",
            wait=20,
        )
        ctx.check("host-stopped", '"running": false' in running.replace(" ", ""), "plugin host is not running", running.strip())
        ctx.shot("cb2-1-editor-plugins-off", selector="#shell.mainWindow", kind="crop")
        root = "/home/default/verify-cb2"
        write_tree(ctx, root, {"main.py": "print('cb2')\n"}, "verify-cb2", "main.py")
        from scenarios.common import open_project
        open_project(ctx, root)
        open_file(ctx, root + "/main.py")
        ctx.eval(
            "import app.run.process_supervisor as proc\n"
            "def _boom(*args, **kwargs):\n"
            "    raise PermissionError(13, 'Permission denied', '/opt/freecad/AppRun')\n"
            "proc.subprocess.Popen = _boom\n"
            "print('patched')\n",
            wait=15,
        )
        arm(ctx, "shell.action.run.run")
        dialog = ctx.wait_json(_DIALOG, lambda row: "Permission denied" in row.get("text", "") or "FreeCAD" in row.get("title", ""), timeout=20)
        ctx.shot("cb2-2-run-explanation", kind="window")
        blob = json.dumps(dialog)
        ctx.check("run-explanation", "Permission denied" in blob and "Traceback" not in blob, "FreeCAD dialog, not a traceback", blob[:500])
    finally:
        faults.remove(ctx)
