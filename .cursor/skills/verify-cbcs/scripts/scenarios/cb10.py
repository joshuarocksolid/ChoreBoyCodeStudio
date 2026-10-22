"""CB-10. Replace moves a Macro/Apps crud_showcase install into FreeCAD/Apps."""

from __future__ import annotations

import json

from scenarios.cb8 import _guest_json, _installer
from scenarios.ctx import Ctx

LEGACY = "/home/default/.local/share/FreeCAD/Macro/Apps/crud_showcase"


def run(ctx: Ctx) -> None:
    planted = _guest_json(ctx, _PLANT)
    ctx.metric("legacy", planted)
    ctx.check("legacy-planted", planted.get("planted") is True, "version 0.0.9 with old_data.txt", json.dumps(planted)[:300])
    page, _state = _installer(ctx, "install", "cb10-replace")
    buttons = [str(step.get("button") or "") for step in (page.get("log") or [])]
    moved = _guest_json(ctx, _CHECK)
    ctx.metric("moved", moved)
    ctx.check(
        "replace-offered",
        any(button == "Replace" for button in buttons),
        "installer button Replace",
        " ".join(buttons),
    )
    ctx.check(
        "legacy-moved",
        moved.get("old_gone") is True and moved.get("data") == "legacy-data-kept" and moved.get("main_py") is True,
        "old_data.txt in FreeCAD/Apps and the Macro slot is gone",
        json.dumps(moved)[:400],
    )
    ctx.check("replaced", "is installed" in str(page.get("title") or "").lower(), "done page after Replace", str(page.get("title")))


_PLANT = r"""
import json, os, shutil
from pathlib import Path
apps = Path("/home/default/FreeCAD/Apps/crud_showcase")
if apps.exists():
    shutil.rmtree(apps)
legacy = Path("/home/default/.local/share/FreeCAD/Macro/Apps/crud_showcase")
if legacy.exists():
    shutil.rmtree(legacy)
legacy.mkdir(parents=True)
(legacy / "cbcs_installed_package.json").write_text(json.dumps({
    "package_id": "crud_showcase",
    "version": "0.0.9",
    "launcher_filename": "crud_showcase.desktop",
}), encoding="utf-8")
(legacy / "old_data.txt").write_text("legacy-data-kept\n", encoding="utf-8")
Path("/home/default/crud_showcase.desktop").write_text(
    "[Desktop Entry]\nType=Application\nName=CRUD Showcase\nExec=echo old\n",
    encoding="utf-8",
)
root = os.path.dirname(os.path.abspath(__file__))
line = "JSON:" + json.dumps({"planted": legacy.is_dir(), "version": "0.0.9"})
open(os.path.join(root, "results", "report.txt"), "w").write(line + "\n")
print(line)
"""

_CHECK = r"""
import json, os
from pathlib import Path
legacy = Path("/home/default/.local/share/FreeCAD/Macro/Apps/crud_showcase")
apps = Path("/home/default/FreeCAD/Apps/crud_showcase")
data = ""
data_path = apps / "old_data.txt"
if data_path.is_file():
    data = data_path.read_text(encoding="utf-8").strip()
main_py = False
if apps.is_dir():
    for path in apps.rglob("main.py"):
        if path.is_file():
            main_py = True
payload = {"old_gone": not legacy.exists(), "data": data, "main_py": main_py, "apps": apps.is_dir()}
root = os.path.dirname(os.path.abspath(__file__))
line = "JSON:" + json.dumps(payload)
open(os.path.join(root, "results", "report.txt"), "w").write(line + "\n")
print(line)
"""
