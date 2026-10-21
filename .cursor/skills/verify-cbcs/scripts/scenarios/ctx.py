"""What a scenario is allowed to do."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, List, Optional

from scenarios.adapter import Adapter
from scenarios.model import Check, Shot


class Ctx:
    def __init__(self, session: Any, adapter: Adapter, scenario: str) -> None:
        self.session = session
        self.adapter = adapter
        self.scenario = scenario
        self.artifacts = session.artifacts / scenario
        self.artifacts.mkdir(parents=True, exist_ok=True)
        self.checks: List[Check] = []
        self.shots: List[Shot] = []
        self.metrics = {}
        self.notes: List[str] = []
        self.sid = ""
        self.install_dir = session.install_dir

    def note(self, text: str) -> None:
        self.notes.append(text)

    def metric(self, key: str, value: Any) -> None:
        self.metrics[key] = value

    def check(self, name: str, ok: bool, expected: str, actual: str) -> None:
        self.checks.append(Check(name, bool(ok), str(expected), str(actual)))

    def launch(self, entry=None, home="/home/default", name=None, env=None, wait_ready=90, allow_unready=False) -> str:
        if self.sid:
            self.stop()
        entry = entry or (self.install_dir + "/run_editor.py")
        session_name = name or ("verify-" + self.scenario.replace("-", ""))
        argv = [
            "cbapp", "app-run", entry,
            "--package-root", str(Path(entry).parent),
            "--cwd", str(Path(entry).parent),
            "--name", session_name,
            "--env", "HOME=" + home,
            "--wait-ready", str(wait_ready),
            "--timeout", "240",
        ]
        for item in env or []:
            argv.extend(["--env", item])
        proc = self.adapter.call(argv, timeout=wait_ready + 60)
        text = (proc.stdout or "") + "\n" + (proc.stderr or "")
        (self.artifacts / "launch.log").write_text(text, encoding="utf-8")
        if proc.returncode != 0 and not allow_unready:
            raise RuntimeError("launch failed\n" + text[-2000:])
        self.sid = sid_from(proc.stdout or "")
        self.adapter.bind(self.sid, self.session.run_id, self.scenario, self.artifacts)
        return self.sid

    def stop(self) -> None:
        if not self.sid:
            return
        self.adapter.call(["cbapp", "stop", self.sid], timeout=30)
        self.sid = ""

    def eval(self, code: str, wait: int = 45) -> str:
        return self.adapter.eval(code, wait=wait)

    def eval_json(self, code: str, wait: int = 45):
        return self.adapter.eval_json(code, wait=wait)

    def shot(self, name: str, selector: Optional[str] = None, kind: str = "crop") -> str:
        path = self.adapter.grab(name, selector=selector, kind=kind)
        recorded = kind
        if selector and kind == "crop":
            recorded = "crop"
        elif kind == "desktop":
            recorded = "desktop"
        else:
            recorded = "window"
        self.shots.append(Shot(name, path, recorded))
        return path

    def wait_json(self, code: str, predicate, timeout: float = 30, pause: float = 0.4):
        deadline = time.time() + timeout
        last = {}
        while time.time() < deadline:
            last = self.eval_json(code, wait=20)
            if predicate(last):
                return last
            time.sleep(pause)
        return last

    def chip(self) -> str:
        payload = self.eval_json(CHIP_SNIPPET, wait=20)
        return str(payload.get("text") or "")

    def wait_chip(self, needle: str, timeout: float = 45) -> str:
        deadline = time.time() + timeout
        last = ""
        while time.time() < deadline:
            last = self.chip()
            if needle in last:
                return last
            time.sleep(0.5)
        return last

    def guest(self, code: str) -> str:
        return self.session.guest(code)


def sid_from(stdout: str) -> str:
    for line in stdout.splitlines():
        raw = line.strip()
        if raw and " " not in raw and "-" in raw:
            return raw
    raise RuntimeError("no session id in:\n" + stdout[-1500:])


CHIP_SNIPPET = r"""
import json
win = None
for widget in app.topLevelWidgets():
    if type(widget).__name__ == "MainWindow":
        win = widget
        break
if win is not None:
    win.statusBar().clearMessage()
text = ""
for widget in app.allWidgets():
    if widget.objectName() == "shell.startupStatusLabel":
        text = widget.text()
        break
print("JSON:" + json.dumps({"text": text}))
"""
