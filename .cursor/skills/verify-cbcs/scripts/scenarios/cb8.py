"""CB-8. Package crud_showcase, install, reinstall, deny Apps, uninstall.

The idesk icon double-click is the one sub-check the confined probe cannot
perform. The launcher file and a desktop shot are still recorded.
"""

from __future__ import annotations

import json

from scenarios.ctx import Ctx
from scenarios.wizard import drive

EXAMPLE = "/home/default/FreeCAD/CBCS/choreboy_code_studio_v0.4.13/example_projects/crud_showcase"
OUT = "/home/default/verify-pkg-out/crud"
APPS = "/home/default/FreeCAD/Apps/crud_showcase"
DESKTOP = "/home/default/crud_showcase.desktop"


def run(ctx: Ctx) -> None:
    try:
        ctx.launch(name="verify-cb8")
        packaged = ctx.eval_json(_PACKAGE, wait=120)
        ctx.metric("artifact", packaged.get("artifact"))
        ctx.check("packaged", packaged.get("success") is True, "crud_showcase installer", json.dumps(packaged)[:400])
        if not packaged.get("artifact"):
            return
        ctx.stop()
        _remember(ctx, str(packaged["artifact"]))
        page, _state = _installer(ctx, "install", "cb8-1-done")
        ctx.check("installed", "is installed" in str(page.get("title") or "").lower(), "done page says installed", str(page.get("title")))
        listing = _guest_json(ctx, _LISTING)
        ctx.metric("install_listing", listing)
        ctx.check("apps-dir", bool(listing.get("apps")), "install dir " + APPS, json.dumps(listing)[:400])
        desktop = str(listing.get("desktop") or "")
        ctx.check("home-launcher", bool(listing.get("desktop_exists")) and "Icon=" not in desktop, "home launcher without Icon=", desktop[:300])
        ctx.check("no-desktop-copy", not listing.get("desktop_folder_copy"), "no copy under ~/Desktop", str(listing.get("desktop_folder_copy")))
        menu = str(listing.get("menu") or "")
        ctx.check("no-menu-file", menu in ("absent",) or menu.startswith("unreadable"), "no menu launcher", menu)
        ctx.check(
            "idesk-double-click",
            True,
            "double-click the idesk Home icon",
            "skipped: confined probe cannot read .idesktop (errno 13), so the icon has no geometry",
            status="skipped",
        )
        _guest_json(ctx, _PLANT_DATA)
        page, _state = _installer(ctx, "install", "cb8-reinstall")
        kept = _guest_json(ctx, _LISTING)
        ctx.check(
            "reinstall-keeps-data",
            kept.get("data") == "part1-data-survives" and "Reinstall" in _buttons(page),
            "Reinstall keeps part1-keep.txt",
            json.dumps({"buttons": _buttons(page), "data": kept.get("data")})[:400],
        )
        before = _guest_json(ctx, _LOCK_APPS)
        page, state = _installer(ctx, "install", "cb8-6-failure")
        after = _guest_json(ctx, _UNLOCK_APPS)
        blob = _dialog_text(state) + "\n" + str(page.get("details") or "") + "\n" + str(page.get("title") or "")
        same = before.get("hashes") == after.get("hashes")
        ctx.check(
            "mode-0555",
            "installation failed" in blob.lower() and ("permission" in blob.lower() or "denied access" in blob.lower()) and same,
            "Installation failed, PermissionError, hashes unchanged",
            "hash_same %s mode %s -> %s\n%s" % (same, before.get("mode"), after.get("mode"), blob[:700]),
        )
        page, _state = _installer(ctx, "uninstall", "cb8-uninstall")
        gone = _guest_json(ctx, _LISTING)
        ctx.check(
            "uninstall-keeps-data",
            gone.get("data") == "part1-data-survives" and not gone.get("main_py") and not gone.get("desktop_exists"),
            "data file remains, main.py and launcher removed",
            json.dumps(gone)[:400],
        )
        ctx.check("uninstalled", "uninstalled" in str(page.get("title") or "").lower(), "uninstall done page", str(page.get("title")))
    finally:
        try:
            ctx.guest(_UNLOCK_APPS)
        except BaseException as exc:
            ctx.note("mode restore: {}".format(exc))


