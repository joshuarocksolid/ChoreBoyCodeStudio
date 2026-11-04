"""PySide6 names on top of PySide2, for generated forms on the 1.0 image.

Install this only after app.qt has chosen PySide2. The Mac run has a real
PySide6 and must not import this module.
"""

from __future__ import annotations

import sys
import types


def install():
    if "PySide6" in sys.modules and not isinstance(sys.modules["PySide6"], types.ModuleType):
        return "present"
    existing = sys.modules.get("PySide6")
    if existing is not None and getattr(existing, "__file__", None):
        return "present"
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
    return "alias"


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
