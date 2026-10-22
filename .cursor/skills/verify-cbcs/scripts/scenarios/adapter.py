"""cbapp ctl with one capability probe per run."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import time
from pathlib import Path
from typing import Callable, Optional, Sequence

from scenarios.caps import Caps, op_supported

Runner = Callable[[Sequence[str], int], "subprocess.CompletedProcess[str]"]

PROBE_SELECTOR = "__verify_cbcs_absent__"
INSTALL_DIR = "/home/default/FreeCAD/CBCS/choreboy_code_studio_v0.4.13"
EDITOR_ENTRY = INSTALL_DIR + "/run_editor.py"
GUEST_SHARE = "/mnt/cbprobe"


def default_runner(args: Sequence[str], timeout: int) -> "subprocess.CompletedProcess[str]":
    return subprocess.run(list(args), text=True, capture_output=True, timeout=timeout)


class Adapter:
    def __init__(self, run: Runner = default_runner, caps: Optional[Caps] = None) -> None:
        self._run = run
        self.caps = caps if caps is not None else Caps()
        self.sid = ""
        self._bridge_probed = caps is not None
        self.run_id = ""
        self.scenario = ""
        self.artifact_dir = Path(".")

    def bind(self, sid: str, run_id: str, scenario: str, artifact_dir: Path) -> None:
        self.sid = sid
        self.run_id = run_id
        self.scenario = scenario
        self.artifact_dir = artifact_dir
        if not self._bridge_probed and sid:
            self.probe_bridge()

    def probe_slot_snapshot(self) -> None:
        proc = self._run(["cb-slot", "checkpoint", "--help"], 20)
        text = (proc.stdout or "") + "\n" + (proc.stderr or "")
        self.caps.slot_snapshot = op_supported(text, "checkpoint")

    def probe_bridge(self) -> None:
        if not self.sid:
            return
        probes = {
            "grab": ["cbapp", "ctl", self.sid, "grab", PROBE_SELECTOR],
            "state": ["cbapp", "ctl", self.sid, "state"],
            "drag": ["cbapp", "ctl", self.sid, "drag", PROBE_SELECTOR, PROBE_SELECTOR],
            "dblclick": ["cbapp", "ctl", self.sid, "dblclick", PROBE_SELECTOR],
            "hover": ["cbapp", "ctl", self.sid, "hover", PROBE_SELECTOR],
        }
        for name, argv in probes.items():
            proc = self._run(argv, 25)
            text = (proc.stdout or "") + "\n" + (proc.stderr or "")
            setattr(self.caps, name, op_supported(text, name))
        self._bridge_probed = True

    def call(self, args: Sequence[str], timeout: int = 60) -> "subprocess.CompletedProcess[str]":
        return self._run(list(args), timeout)

    def eval(self, code: str, wait: int = 45) -> str:
        proc = self.call(
            ["cbapp", "ctl", self.sid, "eval", "-", code, "--wait", str(wait)],
            timeout=wait + 25,
        )
        raw = (proc.stdout or "") + "\n" + (proc.stderr or "")
        if proc.returncode != 0:
            raise RuntimeError(raw[-2500:])
        return eval_stdout(proc.stdout or "")

    def eval_json(self, code: str, wait: int = 45) -> dict:
        text = self.eval(code, wait=wait)
        for line in reversed(text.splitlines()):
            if line.startswith("JSON:"):
                return json.loads(line[5:])
        raise RuntimeError("no JSON: in eval stdout:\n" + text[-1500:])

    def click(self, selector: str) -> None:
        self._ok(["cbapp", "ctl", self.sid, "click", selector], 30)

    def oskey(self, text: Optional[str] = None, keyname: Optional[str] = None) -> None:
        if keyname:
            argv = ["cbapp", "ctl", self.sid, "oskey", "--keyname", keyname]
        else:
            argv = ["cbapp", "ctl", self.sid, "oskey", text or ""]
        self._ok(argv, 20)

    def ctrl_space(self) -> None:
        domain = os.environ.get("CB_DOMAIN") or os.environ.get("CBAPP_DOMAIN") or ""
        if not domain:
            raise RuntimeError("CB_DOMAIN is unset; cannot send Ctrl+Space")
        self._ok(["cb-virsh", "send-key", domain, "KEY_LEFTCTRL", "KEY_SPACE"], 20)

    def grab(self, name: str, selector: Optional[str] = None, kind: str = "crop") -> str:
        dest = self.artifact_dir / "{}.png".format(name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if self.caps.grab and selector:
            proc = self.call(["cbapp", "ctl", self.sid, "grab", selector, "--out", name], timeout=40)
            shot = shot_path((proc.stdout or "") + "\n" + (proc.stderr or ""))
            if shot and Path(shot).is_file():
                if Path(shot).resolve() != dest.resolve():
                    dest.write_bytes(Path(shot).read_bytes())
                return str(dest)
        if kind == "desktop":
            return self.desktop(name)
        if kind == "window" or not selector:
            return self.window_shot(name)
        return self._grab_eval(name, selector, dest)

    def window_shot(self, name: str) -> str:
        dest = self.artifact_dir / "{}.png".format(name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        proc = self.call(["cbapp", "ctl", self.sid, "screenshot", "--target", "app"], timeout=40)
        shot = shot_path((proc.stdout or "") + "\n" + (proc.stderr or ""))
        if shot and Path(shot).is_file():
            if Path(shot).resolve() != dest.resolve():
                dest.write_bytes(Path(shot).read_bytes())
            return str(dest)
        if proc.returncode != 0:
            raise RuntimeError((proc.stdout or "")[-1500:] + (proc.stderr or "")[-800:])
        return str(dest if dest.is_file() else (shot or dest))

    def desktop(self, name: str) -> str:
        dest = self.artifact_dir / "{}.png".format(name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        proc = self.call(["cbapp", "desktop-shot", "--out", str(dest)], timeout=40)
        if dest.is_file():
            return str(dest)
        shot = shot_path((proc.stdout or "") + "\n" + (proc.stderr or ""))
        if shot and Path(shot).is_file():
            return shot
        raise RuntimeError("desktop shot missing")

    def state(self, text_formats: Optional[Sequence[str]] = None, max_lines: Optional[int] = None) -> dict:
        if self.caps.state:
            argv = ["cbapp", "ctl", self.sid, "state"]
            for selector in text_formats or []:
                argv.extend(["--text-formats", selector])
            if max_lines:
                argv.extend(["--max-lines", str(int(max_lines))])
            proc = self.call(argv, timeout=30)
            payload = _load_json_blob((proc.stdout or "").strip())
            if proc.returncode == 0 and isinstance(payload, dict):
                return unwrap_state(payload)
        return self.eval_json(STATE_SNIPPET, wait=30)

    def drag(self, x1: int, y1: int, x2: int, y2: int, steps: int = 20) -> None:
        if self.caps.drag:
            proc = self.call(
                [
                    "cbapp", "ctl", self.sid, "drag",
                    "{},{}".format(int(x1), int(y1)),
                    "{},{}".format(int(x2), int(y2)),
                    "--steps", str(steps), "--os",
                ],
                timeout=40,
            )
            if proc.returncode == 0:
                return
        self._stepped_xtest(int(x1), int(y1), int(x2), int(y2), steps)

    def dblclick(self, selector: str) -> None:
        if self.caps.dblclick:
            proc = self.call(["cbapp", "ctl", self.sid, "dblclick", selector], timeout=20)
            if proc.returncode == 0:
                return
        self._ok(["cbapp", "ctl", self.sid, "dclick", selector], 20)

    def hover(self, x: int, y: int, ms: int = 600) -> None:
        if self.caps.hover:
            proc = self.call(
                ["cbapp", "ctl", self.sid, "hover", "{},{}".format(int(x), int(y)), "--ms", str(ms)],
                timeout=20,
            )
            if proc.returncode == 0:
                return
        self.call(
            ["cbapp", "ctl", self.sid, "mouse", "--action", "move", "--x", str(int(x)), "--y", str(int(y))],
            timeout=20,
        )
        time.sleep(max(ms, 0) / 1000.0)

    def _stepped_xtest(self, x1: int, y1: int, x2: int, y2: int, steps: int) -> None:
        self.call(
            ["cbapp", "ctl", self.sid, "mouse", "--action", "press", "--button", "1", "--x", str(x1), "--y", str(y1)],
            timeout=15,
        )
        count = max(int(steps), 1)
        for index in range(1, count + 1):
            x = int(x1 + (x2 - x1) * index / count)
            y = int(y1 + (y2 - y1) * index / count)
            self.call(
                ["cbapp", "ctl", self.sid, "mouse", "--action", "move", "--x", str(x), "--y", str(y)],
                timeout=15,
            )
        self.call(
            ["cbapp", "ctl", self.sid, "mouse", "--action", "release", "--button", "1", "--x", str(x2), "--y", str(y2)],
            timeout=15,
        )

    def _grab_eval(self, name: str, selector: str, dest: Path) -> str:
        rel = "verify-cbcs/{}/{}.png".format(self.run_id, name)
        guest = GUEST_SHARE + "/" + rel
        self._mkdir_share(os.path.dirname(rel))
        code = GRAB_SNIPPET.format(selector=json.dumps(selector), path=json.dumps(guest))
        self.eval(code, wait=30)
        pulled = self._scp(share_host(rel), dest)
        if not pulled.is_file() or pulled.stat().st_size < 32:
            raise RuntimeError("crop missing after grab: " + str(dest))
        return str(dest)

    def _mkdir_share(self, rel_dir: str) -> None:
        remote = share_host(rel_dir)
        proc = self.call(["ssh", "-o", "BatchMode=yes", "debian", "mkdir -p " + shlex.quote(remote)], timeout=20)
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr or proc.stdout or "mkdir failed")

    def _scp(self, remote_path: str, dest: Path) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        proc = self.call(["scp", "-o", "BatchMode=yes", "debian:" + remote_path, str(dest)], timeout=40)
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr or proc.stdout or "scp failed")
        return dest

    def _ok(self, argv: list, timeout: int) -> None:
        proc = self.call(argv, timeout=timeout)
        if proc.returncode != 0:
            raise RuntimeError(((proc.stdout or "") + (proc.stderr or ""))[-2000:])


def share_host(rel: str) -> str:
    host_root = os.environ.get("CB_SHARE") or os.environ.get("CBPROBE_SHARE_HOST") or ""
    if not host_root:
        raise RuntimeError("CB_SHARE is unset")
    return host_root.rstrip("/") + "/" + rel.strip("/")


def unwrap_state(payload: object) -> dict:
    """Return the state object from a ctl envelope or from the object itself."""
    if not isinstance(payload, dict):
        return {}
    keys = ("windows", "dialogs", "tabs", "text_formats", "status_bar")
    result = payload.get("result")
    if isinstance(result, dict) and any(key in result for key in keys):
        return result
    if any(key in payload for key in keys):
        return payload
    if isinstance(result, dict):
        return result
    return payload


def shot_path(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("SHOT:"):
            return line.split("SHOT:", 1)[1].strip()
    return ""


def eval_stdout(stdout: str) -> str:
    text = (stdout or "").strip()
    if not text:
        return ""
    payload = _load_json_blob(text)
    if payload is None:
        return text
    result = payload.get("result") if isinstance(payload, dict) else None
    if isinstance(result, dict):
        if result.get("ok") is False:
            raise RuntimeError(text[-2000:])
        return str(result.get("stdout") or "")
    if isinstance(payload, dict) and payload.get("ok") is False:
        raise RuntimeError(text[-2000:])
    return text


def _load_json_blob(text: str):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None


GRAB_SNIPPET = """
selector = {selector}
path = {path}
widget = find(selector)
if widget is None:
    name = selector[1:] if selector.startswith("#") else selector
    matches = [w for w in app.allWidgets() if w.objectName() == name and w.isVisible()]
    widget = matches[0] if matches else None