def _installer(ctx: Ctx, mode: str, shot: str):
    artifact = _artifact(ctx)
    ctx.launch(
        entry=artifact + "/installer/install.py",
        package_root=artifact,
        name="verify-crud",
        wait_ready=70,
    )
    page = drive(ctx.eval, mode=mode, timeout=120)
    details = ""
    try:
        payload = ctx.eval_json(_DETAILS, wait=20)
        details = str(payload.get("text") or "")
    except Exception as exc:
        details = "details-unavailable: {}".format(exc)
    page["details"] = details
    ctx.shot(shot, kind="window")
    try:
        ctx.shot(shot + "-desktop", kind="desktop")
    except Exception as exc:
        ctx.note("desktop shot: {}".format(exc))
    state = ctx.adapter.state()
    (ctx.artifacts / (shot + "-state.json")).write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    ctx.stop()
    return page, state


def _remember(ctx: Ctx, artifact: str) -> None:
    quoted = json.dumps(artifact)
    _guest_json(ctx, _REMEMBER % (quoted, quoted))


def _artifact(ctx: Ctx) -> str:
    found = _guest_json(ctx, _FIND)
    path = str(found.get("artifact") or "")
    if not path:
        raise RuntimeError("crud installer artifact is missing")
    return path


def _guest_json(ctx: Ctx, code: str) -> dict:
    text = ctx.guest(code)
    for line in reversed(text.splitlines()):
        if line.startswith("JSON:"):
            payload = json.loads(line[5:])
            return payload if isinstance(payload, dict) else {}
    raise RuntimeError("no JSON from guest\n" + text[-800:])


def _buttons(page: dict) -> list:
    return [str(step.get("button") or "") for step in (page.get("log") or []) if step.get("button")]


def _dialog_text(state: dict) -> str:
    chunks = []
    for row in state.get("dialogs") or []:
        chunks.append(str(row.get("title") or ""))
        chunks.extend(str(item) for item in (row.get("labels") or []))
    return "\n".join(chunks)


_DETAILS = r"""
import json
try:
    from PySide2.QtWidgets import QPlainTextEdit
except ImportError:
    from PySide6.QtWidgets import QPlainTextEdit
chunks = []
for widget in app.allWidgets():
    if isinstance(widget, QPlainTextEdit):
        text = widget.toPlainText() or ""
        if text.strip():
            chunks.append(text)
print("JSON:" + json.dumps({"text": "\n".join(chunks)[:2500]}))
"""

_PACKAGE = r"""
import json
from pathlib import Path
root = Path(%s)
meta = root / "cbcs" / "project.json"
if not meta.is_file():
    meta.parent.mkdir(parents=True, exist_ok=True)
    meta.write_text(json.dumps({
        "schema_version": 2,
        "name": "CRUD Showcase",
        "project_id": "proj_crud_showcase",
        "default_entry": "main.py",
        "default_argv": [],
        "env_overrides": {},
        "exclude_patterns": ["vendor"],
        "run_configs": [],
        "project_notes": "",
        "template": "blank_project",
        "working_directory": ".",
    }), encoding="utf-8")
from app.packaging.packager import package_project
out = Path(%s)
out.mkdir(parents=True, exist_ok=True)
result = package_project(project_root=str(root), project_name="CRUD Showcase", entry_file="main.py", output_dir=str(out))
print("JSON:" + json.dumps({
    "success": bool(result.success),
    "error": str(result.error or ""),
    "artifact": str(result.artifact_root or ""),
}))
""" % (json.dumps(EXAMPLE), json.dumps(OUT))

_REMEMBER = r"""
import json, os
path = "/home/default/verify-pkg-out/crud-artifact.txt"
open(path, "w", encoding="utf-8").write(%s + "\n")
root = os.path.dirname(os.path.abspath(__file__))
line = "JSON:" + json.dumps({"artifact": %s})
open(os.path.join(root, "results", "report.txt"), "w").write(line + "\n")
print(line)
"""

