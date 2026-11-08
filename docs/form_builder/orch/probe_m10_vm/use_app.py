"""Drive one installed app from its app_files tree.

Started under /opt/freecad/AppRun so the widgets are the installed window.
QTest cannot cross into a process this file did not create, so the probe
launches this file to use the installed copy.
"""

from __future__ import annotations

import json
import os
import sys

from PySide.QtGui import QGuiApplication
from PySide.QtTest import QTest
from PySide.QtWidgets import QApplication, QLineEdit, QPushButton, QWidget


def _qt():
    from PySide.QtCore import Qt

    return Qt


def _left():
    qt = _qt()
    return getattr(getattr(qt, "MouseButton", qt), "LeftButton")


def main() -> int:
    app_files = os.environ["M10_APP"]
    module_name = os.environ["M10_MODULE"]
    class_name = os.environ["M10_CLASS"]
    shots = os.environ["M10_SHOTS"]
    mode = os.environ.get("M10_MODE", "record")
    os.makedirs(shots, exist_ok=True)
    os.chdir(app_files)
    if app_files not in sys.path:
        sys.path.insert(0, app_files)
    os.environ.pop("QT_QPA_PLATFORM", None)
    qapp = QApplication.instance() or QApplication(sys.argv)
    module = __import__(module_name, fromlist=[class_name])
    window = getattr(module, class_name)()
    window.show()
    for _ in range(12):
        qapp.processEvents()
    notes = []
    _shot(qapp, shots, "01-open.png")
    names = sorted({child.objectName() for child in window.findChildren(QWidget) if child.objectName()})
    notes.append("widgets=" + ",".join(names[:80]))
    if mode == "desk":
        _desk(qapp, window, shots, notes)
    else:
        _record(qapp, window, shots, notes, mode)
    path = os.path.join(shots, "use.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"notes": notes, "class": class_name}, handle, indent=2)
        handle.write("\n")
    window.close()
    return 0


def _shot(qapp, shots, name) -> None:
    for _ in range(4):
        qapp.processEvents()
    screen = QGuiApplication.primaryScreen()
    if screen is None:
        return
    screen.grabWindow(0).save(os.path.join(shots, name))


def _record(qapp, window, shots, notes, mode) -> None:
    edits = [child for child in window.findChildren(QLineEdit) if child.isEnabled()]
    if edits:
        edits[0].setFocus()
        QTest.keyClicks(edits[0], "M10 Probe")
        qapp.processEvents()
        notes.append("typed into %s" % edits[0].objectName())
    _shot(qapp, shots, "02-typed.png")
    save = window.findChild(QPushButton, "saveButton")
    if save is not None:
        QTest.mouseClick(save, _left())
        for _ in range(10):
            qapp.processEvents()
        notes.append("clicked saveButton")
    _shot(qapp, shots, "03-saved.png")
    if mode == "list":
        nxt = window.findChild(QPushButton, "nextButton")
        if nxt is not None:
            QTest.mouseClick(nxt, _left())
            notes.append("clicked next")
        _shot(qapp, shots, "04-next.png")


def _desk(qapp, window, shots, notes) -> None:
    bar = window.menuBar() if hasattr(window, "menuBar") else None
    if bar is None:
        notes.append("no menu bar")
        return
    for action in bar.actions():
        menu = action.menu()
        if menu is None:
            continue
        menu.popup(window.mapToGlobal(window.rect().center()))
        for _ in range(4):
            qapp.processEvents()
        _shot(qapp, shots, "menu-%s.png" % (action.text().replace("&", "") or "item"))
        for child in menu.actions():
            if child.isSeparator():
                continue
            child.trigger()
            qapp.processEvents()
            notes.append("triggered %s" % child.text().replace("&", ""))
        menu.close()
    qt = _qt()
    key = getattr(getattr(qt, "Key", qt), "Key_N")
    mod = getattr(getattr(qt, "KeyboardModifier", qt), "ControlModifier")
    QTest.keyClick(window, key, mod)
    notes.append("sent Ctrl+N")
    _shot(qapp, shots, "05-shortcut.png")


if __name__ == "__main__":
    raise SystemExit(main())
