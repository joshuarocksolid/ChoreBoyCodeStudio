"""Project-module hygiene and your own classes for the preview child.

The editor never imports this (CONTRACTS section 10.4). Each own class is
imported and built once on a throwaway hidden parent before ``setupUi``
(UX-CUST-008). If the import or that build raises, or runs past its time
limit, the class becomes a stub that subclasses ``extends`` and is marked
``_cbcs_stub``, so the form still loads. The stub also stands in for the class
in ``sys.modules`` while the generated module imports it (a flagged fake
module, dropped at the start of the next load), so the generated
``from widgets.till_display import TillDisplay`` gets the stub, not the code
that failed.
"""

from __future__ import annotations

import contextlib
import importlib
import os
import signal
import sys
import threading
import time
import traceback
import types
from typing import Dict, Iterator, List, Optional, Sequence, Tuple

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


#: Seconds one own class may take to import and build, and all of them together in one load.
#: The host calls a view hung after two missed 5 s pings, so the sum stays well under that.
CLASS_SECONDS = 3.0
LOAD_SECONDS = 8.0
_STUB_MODULE = "_cbcs_stub_module"
_spent = 0.0


class ClassTimedOut(Exception):
    """An own class took too long to import or build."""


def purge_project_modules(root: Optional[str]) -> List[str]:
    """Drop ``sys.modules`` entries whose file lives under ``root``, and the stub modules of the last load."""
    global _spent
    _spent = 0.0
    dropped: List[str] = [
        name for name, module in list(sys.modules.items()) if getattr(module, _STUB_MODULE, False) is True
    ]
    for name in dropped:
        sys.modules.pop(name, None)
    if not root:
        return dropped
    real = os.path.realpath(root)
    prefix = real + os.sep
    for name, module in list(sys.modules.items()):
        filename = getattr(module, "__file__", None)
        if not isinstance(filename, str):
            continue
        path = os.path.realpath(filename)
        if path == real or path.startswith(prefix):
            dropped.append(name)
    for name in dropped:
        sys.modules.pop(name, None)
    importlib.invalidate_caches()
    return dropped


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
    """Import ``spec`` and build one instance. On failure return a stub class and the exception.

    An empty ``header_module`` means the editor knows no module for the class (a
    form outside a project): the stub is the answer, with no error. The error
    text carries the file and line of the failure inside the project.
    """
    if not spec.header_module:
        return make_stub(spec.class_name, spec.extends), None
    try:
        parts = spec.header_module.split(".")
        if not all(part.isidentifier() for part in parts):
            raise ImportError("%r is not a module path" % spec.header_module)
        with _time_limit():
            module = importlib.import_module(spec.header_module)
            cls = getattr(module, spec.class_name)
            if not isinstance(cls, type):
                raise TypeError("%s is not a class" % spec.class_name)
            _trial(cls)
        return cls, None
    except (Exception, SystemExit) as exc:
        stub = make_stub(spec.class_name, spec.extends)
        _stand_in_module(spec.header_module, spec.class_name, stub)
        return stub, _located(exc)


def _trial(cls: type) -> None:
    """Build one instance on a throwaway hidden parent and delete it, before ``setupUi``."""
    parent = QtWidgets.QWidget()
    parent.hide()
    try:
        made = cls(parent)
        delete = getattr(made, "deleteLater", None)
        if callable(delete):
            made.setParent(None)  # type: ignore[attr-defined]
            delete()
    finally:
        parent.deleteLater()


@contextlib.contextmanager
def _time_limit() -> Iterator[None]:
    """Raise ``ClassTimedOut`` in the main thread when the block runs past its limit (POSIX only)."""
    global _spent
    remaining = LOAD_SECONDS - _spent
    if remaining <= 0:
        raise ClassTimedOut("the preview had no time left for this class")
    seconds = min(CLASS_SECONDS, remaining)
    usable = (
        hasattr(signal, "setitimer")
        and hasattr(signal, "SIGALRM")
        and threading.current_thread() is threading.main_thread()
    )
    started = time.monotonic()
    if not usable:
        try:
            yield
        finally:
            _spent += time.monotonic() - started
        return

    def expired(_signum: int, _frame: object) -> None:
        raise ClassTimedOut("it took more than %d seconds" % int(seconds))

    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
        _spent += time.monotonic() - started


def _stand_in_module(module_name: str, class_name: str, stub: type) -> None:
    """Make ``from module_name import class_name`` give ``stub``. Dropped at the start of the next load."""
    parts = module_name.split(".")
    for index in range(1, len(parts)):
        parent_name = ".".join(parts[:index])
        if parent_name not in sys.modules:
            parent = types.ModuleType(parent_name)
            parent.__path__ = []  # type: ignore[attr-defined]
            setattr(parent, _STUB_MODULE, True)
            sys.modules[parent_name] = parent
    existing = sys.modules.get(module_name)
    if existing is not None and getattr(existing, _STUB_MODULE, False) is True:
        setattr(existing, class_name, stub)
        return
    fake = types.ModuleType(module_name)
    if existing is not None:
        for key, value in vars(existing).items():
            if not key.startswith("__"):
                setattr(fake, key, value)
    setattr(fake, class_name, stub)
    setattr(fake, _STUB_MODULE, True)
    sys.modules[module_name] = fake


def _located(error: BaseException) -> BaseException:
    """``error`` with the innermost project file and line in its text (UX-CUST-008).

    The host shows "{ExceptionName} in {file} line {n}". The new exception keeps the
    original type's name, so the text the session reports starts the same way.
    """
    frames = traceback.extract_tb(error.__traceback__)
    here = os.path.dirname(os.path.abspath(__file__))
    app_root = os.path.abspath(os.path.join(here, *([".."] * 5)))
    chosen = None
    for frame in frames:
        name = os.path.abspath(frame.filename)
        if "importlib" in name or name.startswith(app_root + os.sep) or name.startswith("<"):
            continue
        chosen = frame
    message = str(error)
    if isinstance(error, SyntaxError) and error.filename and error.lineno:
        message = '%s\n  File "%s", line %d, in <module>' % (error.msg, error.filename, error.lineno)
    elif chosen is not None:
        message = '%s\n  File "%s", line %d, in %s' % (message, chosen.filename, chosen.lineno, chosen.name)
    named = type("ClassFailure", (Exception,), {})
    named.__name__ = type(error).__name__
    named.__qualname__ = type(error).__name__
    return named(message)


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