_FIND = r"""
import json, os
path = "/home/default/verify-pkg-out/crud-artifact.txt"
artifact = open(path, encoding="utf-8").read().strip() if os.path.isfile(path) else ""
root = os.path.dirname(os.path.abspath(__file__))
line = "JSON:" + json.dumps({"artifact": artifact})
open(os.path.join(root, "results", "report.txt"), "w").write(line + "\n")
print(line)
"""

_LISTING = r"""
import json, os
from pathlib import Path
apps = Path("/home/default/FreeCAD/Apps/crud_showcase")
desktop = Path("/home/default/crud_showcase.desktop")
desktop_copy = Path("/home/default/Desktop/crud_showcase.desktop")
menu = Path("/home/default/.local/share/applications/crud_showcase.desktop")
data = ""
data_path = apps / "part1-keep.txt"
if data_path.is_file():
    data = data_path.read_text(encoding="utf-8").strip()
main_py = False
files = []
if apps.is_dir():
    for path in apps.rglob("*"):
        if path.is_file():
            rel = str(path.relative_to(apps))
            files.append(rel)
            if rel.endswith("main.py"):
                main_py = True
menu_state = "absent"
try:
    if menu.is_file():
        menu_state = "present"
except OSError as exc:
    menu_note = getattr(exc, "errno", None)
    menu_state = "unreadable errno %s" % menu_note
text = desktop.read_text(encoding="utf-8") if desktop.is_file() else ""
payload = {
    "apps": apps.is_dir(),
    "files": files[:40],
    "main_py": main_py,
    "data": data,
    "desktop_exists": desktop.is_file(),
    "desktop": text[:500],
    "desktop_folder_copy": desktop_copy.is_file(),
    "menu": menu_state,
}
root = os.path.dirname(os.path.abspath(__file__))
line = "JSON:" + json.dumps(payload)
open(os.path.join(root, "results", "report.txt"), "w").write(line + "\n")
print(line)
"""

_PLANT_DATA = r"""
import json, os
from pathlib import Path
path = Path("/home/default/FreeCAD/Apps/crud_showcase/part1-keep.txt")
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text("part1-data-survives\n", encoding="utf-8")
root = os.path.dirname(os.path.abspath(__file__))
line = "JSON:" + json.dumps({"data": path.read_text(encoding="utf-8").strip()})
open(os.path.join(root, "results", "report.txt"), "w").write(line + "\n")
print(line)
"""

_LOCK_APPS = r"""
import hashlib, json, os
from pathlib import Path
apps = Path("/home/default/FreeCAD/Apps")
root_dir = Path("/home/default/FreeCAD/Apps/crud_showcase")
hashes = {}
for rel in ("cbcs_installed_package.json", "part1-keep.txt", "main.py", "app_files/main.py"):
    path = root_dir / rel
    hashes[rel] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else ""
if apps.is_dir():
    os.chmod(apps, 0o555)
mode = oct(apps.stat().st_mode & 0o777) if apps.exists() else ""
root = os.path.dirname(os.path.abspath(__file__))
line = "JSON:" + json.dumps({"mode": mode, "hashes": hashes})
open(os.path.join(root, "results", "report.txt"), "w").write(line + "\n")
print(line)
"""

_UNLOCK_APPS = r"""
import hashlib, json, os
from pathlib import Path
apps = Path("/home/default/FreeCAD/Apps")
root_dir = Path("/home/default/FreeCAD/Apps/crud_showcase")
if apps.is_dir():
    os.chmod(apps, 0o755)
hashes = {}
for rel in ("cbcs_installed_package.json", "part1-keep.txt", "main.py", "app_files/main.py"):
    path = root_dir / rel
    hashes[rel] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else ""
mode = oct(apps.stat().st_mode & 0o777) if apps.exists() else ""
root = os.path.dirname(os.path.abspath(__file__))
line = "JSON:" + json.dumps({"mode": mode, "hashes": hashes})
open(os.path.join(root, "results", "report.txt"), "w").write(line + "\n")
print(line)
"""
