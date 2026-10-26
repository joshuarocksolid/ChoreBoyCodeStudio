"""The three faults the v0.4.13 drivers injected, and the undo."""

from __future__ import annotations

import json

from scenarios.ctx import Ctx

INSTALL = "/home/default/FreeCAD/CBCS/choreboy_code_studio_v0.4.13"

HISTORY = '''
import os
import traceback
try:
    import app.persistence.local_history_store as store

    def _boom(self, *args, **kwargs):
        raise OSError(13, "Permission denied", "/home/default/verify-cb1/lock-deny-history/index.sqlite3")

    store.LocalHistoryStore.__init__ = _boom
    import runpy
    runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "run_editor.py"), run_name="__main__")
except SystemExit:
    raise
except Exception:
    open("/home/default/verify-aside/wrap_history.err", "w").write(traceback.format_exc())
    raise
'''

FATAL = '''
import os
import traceback
try:
    import app.shell.main_window as main_window

    def _boom(self, *args, **kwargs):
        raise RuntimeError("injected window build failure for acceptance CB-1.3")

    main_window.MainWindow.__init__ = _boom
    import runpy
    runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "run_editor.py"), run_name="__main__")
except SystemExit:
    raise
except Exception:
    open("/home/default/verify-aside/wrap_fatal.err", "w").write(traceback.format_exc())
    raise
'''

PLUGIN = '''
import os
import traceback
try:
    import app.plugins.host_supervisor as host

    def _boom(self, *args, **kwargs):
        raise PermissionError(13, "Permission denied", "/opt/freecad/AppRun")

    host.PluginHostSupervisor.start = _boom
    import runpy
    runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "run_editor.py"), run_name="__main__")
except SystemExit:
    raise
except Exception:
    open("/home/default/verify-aside/wrap_plugin.err", "w").write(traceback.format_exc())
    raise
'''

PLUGIN_OLD = '''
import os
import traceback
try:
    import app.shell.plugin_host_unavailable_dialog as dlg
    import app.plugins.host_supervisor as host

    dlg.freecad_version_label = lambda: "0.21.0"

    def _boom(self, *args, **kwargs):
        raise PermissionError(13, "Permission denied", "/opt/freecad/AppRun")

    host.PluginHostSupervisor.start = _boom
    import runpy
    runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "run_editor.py"), run_name="__main__")
except SystemExit:
    raise
except Exception:
    open("/home/default/verify-aside/wrap_plugin_old.err", "w").write(traceback.format_exc())
    raise
'''

_NAMES = {
    "history": ("verify_wrap_history.py", HISTORY),
    "fatal": ("verify_wrap_fatal.py", FATAL),
    "plugin": ("verify_wrap_plugin.py", PLUGIN),
    "plugin_old": ("verify_wrap_plugin_old.py", PLUGIN_OLD),
}


def install(ctx: Ctx, kind: str) -> str:
    name, body = _NAMES[kind]
    path = INSTALL + "/" + name
    ctx.guest(_WRITE.format(path=json.dumps(path), body=json.dumps(body)))
    return path


def remove(ctx: Ctx) -> None:
    ctx.guest(
        "import os\n"
        "root = %s\n"
        "for name in ('verify_wrap_history.py', 'verify_wrap_fatal.py', 'verify_wrap_plugin.py', 'verify_wrap_plugin_old.py'):\n"
        "    path = root + '/' + name\n"
        "    if os.path.isfile(path):\n"
        "        os.remove(path)\n"
        "        print('removed', path)\n"
        "    else:\n"
        "        print('absent', path)\n"
        "open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results', 'report.txt'), 'w').write('removed\\n')\n"
        % json.dumps(INSTALL)
    )


_WRITE = """
import os
path = {path}
os.makedirs(os.path.dirname(path), exist_ok=True)
os.makedirs("/home/default/verify-aside", exist_ok=True)
open(path, "w", encoding="utf-8").write({body})
root = os.path.dirname(os.path.abspath(__file__))
open(os.path.join(root, "results", "report.txt"), "w").write("wrote " + path + "\\n")
print("wrote", path)
"""
