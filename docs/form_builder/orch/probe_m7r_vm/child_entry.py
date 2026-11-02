"""Preview child entry for the M7.R probe.

build_probe.sh installs this file as payload/run_form_preview.py. AppRun
launches that path. Stdio is split before Qt, the same way the product
entry does. After a real TryStart load of the invoice form, this file
drives the widgets and grabs the window. It does not change product code.
"""

from __future__ import annotations

import os
import sys
import traceback

sys.dont_write_bytecode = True
os.environ["CBCS_QT_API"] = "pyside6"

from app.features.form_builder.qtside.preview.child.stdio import isolate_stdio

_STREAMS = isolate_stdio()

import app.features.form_builder.qtside.preview.child.session as child_session

_ORIG_LOAD = child_session.ChildSession._load
_WALKED = False


def _results_dir():
    raw = os.environ.get("CBCS_PROBE_RESULTS", "").strip()
    if not raw:
        return None
    return raw


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
    _ORIG_LOAD(self, message, try_message)
    try:
        _schedule(self, message, try_message)
    except Exception:
        _write("try_error.txt", traceback.format_exc())


def _schedule(self, message, try_message):
    if try_message is None or not getattr(try_message, "show_form", False):
        return
    source = getattr(try_message, "module_source", None) or ""
    if "discountCheck" not in source:
        return
    from app.qt.QtCore import QTimer

    view_id = message.view_id

    def go():
        _walk(self, view_id)

    QTimer.singleShot(0, go)


def _walk(session, view_id):
    global _WALKED
    if _WALKED:
        return
    if _results_dir() is None:
        return
    view = session._views.get(view_id)
    if view is None:
        return
    from app.qt.QtWidgets import QWidget

    shell = view.widget
    if shell.findChild(QWidget, "discountCheck") is None:
        return
    _WALKED = True
    notes = {}
    error = ""
    try:
        notes = _drive(shell)
    except Exception:
        error = traceback.format_exc()
    try:
        _grab(shell)
    except Exception:
        error = (error + "\n" if error else "") + traceback.format_exc()
    _finish(notes, error)


def _drive(shell):
    from app.qt.QtWidgets import QApplication

    app = QApplication.instance()
    shell.show()
    shell.raise_()
    shell.resize(1100, 720)
    if app is not None:
        app.processEvents()
    discount = _need(shell, "discountEdit")
    check = _need(shell, "discountCheck")
    qty = _need(shell, "qtySpin")
    price = _need(shell, "priceSpin")
    total = _need(shell, "lineTotalLabel")
    email = _need(shell, "emailEdit")
    save = _need(shell, "saveButton")
    before_enabled = bool(discount.isEnabled())
    discount_how = _tick(check)
    _pump(app, 4)
    after_enabled = bool(discount.isEnabled())
    total_before = _text(total)
    qty_how = _type_number(qty, "2")
    price_how = _type_number(price, "3")
    _pump(app, 6)
    total_after = _text(total)
    if hasattr(email, "clear"):
        email.clear()
    finished = getattr(email, "editingFinished", None)
    if finished is not None and hasattr(finished, "emit"):
        finished.emit()
    _pump(app, 4)
    visible_mid = _visible(shell)
    if hasattr(save, "click"):
        save.click()
    _pump(app, 8)
    visible = visible_mid + "\n" + _visible(shell)
    ran = _what_ran(shell)
    email_seen = "Email is required" in visible or "Email is required" in ran
    stopped = "Check all fields" in ran and "stopped" in ran
    total_ok = total_after != total_before and "6" in total_after
    checks = {
        "discount": (not before_enabled) and after_enabled,
        "total": total_ok,
        "email": email_seen,
        "save": stopped,
    }
    return {
        "discount_before": before_enabled,
        "discount_after": after_enabled,
        "discount_how": discount_how,
        "qty_how": qty_how,
        "price_how": price_how,
        "qty": _value(qty),
        "price": _value(price),
        "total_before": total_before,
        "total_after": total_after,
        "email_seen": email_seen,
        "what_ran": ran,
        "visible": visible[-4000:],
        "checks": checks,
        "what_ran_window": _separate_what_ran(shell),
    }


def _need(shell, name):
    from app.qt.QtWidgets import QWidget

    found = shell.findChild(QWidget, name)
    if found is None:
        raise RuntimeError("preview has no %s" % name)
    return found


def _pump(app, times):
    if app is None:
        return
    for _ in range(times):
        app.processEvents()


def _tick(check):
    from app.qt.QtCore import Qt
    from app.qt.QtTest import QTest
    from app.qt.QtWidgets import QApplication

    button = getattr(getattr(Qt, "MouseButton", Qt), "LeftButton")
    try:
        QTest.mouseClick(check, button)
    except Exception:
        pass
    app = QApplication.instance()
    if app is not None:
        app.processEvents()
    if hasattr(check, "isChecked") and check.isChecked():
        return "mouseClick"
    if hasattr(check, "setChecked"):
        check.setChecked(True)
        return "setChecked"
    raise RuntimeError("could not tick %s" % check.objectName())


