"""Preview child for the M8.R Try walk.

build_probe.sh installs this file as payload/run_form_preview.py. AppRun
launches it. Stdio is split before Qt. This process does not force PySide6.
app.qt selects PySide2, then the alias lets generated forms import PySide6.
"""

from __future__ import annotations

import os
import sys
import traceback

sys.dont_write_bytecode = True

import pyside6_alias  # noqa: E402

pyside6_alias.install()
os.environ["CBCS_QT_API"] = "pyside6"

from app.features.form_builder.qtside.preview.child.stdio import isolate_stdio  # noqa: E402

_STREAMS = isolate_stdio()

try:
    os.makedirs("/tmp/m8r_try_results", exist_ok=True)
    with open("/tmp/m8r_try_results/child_started.txt", "w", encoding="utf-8") as handle:
        handle.write("stdio ok\n")
except OSError:
    pass

try:
    from PySide2.QtWidgets import QMessageBox

    def _record_dialog(self, *args, **kwargs):
        del args, kwargs
        text = ""
        try:
            text = str(self.text())
        except Exception:
            text = ""
        _write("dialog.txt", text)
        return 0

    QMessageBox.exec = _record_dialog
    QMessageBox.exec_ = _record_dialog
except Exception:
    pass

import app.features.form_builder.qtside.preview.child.session as child_session  # noqa: E402

_ORIG_LOAD = child_session.ChildSession._load
_ORIG_PUSH = child_session.ChildSession.push_line
_WALKED = False


def _push(self, line):
    folder = _results_dir()
    if folder:
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, "push.txt"), "a", encoding="utf-8") as handle:
            handle.write(("none" if line is None else line[:160].replace("\n", " ")) + "\n")
    return _ORIG_PUSH(self, line)


child_session.ChildSession.push_line = _push


def _results_dir():
    raw = os.environ.get("CBCS_PROBE_RESULTS", "").strip()
    if raw:
        return raw
    return "/tmp/m8r_try_results"


def _write(name, text):
    folder = _results_dir()
    if folder is None:
        return
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, name)
    tmp = path + ".partial"
    with open(tmp, "w", encoding="utf-8") as handle:
        handle.write(text)
    os.replace(tmp, path)


def _load(self, message, try_message=None):
    _write("try_load.txt", "show=%s view=%s" % (getattr(try_message, "show_form", None), getattr(message, "view_id", "")))
    _ORIG_LOAD(self, message, try_message)
    _write("try_loaded.txt", "ok")
    try:
        _schedule(self, message, try_message)
    except Exception:
        _write("try_error.txt", traceback.format_exc())


def _schedule(self, message, try_message):
    if try_message is None or not getattr(try_message, "show_form", False):
        return
    from app.qt.QtCore import QTimer

    view_id = message.view_id
    attempts = {"n": 0}

    def go():
        attempts["n"] += 1
        ready = _walk(self, view_id)
        if ready or _WALKED:
            return
        if attempts["n"] < 30:
            QTimer.singleShot(100, go)
            return
        _write("try_error.txt", "the invoice form never showed a notes field")
        _write("try_walk.done", "error")

    QTimer.singleShot(0, go)


def _walk(session, view_id):
    global _WALKED
    if _WALKED or _results_dir() is None:
        return
    view = session._views.get(view_id)
    if view is None:
        return
    from app.qt.QtWidgets import QWidget

    shell = view.widget
    if shell.findChild(QWidget, "notes") is None:
        if not _WALKED:
            names = []
            for child in shell.findChildren(QWidget):
                name = child.objectName()
                if name:
                    names.append(name)
            _write("try_names.txt", "\n".join(names))
        return False
    _WALKED = True
    notes = {}
    error = ""
    try:
        notes = _drive(shell)
    except Exception:
        error = traceback.format_exc()
    try:
        _grab(shell, "07_try_banner.png")
        panel = shell.findChild(QWidget, "preview.whatRan")
        if panel is not None:
            _grab(panel, "08_what_ran.png")
    except Exception:
        error = (error + "\n" if error else "") + traceback.format_exc()
    _finish(notes, error)
    return True


