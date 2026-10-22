"""Drive one QWizard page per eval. Stops on the done or failure title."""

from __future__ import annotations

import json
import time
from typing import Any, Callable, Dict, List


def drive(eval_fn: Callable[..., str], mode: str = "install", timeout: float = 100) -> Dict[str, Any]:
    """Click Next, Install, Replace, or Uninstall until the page title is final."""
    code = _STEP.replace("__MODE__", mode)
    deadline = time.time() + timeout
    last: Dict[str, Any] = {"title": "", "action": "wait"}
    log: List[Dict[str, Any]] = []
    while time.time() < deadline:
        raw = eval_fn(code, wait=25)
        last = _parse(raw)
        log.append(last)
        if last.get("action") == "done":
            return _finish(last, log)
        time.sleep(0.45)
    last["action"] = "timeout"
    return _finish(last, log)


def _finish(last: Dict[str, Any], log: List[Dict[str, Any]]) -> Dict[str, Any]:
    steps = []
    for step in log:
        steps.append({key: value for key, value in step.items() if key != "log"})
    done = {key: value for key, value in last.items() if key != "log"}
    done["log"] = steps
    return done


def _parse(raw: str) -> Dict[str, Any]:
    for line in reversed((raw or "").splitlines()):
        text = line.strip()
        if text.startswith("{") and text.endswith("}"):
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                return payload
    return {"title": "", "action": "unparsed", "raw": (raw or "")[-300:]}


_STEP = r"""
import json

def _qt():
    for name in ("PySide2", "PySide6"):
        try:
            mod = __import__(name + ".QtWidgets", fromlist=["QtWidgets"])
        except ImportError:
            continue
        if mod.QApplication.instance() is not None:
            return mod
    return None

def _label(widget):
    return (widget.text() or "").replace("&", "").strip()

QtWidgets = _qt()
payload = {"title": "", "action": "wait"}
if QtWidgets is not None:
    QApplication = QtWidgets.QApplication
    QWizard = QtWidgets.QWizard
    QPushButton = QtWidgets.QPushButton
    QRadioButton = QtWidgets.QRadioButton
    QMessageBox = QtWidgets.QMessageBox
    MODE = "__MODE__"
    app = QApplication.instance()
    boxes = [w for w in app.topLevelWidgets() if isinstance(w, QMessageBox) and w.isVisible()]
    wizards = [w for w in app.topLevelWidgets() if isinstance(w, QWizard) and w.isVisible()]
    if boxes:
        box = boxes[-1]
        yes = [b for b in box.findChildren(QPushButton) if _label(b).lower() in ("yes", "ok", "continue")]
        if yes:
            yes[0].click()
            app.processEvents()
        payload = {"title": box.windowTitle(), "action": "message"}
    elif wizards:
        wiz = wizards[-1]
        page = wiz.currentPage()
        title = page.title() if page is not None else ""
        low = title.lower()
        final = (
            "installation failed" in low
            or "uninstall failed" in low
            or "is installed" in low
            or "was uninstalled" in low
            or low == "installation complete"
        )
        if final:
            payload = {"title": title, "action": "done"}
        else:
            visible = []
            for button in wiz.findChildren(QPushButton):
                if button.isVisible() and button.isEnabled():
                    visible.append(button)
            clicked = ""
            if MODE == "uninstall" and "already installed" in low and page is not None:
                for radio in page.findChildren(QRadioButton):
                    if _label(radio).lower().startswith("uninstall"):
                        radio.setChecked(True)
                        radio.click()
                        app.processEvents()
                        break
                visible = [b for b in wiz.findChildren(QPushButton) if b.isVisible() and b.isEnabled()]
                for button in visible:
                    if _label(button).lower().startswith("uninstall"):
                        button.click()
                        app.processEvents()
                        clicked = _label(button)
                        break
            else:
                want = ("install", "replace", "reinstall", "next", "finish")
                if MODE == "uninstall":
                    want = ("uninstall", "next", "finish")
                for key in want:
                    for button in visible:
                        text = _label(button).lower()
                        if text == key or text.startswith(key):
                            button.click()
                            app.processEvents()
                            clicked = _label(button)
                            break
                    if clicked:
                        break
            payload = {"title": title, "action": "click" if clicked else "none", "button": clicked}
print(json.dumps(payload))
"""