def _type_number(widget, digits):
    from app.qt.QtCore import Qt
    from app.qt.QtTest import QTest
    from app.qt.QtWidgets import QApplication

    app = QApplication.instance()
    target = widget.lineEdit() if hasattr(widget, "lineEdit") and widget.lineEdit() is not None else widget
    try:
        target.setFocus()
        if hasattr(target, "selectAll"):
            target.selectAll()
        if app is not None:
            app.processEvents()
        for digit in digits:
            key = getattr(getattr(Qt, "Key", Qt), "Key_%s" % digit)
            QTest.keyClick(target, key)
        if app is not None:
            app.processEvents()
        if _value(widget) == digits or str(_value(widget)).startswith(digits):
            return "keyClick"
    except Exception:
        pass
    if hasattr(widget, "setValue"):
        widget.setValue(int(digits))
        return "setValue"
    raise RuntimeError("could not set %s" % widget.objectName())


def _value(widget):
    if hasattr(widget, "value"):
        try:
            return widget.value()
        except Exception:
            return None
    return _text(widget)


def _text(widget):
    reader = getattr(widget, "text", None)
    if not callable(reader):
        return ""
    try:
        value = reader()
    except Exception:
        return ""
    return value if isinstance(value, str) else str(value)


def _visible(shell):
    from app.qt.QtWidgets import QWidget

    lines = []
    for item in shell.findChildren(QWidget):
        name = item.objectName() or ""
        for attr in ("text", "toolTip", "placeholderText"):
            reader = getattr(item, attr, None)
            if not callable(reader):
                continue
            try:
                value = reader()
            except Exception:
                continue
            if isinstance(value, str) and value.strip():
                lines.append("%s %s %s" % (name, attr, value))
    return "\n".join(lines)


def _what_ran(shell):
    from app.qt.QtWidgets import QTreeWidget

    tree = shell.findChild(QTreeWidget, "preview.whatRan.list")
    if tree is None:
        return ""
    lines = []
    for index in range(tree.topLevelItemCount()):
        item = tree.topLevelItem(index)
        lines.append("\t".join(item.text(column) for column in range(item.columnCount())))
        for child_index in range(item.childCount()):
            child = item.child(child_index)
            lines.append("  " + "\t".join(child.text(column) for column in range(child.columnCount())))
    return "\n".join(lines) + ("\n" if lines else "")


def _separate_what_ran(shell):
    from app.qt.QtWidgets import QWidget

    panel = shell.findChild(QWidget, "preview.whatRan")
    if panel is None:
        return False
    return panel.window() is not shell.window()


def _grab(shell):
    from app.qt.QtWidgets import QWidget

    folder = _results_dir()
    if folder is None:
        return
    os.makedirs(folder, exist_ok=True)
    shell.show()
    shell.resize(1100, 720)
    from app.qt.QtWidgets import QApplication, QSplitter

    app = QApplication.instance()
    splitter = shell.findChild(QSplitter, "preview.splitter")
    if splitter is not None:
        splitter.setSizes([520, 520])
    if app is not None:
        app.processEvents()
    pixmap = shell.grab()
    target = os.path.join(folder, "try_mode.png")
    if not pixmap.save(target, "PNG"):
        raise RuntimeError("QWidget.grab() could not save try_mode.png")
    panel = shell.findChild(QWidget, "preview.whatRan")
    if panel is not None and panel.window() is not shell.window():
        shot = panel.grab()
        extra = os.path.join(folder, "try_mode_what_ran.png")
        if not shot.save(extra, "PNG"):
            raise RuntimeError("QWidget.grab() could not save the What ran window")


def _finish(notes, error):
    import json

    ran = ""
    if isinstance(notes, dict):
        ran = notes.get("what_ran") or ""
    _write("what_ran.txt", ran if isinstance(ran, str) else "")
    checks = notes.get("checks") if isinstance(notes, dict) else None
    failed = []
    if isinstance(checks, dict):
        for name, ok in checks.items():
            if not ok:
                failed.append(name)
    body = ""
    if error:
        body = error
    if failed:
        body = (body + "\n" if body else "") + "try walk checks failed: %s\n%s\n" % (
            ", ".join(failed),
            json.dumps(notes, indent=2, default=str),
        )
    if body:
        _write("try_error.txt", body)
    _write("try_walk.json", json.dumps(notes, indent=2, default=str) + "\n")
    _write("try_walk.done", "done\n")


child_session.ChildSession._load = _load

from app.features.form_builder.qtside.preview.child.main import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:], _STREAMS))