def _drive(shell):
    from app.qt.QtWidgets import QApplication, QLabel, QWidget

    app = QApplication.instance()
    shell.show()
    shell.raise_()
    shell.resize(960, 640)
    if app is not None:
        app.processEvents()
    notes = shell.findChild(QWidget, "notes")
    if notes is None or not hasattr(notes, "setText"):
        raise RuntimeError("notes field missing")
    notes.setText("m8r try rollback")
    if app is not None:
        app.processEvents()
    ui = getattr(shell, "form_ui", None)
    if ui is None:
        ui = shell
    if not hasattr(ui, "cbcs_open"):
        raise RuntimeError("the form has no cbcs_open")
    ui.cbcs_open(1)
    if app is not None:
        app.processEvents()
    notes = shell.findChild(QWidget, "notes")
    notes.setText("m8r try rollback")
    saved = bool(ui.cbcs_save())
    if app is not None:
        import time

        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.05)
    banner = shell.findChild(QLabel, "preview.banner")
    banner_text = "" if banner is None else str(banner.text())
    ran = _what_ran(shell)
    return {"saved": saved, "banner": banner_text, "what_ran": ran}


def _what_ran(shell):
    from app.qt.QtWidgets import QWidget

    panel = shell.findChild(QWidget, "preview.whatRan")
    if panel is None:
        return ""
    listing = panel.findChild(QWidget, "preview.whatRan.list")
    if listing is not None and hasattr(listing, "topLevelItemCount"):
        lines = []
        count = listing.topLevelItemCount()
        for index in range(count):
            item = listing.topLevelItem(index)
            lines.append(str(item.text(1)))
        return "\n".join(lines)
    return ""


def _grab(widget, name):
    folder = _results_dir()
    if folder is None:
        return
    pixmap = widget.grab()
    if pixmap.width() > 800:
        height = int(round(pixmap.height() * (800.0 / float(pixmap.width()))))
        pixmap = pixmap.scaled(800, max(height, 1))
    path = os.path.join(folder, name)
    if not pixmap.save(path, "PNG"):
        raise RuntimeError("grab failed for %s" % name)


def _finish(notes, error):
    import json

    notes = dict(notes or {})
    notes["error"] = error
    _write("try_walk.json", json.dumps(notes, indent=2))
    _write("what_ran.txt", notes.get("what_ran") or "")
    _write("try_banner.txt", notes.get("banner") or "")
    if error:
        _write("try_error.txt", error)
    _write("try_walk.done", "ok" if not error else "error")


child_session.ChildSession._load = _load
child_session.ChildSession.push_line = _push


def _drive_from_file(path):
    """Run TryStart inside this AppRun process. The request pipe from a second
    AppRun stayed empty, so the frame is a file this process reads itself."""

    import faulthandler
    import time

    from app.qt.QtWidgets import QApplication

    hang = open("/tmp/m8r_try_results/hang.txt", "w", encoding="utf-8")
    faulthandler.dump_traceback_later(12, file=hang)

    text = open(path, encoding="utf-8").read()
    app = QApplication.instance() or QApplication(["cbcs-form-preview"])

    class _Writer:
        def send(self, message):
            return None

    session = child_session.ChildSession(_Writer(), app)
    # str.splitlines treats the frame prefix \x1e as a line break. The preview
    # decoder splits on newline only, so this walk does the same.
    for line in text.split("\n"):
        if line:
            session.push_line(line + "\n")
    session.drain()
    faulthandler.cancel_dump_traceback_later()
    deadline = time.monotonic() + 25
    done = os.path.join(_results_dir() or "/tmp/m8r_try_results", "try_walk.done")
    while time.monotonic() < deadline and not os.path.isfile(done):
        app.processEvents()
        time.sleep(0.05)
    if not os.path.isfile(done):
        _write("try_error.txt", "the walk did not finish")
        _write("try_walk.done", "error")


if __name__ == "__main__":
    frame = "/tmp/m8r_try_frame.txt"
    if os.path.isfile(frame):
        try:
            _drive_from_file(frame)
        except Exception:
            _write("try_error.txt", traceback.format_exc())
            _write("try_walk.done", "error")
        raise SystemExit(0)
    from app.features.form_builder.qtside.preview.child.main import main

    raise SystemExit(main(sys.argv[1:], _STREAMS))
