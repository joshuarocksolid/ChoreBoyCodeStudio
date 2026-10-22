"""Project-module hygiene and promoted-class stubs for the preview child.

The editor never imports this. A failed promoted class becomes a stub that
subclasses ``extends`` and is marked ``_cbcs_stub`` so the form still loads.
"""

from __future__ import annotations

import importlib
import os
import sys
import types
from typing import Dict, List, Optional, Sequence, Tuple

from app.features.form_builder.engine.ipc.protocol import PromotedClass
from app.qt import QtCore, QtGui, QtWidgets


def resolve_qt_class(extends: str) -> type:
    """Return the Qt class named ``extends``, or ``QWidget`` when it is unknown."""
    for module in (QtWidgets, QtGui, QtCore):
        candidate = getattr(module, extends, None)
        if isinstance(candidate, type):
            return candidate
    return QtWidgets.QWidget


def make_stub(class_name: str, extends: str) -> type:
    """A stand-in widget. ``_cbcs_stub`` tells the host the real class did not load."""
    base = resolve_qt_class(extends)

    def init(self: QtWidgets.QWidget, parent: Optional[QtWidgets.QWidget] = None) -> None:
        base.__init__(self, parent)

    stub = type(class_name, (base,), {"__init__": init, "_cbcs_stub": True})
    return stub


def purge_project_modules(root: Optional[str]) -> List[str]:
    """Drop ``sys.modules`` entries whose file lives under ``root``."""
    if not root:
        return []
    real = os.path.realpath(root)
    prefix = real + os.sep
    dropped: List[str] = []
    for name, module in list(sys.modules.items()):
        filename = getattr(module, "__file__", None)
        if not isinstance(filename, str):
            continue
        path = os.path.realpath(filename)
        if path == real or path.startswith(prefix):
            dropped.append(name)
            _forget_bytecode(path)
    for name in dropped:
        sys.modules.pop(name, None)
    importlib.invalidate_caches()
    return dropped


def _forget_bytecode(path: str) -> None:
    """Drop a just-imported project's pyc so the next load reads the source.

    A save in the same second leaves the pyc timestamp looking fresh. Preview
    would keep the old module body after ``sys.modules`` was cleared.
    """
    if path.endswith(".pyc"):
        _remove_file(path)
        return
    cache = os.path.join(os.path.dirname(path), "__pycache__")
    if not os.path.isdir(cache):
        return
    stem = os.path.splitext(os.path.basename(path))[0]
    prefix = stem + "."
    try:
        names = os.listdir(cache)
    except OSError:
        return
    for name in names:
        if name.startswith(prefix) and name.endswith(".pyc"):
            _remove_file(os.path.join(cache, name))


def _remove_file(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        return


def replace_sys_path(previous: Sequence[str], entries: Sequence[str]) -> List[str]:
    """Remove the previous view's entries and prepend ``entries`` (first stays first)."""
    for entry in previous:
        while entry in sys.path:
            sys.path.remove(entry)
    for entry in reversed(tuple(entries)):
        while entry in sys.path:
            sys.path.remove(entry)
        sys.path.insert(0, entry)
    return list(entries)


def install_resource_module(name: str, source: str) -> None:
    """Register an in-memory ``*_rc.py`` so the form can import it."""
    parts = name.split(".")
    for index in range(1, len(parts)):
        parent_name = ".".join(parts[:index])
        parent = sys.modules.get(parent_name)
        if parent is None:
            parent = types.ModuleType(parent_name)
            parent.__file__ = "<resource:%s>" % parent_name
            parent.__path__ = []
            sys.modules[parent_name] = parent
    module = types.ModuleType(name)
    module.__file__ = "<resource:%s>" % name
    exec(compile(source, module.__file__, "exec"), module.__dict__)
    sys.modules[name] = module
    if len(parts) > 1:
        setattr(sys.modules[".".join(parts[:-1])], parts[-1], module)


def install_promoted(spec: PromotedClass) -> Tuple[type, Optional[BaseException]]:
    """Import ``spec``. On failure install a stub and return the exception."""
    try:
        module = importlib.import_module(spec.header_module)
        cls = getattr(module, spec.class_name)
        if not isinstance(cls, type):
            raise TypeError("%s is not a class" % spec.class_name)
        return cls, None
    except Exception as exc:
        stub = make_stub(spec.class_name, spec.extends)
        _place(spec.header_module, spec.class_name, stub)
        return stub, exc


def _place(module_name: str, class_name: str, cls: type) -> None:
    module = sys.modules.get(module_name)
    if module is None:
        module = types.ModuleType(module_name)
        module.__file__ = "<stub:%s>" % module_name
        sys.modules[module_name] = module
    setattr(module, class_name, cls)


def snapshot_texts(widget: QtWidgets.QWidget) -> Dict[str, str]:
    saved: Dict[str, str] = {}
    for item in _walk(widget):
        name = item.objectName()
        reader = getattr(item, "text", None)
        if not name or not callable(reader):
            continue
        try:
            value = reader()
        except Exception:
            continue
        if isinstance(value, str):
            saved[name] = value
    return saved


def restore_texts(widget: QtWidgets.QWidget, saved: Dict[str, str]) -> None:
    for item in _walk(widget):
        name = item.objectName()
        if name not in saved:
            continue
        setter = getattr(item, "setText", None)
        if callable(setter):
            setter(saved[name])


def describe(widget: QtWidgets.QWidget) -> Tuple[Tuple[str, ...], Dict[str, str], Dict[str, str], Tuple[str, ...]]:
    """Names, text properties, immediate base class, and stub object names."""
    names: List[str] = []
    texts: Dict[str, str] = {}
    bases: Dict[str, str] = {}
    stubs: List[str] = []
    for item in _walk(widget):
        name = item.objectName()
        if not name:
            continue
        names.append(name)
        parent_types = type(item).__bases__
        bases[name] = parent_types[0].__name__ if parent_types else type(item).__name__
        if getattr(type(item), "_cbcs_stub", False) or getattr(item, "_cbcs_stub", False):
            stubs.append(name)
        reader = getattr(item, "text", None)
        if not callable(reader):
            continue
        try:
            value = reader()
        except Exception:
            continue
        if isinstance(value, str):
            texts[name] = value
    return tuple(names), texts, bases, tuple(stubs)


def named_widgets(widget: QtWidgets.QWidget, object_name: str) -> List[QtWidgets.QWidget]:
    found = [item for item in _walk(widget) if item.objectName() == object_name]
    return found


def _walk(widget: QtWidgets.QWidget) -> List[QtWidgets.QWidget]:
    found = [widget]
    found.extend(widget.findChildren(QtWidgets.QWidget))
    return found
