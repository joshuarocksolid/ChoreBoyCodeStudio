"""PySide6 names on top of PySide2, for generated forms on the 1.0 image.

Install this only after app.qt has chosen PySide2. The Mac run has a real
PySide6 and must not import this module.
"""

from __future__ import annotations

import sys
import types


def install():
    """Return ``native`` when this process has real PySide6.

    The 1.0 image has no PySide6, so the alias is built from PySide2. A real
    PySide6 import must win before that alias is installed.
    """

    existing = sys.modules.get("PySide6")
    if existing is not None and getattr(existing, "__file__", None):
        return "native" if "PySide2" not in str(existing.__file__) else "present"
    try:
        import PySide6
    except ImportError:
        PySide6 = None
    if PySide6 is not None and getattr(PySide6, "__file__", None):
        return "native"
    import PySide2.QtCore
    import PySide2.QtGui
    import PySide2.QtWidgets

    widgets = PySide2.QtWidgets
    for name in ("QDialog", "QMessageBox", "QInputDialog", "QColorDialog", "QFileDialog", "QFontDialog"):
        cls = getattr(widgets, name, None)
        if cls is None or hasattr(cls, "exec"):
            continue
        exec_ = getattr(cls, "exec_", None)
        if exec_ is None:
            continue
        try:
            cls.exec = exec_
        except (AttributeError, TypeError):
            continue
    gui = types.ModuleType("PySide6.QtGui")
    gui.__dict__.update(PySide2.QtGui.__dict__)
    for name in ("QShortcut", "QAction", "QActionGroup"):
        value = getattr(widgets, name, None)
        if value is not None:
            setattr(gui, name, value)
    import importlib.machinery

    package = types.ModuleType("PySide6")
    package.__version__ = getattr(PySide2, "__version__", "") or PySide2.QtCore.qVersion()
    package.QtCore = PySide2.QtCore
    package.QtGui = gui
    package.QtWidgets = widgets
    package.__path__ = []
    package.__spec__ = importlib.machinery.ModuleSpec("PySide6", loader=None, is_package=True)
    for name in ("QApplication", "QDialog", "QMessageBox", "QInputDialog", "QMenu"):
        cls = getattr(widgets, name, None)
        if cls is None or hasattr(cls, "exec"):
            continue
        exec_ = getattr(cls, "exec_", None)
        if exec_ is None:
            continue
        try:
            cls.exec = exec_
        except (AttributeError, TypeError):
            continue
    sys.modules["PySide6"] = package
    sys.modules["PySide6.QtCore"] = PySide2.QtCore
    sys.modules["PySide6.QtGui"] = gui
    sys.modules["PySide6.QtWidgets"] = widgets
    if not any(isinstance(item, _Finder) for item in sys.meta_path):
        sys.meta_path.insert(0, _Finder())
    _install_qttest_shim()
    return "alias"


def _install_qttest_shim() -> None:
    """FreeCAD 1.0 ships PyQt5.QtTest and not PySide2.QtTest.

    The font row sends one Up key. This shim posts that press and release
    through the same QApplication path QTest uses, and only when the real
    module is absent.
    """

    if "PySide2.QtTest" in sys.modules:
        return
    try:
        import PySide2.QtTest  # noqa: F401
    except ImportError:
        pass
    else:
        return
    from PySide2.QtCore import QEvent, QPoint, Qt
    from PySide2.QtGui import QKeyEvent, QMouseEvent
    from PySide2.QtWidgets import QApplication

    def keyClick(widget, key, modifier=Qt.NoModifier, delay=-1):
        del delay
        text = ""
        key_code = key
        if isinstance(key, str):
            text = key
            key_code = ord(key.upper()) if len(key) == 1 else 0
        for kind in (QEvent.KeyPress, QEvent.KeyRelease):
            QApplication.sendEvent(widget, QKeyEvent(kind, key_code, modifier, text))

    def keyClicks(widget, sequence, modifier=Qt.NoModifier, delay=-1):
        for char in sequence:
            keyClick(widget, char, modifier, delay)

    def mousePress(widget, button, modifier=Qt.NoModifier, pos=None, delay=-1):
        del delay
        at = pos if pos is not None else QPoint(widget.width() // 2, widget.height() // 2)
        QApplication.sendEvent(
            widget,
            QMouseEvent(QEvent.MouseButtonPress, at, button, button, modifier),
        )

    def mouseMove(widget, pos=None, delay=-1):
        del delay
        at = pos if pos is not None else QPoint(0, 0)
        QApplication.sendEvent(
            widget,
            QMouseEvent(QEvent.MouseMove, at, Qt.NoButton, Qt.NoButton, Qt.NoModifier),
        )

    def mouseRelease(widget, button, modifier=Qt.NoModifier, pos=None, delay=-1):
        del delay
        at = pos if pos is not None else QPoint(widget.width() // 2, widget.height() // 2)
        QApplication.sendEvent(
            widget,
            QMouseEvent(QEvent.MouseButtonRelease, at, button, Qt.NoButton, modifier),
        )

    module = types.ModuleType("PySide2.QtTest")
    module.QTest = types.SimpleNamespace(
        keyClick=keyClick,
        keyClicks=keyClicks,
        mousePress=mousePress,
        mouseMove=mouseMove,
        mouseRelease=mouseRelease,
    )
    sys.modules["PySide2.QtTest"] = module


class _Finder:
    """Map any other PySide6 module onto the PySide2 module of the same name."""

    def find_spec(self, fullname, path, target=None):
        del path, target
        if fullname != "PySide6" and not fullname.startswith("PySide6."):
            return None
        import importlib.machinery

        return importlib.machinery.ModuleSpec(fullname, self)

    def create_module(self, spec):
        import importlib

        if spec.name in sys.modules:
            return sys.modules[spec.name]
        if spec.name == "PySide6.QtGui":
            return sys.modules.get("PySide6.QtGui")
        rest = spec.name.split(".", 1)[1] if "." in spec.name else ""
        if not rest:
            return None
        try:
            module = importlib.import_module("PySide2." + rest)
        except ImportError:
            return None
        sys.modules[spec.name] = module
        return module

    def exec_module(self, module):
        return None