if widget is None:
    raise RuntimeError("grab missed " + selector)
widget.grab().save(path)
print("SAVED", path, widget.width(), widget.height())
"""

STATE_SNIPPET = r"""
import json
try:
    from PySide2.QtWidgets import QLabel, QPushButton, QStatusBar
except ImportError:
    from PySide6.QtWidgets import QLabel, QPushButton, QStatusBar
windows = []
dialogs = []
for widget in app.topLevelWidgets():
    if not widget.isVisible():
        continue
    windows.append({
        "class": type(widget).__name__,
        "objectName": widget.objectName(),
        "title": widget.windowTitle(),
        "geometry": [widget.x(), widget.y(), widget.width(), widget.height()],
    })
    if widget.inherits("QDialog") or widget.inherits("QMessageBox"):
        labels = []
        for lab in widget.findChildren(QLabel):
            text = (lab.text() or "").strip()
            if text:
                labels.append(text)
        buttons = []
        for button in widget.findChildren(QPushButton):
            buttons.append({"text": button.text(), "default": bool(button.isDefault())})
        dialogs.append({
            "class": type(widget).__name__,
            "objectName": widget.objectName(),
            "title": widget.windowTitle(),
            "modal": bool(widget.isModal()),
            "labels": labels,
            "buttons": buttons,
        })
status_bar = []
for bar in app.allWidgets():
    if not isinstance(bar, QStatusBar) or not bar.isVisible():
        continue
    children = []
    for child in list(bar.findChildren(QLabel)) + list(bar.findChildren(QPushButton)):
        children.append({
            "objectName": child.objectName(),
            "text": child.text(),
            "visible": child.isVisible(),
        })
    status_bar.append({"currentMessage": bar.currentMessage(), "children": children})
focus = app.focusWidget()
print("JSON:" + json.dumps({
    "windows": windows,
    "dialogs": dialogs,
    "status_bar": status_bar,
    "focus": None if focus is None else {"objectName": focus.objectName(), "class": type(focus).__name__},
}))
"""
