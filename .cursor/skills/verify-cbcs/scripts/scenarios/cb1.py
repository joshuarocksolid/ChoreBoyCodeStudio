"""CB-1. Import planted settings, history OSError, fatal MainWindow."""

from __future__ import annotations

import json

from scenarios import faults
from scenarios.ctx import Ctx

HOME = "/home/default/verify-cb1"
LEFTOVER = HOME + "/.local/share/FreeCAD/choreboy_code_studio_state"
SETTINGS = {
    "theme": {"mode": "dark"},
    "marker": "v0412-pref-FC10-DARK",
}


def run(ctx: Ctx) -> None:
    try:
        _upgrade(ctx)
        ctx.stop()
        _history(ctx)
        ctx.stop()
        _fatal(ctx)
    finally:
        faults.remove(ctx)
        ctx.guest(_UNDO)


def _upgrade(ctx: Ctx) -> None:
    planted = ctx.guest(_PLANT)
    ctx.launch(home=HOME, name="verify-cb1", wait_ready=90)
    dialog = ctx.wait_json(_DIALOG, lambda row: "import" in row.get("text", "").lower() or "Runtime ready" in row.get("chip", ""), timeout=25)
    ctx.shot("cb1-1-settings-imported", kind="window")
    blob = json.dumps(dialog)
    ctx.check(
        "settings-imported",
        "CBCS imported settings" in blob or "Settings were imported" in blob,
        "CBCS imported settings",
        blob[:500],
    )
    compared = ctx.eval(_COMPARE, wait=20)
    ctx.check("settings-sha", "SHA_MATCH" in compared, "product settings sha matches leftover", compared.strip()[-400:])
    ctx.check("history-not-copied", "SQLITE_UNCHANGED" in compared, "product history sqlite not copied", compared.strip()[-400:])
    ctx.note(planted[-300:])


def _history(ctx: Ctx) -> None:
    entry = faults.install(ctx, "history")
    ctx.launch(entry=entry, name="verify-cb1-history", wait_ready=70, allow_unready=True)
    dialog = ctx.wait_json(_DIALOG, lambda row: "history" in row.get("text", "").lower(), timeout=25)
    ctx.shot("cb1-2-history-off", kind="window")
    blob = json.dumps(dialog)
    ctx.check("history-off", "Local history is off" in blob, "Local history is off", blob[:500])
    ctx.check("history-errno", "Errno 13" in blob or "Permission denied" in blob, "Errno 13 on the history store", blob[:500])


def _fatal(ctx: Ctx) -> None:
    entry = faults.install(ctx, "fatal")
    ctx.launch(entry=entry, name="verify-cb1-fatal", wait_ready=50, allow_unready=True)
    dialog = ctx.wait_json(_DIALOG, lambda row: "could not start" in row.get("text", "").lower() or "could not start" in row.get("title", "").lower(), timeout=25)
    ctx.shot("cb1-3-could-not-start", kind="window")
    blob = json.dumps(dialog)
    ctx.check("could-not-start", "CBCS could not start" in blob, "CBCS could not start", blob[:600])
    for label in ("Copy Details", "Show Details", "Close"):
        ctx.check("button-" + label, label in blob, label, blob[:600])
    ctx.check("no-main-window", "MainWindow" not in blob, "no MainWindow", blob[:300])


_PLANT = r"""
import hashlib, json, os, shutil
home = "/home/default/verify-cb1"
leftover = home + "/.local/share/FreeCAD/choreboy_code_studio_state"
os.makedirs(leftover + "/history", exist_ok=True)
settings = {"theme": {"mode": "dark"}, "marker": "v0412-pref-FC10-DARK"}
path = leftover + "/settings.json"
text = json.dumps(settings, indent=2) + "\n"
open(path, "w", encoding="utf-8").write(text)
open(leftover + "/history/index.sqlite3", "wb").close()
state = "/home/default/FreeCAD/CBCS/state"
aside = "/home/default/verify-aside"
os.makedirs(aside, exist_ok=True)
product = state + "/settings.json"
if os.path.isfile(product):
    shutil.copy2(product, aside + "/settings.json.before-cb1")
    os.rename(product, product + ".verify-aside")
hist = state + "/history/index.sqlite3"
size = os.path.getsize(hist) if os.path.isfile(hist) else -1
open(aside + "/history-before.txt", "w").write(str(size))
digest = hashlib.sha256(open(path, "rb").read()).hexdigest()
line = "planted " + digest + " history " + str(size)
root = os.path.dirname(os.path.abspath(__file__))
open(os.path.join(root, "results", "report.txt"), "w").write(line + "\n")
print(line)
"""

_UNDO = r"""
import os, shutil
product = "/home/default/FreeCAD/CBCS/state/settings.json"
aside = "/home/default/verify-aside/settings.json.before-cb1"
if os.path.isfile(aside):
    shutil.copy2(aside, product)
    print("restored settings")
parked = product + ".verify-aside"
if os.path.isfile(parked):
    os.remove(parked)
    print("removed parked")
root = os.path.dirname(os.path.abspath(__file__))
open(os.path.join(root, "results", "report.txt"), "w").write("undone\n")
"""

_COMPARE = r"""
import hashlib, os
leftover = "/home/default/verify-cb1/.local/share/FreeCAD/choreboy_code_studio_state/settings.json"
product = "/home/default/FreeCAD/CBCS/state/settings.json"
left = hashlib.sha256(open(leftover, "rb").read()).hexdigest() if os.path.isfile(leftover) else ""
prod = hashlib.sha256(open(product, "rb").read()).hexdigest() if os.path.isfile(product) else ""
print("left", left)
print("prod", prod)
print("SHA_MATCH" if left and left == prod else "SHA_DIFFER")
before = "/home/default/verify-aside/history-before.txt"
hist = "/home/default/FreeCAD/CBCS/state/history/index.sqlite3"
now = os.path.getsize(hist) if os.path.isfile(hist) else -1
want = int(open(before).read().strip()) if os.path.isfile(before) else -2
print("history", now, want)
print("SQLITE_UNCHANGED" if now == want else "SQLITE_CHANGED")
"""

_DIALOG = r"""
import json
try:
    from PySide2.QtWidgets import QLabel, QPushButton
except ImportError:
    from PySide6.QtWidgets import QLabel, QPushButton
titles = []
texts = []
buttons = []
classes = []
for widget in app.topLevelWidgets():
    if not widget.isVisible():
        continue
    classes.append(type(widget).__name__)
    title = widget.windowTitle() or ""
    if title:
        titles.append(title)
    if widget.inherits("QDialog") or widget.inherits("QMessageBox"):
        for lab in widget.findChildren(QLabel):
            if (lab.text() or "").strip():
                texts.append(" ".join(lab.text().split()))
        for button in widget.findChildren(QPushButton):
            buttons.append(button.text())
chip = ""
for widget in app.allWidgets():
    if widget.objectName() == "shell.startupStatusLabel":
        chip = widget.text()
print("JSON:" + json.dumps({
    "title": " | ".join(titles),
    "text": "\n".join(texts),
    "buttons": buttons,
    "classes": classes,
    "chip": chip,
}))
"""
