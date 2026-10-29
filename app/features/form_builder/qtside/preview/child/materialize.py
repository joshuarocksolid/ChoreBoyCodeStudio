"""Build the preview widget for one LoadForm.

``module_source`` is the generated ``ui_<name>.py`` text and wins when it is
set. ``ui_xml`` goes through QUiLoader with plugin paths cleared and a
``createWidget`` override for promoted classes. External forms stay on that
path. Codegen is not in this tree yet, so a host that only has the ``.ui``
text sends ``ui_xml`` until it can send ``module_source``.
"""

from __future__ import annotations

import re
import sys
import types
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from app.features.form_builder.engine.ipc.protocol import LoadForm
from app.qt.QtCore import QBuffer, QIODevice
from app.qt.QtUiTools import QUiLoader
from app.qt.QtWidgets import QDialog, QMainWindow, QWidget

from app.features.form_builder.qtside.preview.child.modules import make_stub

_WIDGET_TAG = re.compile(r"<widget\b([^>]*)/?>")
_ATTR = re.compile(r'([\w:-]+)="([^"]*)"')


@dataclass(frozen=True)
class Materialized:
    widget: QWidget
    failures: Tuple[Tuple[str, BaseException], ...]


class FormMaterializer:
    """The seam codegen replaces by filling ``LoadForm.module_source``."""

    def build(
        self,
        request: LoadForm,
        classes: Dict[str, type],
        extends: Dict[str, str],
    ) -> Materialized:
        if request.module_source:
            return Materialized(self._from_module(request.module_source, request.module_name), ())
        if request.ui_xml:
            return self._from_xml(request.ui_xml, classes, extends)
        raise RuntimeError("load_form needs module_source or ui_xml")

    def _from_module(self, source: str, module_name: str) -> QWidget:
        module = types.ModuleType(module_name)
        module.__file__ = "<%s>" % module_name
        sys.modules[module_name] = module
        exec(compile(source, module.__file__, "exec"), module.__dict__)
        ui_cls = _ui_class(module)
        if ui_cls is not None:
            host = _host_for(ui_cls, source)
            _ensure_size(host)
            host.show()
            return host
        build = module.__dict__.get("build_preview")
        if callable(build):
            widget = build()
            if isinstance(widget, QWidget):
                _ensure_size(widget)
                widget.show()
                return widget
        raise RuntimeError("generated module %s has no Ui_ class" % module_name)

    def _from_xml(
        self,
        xml: str,
        classes: Dict[str, type],
        extends: Dict[str, str],
    ) -> Materialized:
        failures: List[Tuple[str, BaseException]] = []
        loader = _PromotedLoader(classes, extends, failures)
        buffer = QBuffer()
        buffer.setData(xml.encode("utf-8"))
        buffer.open(QIODevice.ReadOnly)
        widget = None
        load_error: Optional[BaseException] = None
        try:
            widget = loader.load(buffer)
        except Exception as exc:
            load_error = exc
            widget = None
        if widget is None:
            widget = _fallback_form(
                xml,
                classes,
                extends,
                failures,
                load_error or _loader_error(loader),
                record_failures=not failures,
            )
        _ensure_size(widget)
        widget.show()
        return Materialized(widget, tuple(failures))


class _PromotedLoader(QUiLoader):
    def __init__(
        self,
        classes: Dict[str, type],
        extends: Dict[str, str],
        failures: List[Tuple[str, BaseException]],
    ) -> None:
        super().__init__()
        self._classes = classes
        self._extends = extends
        self._failures = failures
        clear = getattr(self, "clearPluginPaths", None)
        if callable(clear):
            clear()

    def createWidget(self, class_name: str, parent: Optional[QWidget] = None, name: str = "") -> QWidget:  # noqa: N802
        cls = self._classes.get(class_name)
        if cls is None:
            created = super().createWidget(class_name, parent, name)
            if created is None:
                raise RuntimeError("QUiLoader could not create %s" % class_name)
            return created
        try:
            widget = cls(parent)
        except Exception as exc:
            self._failures.append((class_name, exc))
            widget = make_stub(class_name, self._extends.get(class_name, "QWidget"))(parent)
        if name:
            widget.setObjectName(name)
        return widget


def _host_for(ui_cls: type, source: str) -> QWidget:
    """The window ``setupUi`` fills: a main window for ``setCentralWidget``, a dialog for ``accept``, else a widget.

    The generated class does not name its root class, so the module's own calls say what it needs
    (a QMainWindow form calls ``setCentralWidget`` and ``setMenuBar`` on the window; a dialog's
    button box connects to its ``accept`` and ``reject``). The others are tried when the first fails.
    """
    if "setCentralWidget(" in source or ".setMenuBar(" in source or ".setStatusBar(" in source:
        order: Tuple[type, ...] = (QMainWindow, QDialog, QWidget)
    elif ".accept)" in source or ".reject)" in source or ".setSizeGripEnabled(" in source or ".setModal(" in source:
        order = (QDialog, QWidget, QMainWindow)
    else:
        order = (QWidget, QDialog, QMainWindow)
    error: Optional[AttributeError] = None
    for kind in order:
        host = kind()
        try:
            ui_cls().setupUi(host)
            return host
        except AttributeError as exc:
            error = exc
            host.deleteLater()
    assert error is not None
    raise error


def _ui_class(module: types.ModuleType) -> Optional[type]:
    for value in module.__dict__.values():
        if isinstance(value, type) and value.__name__.startswith("Ui_") and hasattr(value, "setupUi"):
            return value
    return None


def _ensure_size(widget: QWidget) -> None:
    if widget.width() <= 0 or widget.height() <= 0:
        widget.resize(320, 240)


def _loader_error(loader: QUiLoader) -> BaseException:
    text = ""
    reader = getattr(loader, "errorString", None)
    if callable(reader):
        text = str(reader() or "")
    return RuntimeError(text or "QUiLoader returned nothing")


def _fallback_form(
    xml: str,
    classes: Dict[str, type],
    extends: Dict[str, str],
    failures: List[Tuple[str, BaseException]],
    load_error: BaseException,
    *,
    record_failures: bool,
) -> QWidget:
    """A QWidget shell so a broken custom widget does not fail the whole load."""
    host = QWidget()
    host.setObjectName("Form")
    placed = False
    for class_name, object_name in _widget_tags(xml):
        if class_name not in classes and class_name not in extends:
            continue
        if record_failures:
            failures.append((class_name, load_error))
        stub = make_stub(class_name, extends.get(class_name, "QWidget"))(host)
        stub.setObjectName(object_name)
        placed = True
    if not placed and classes:
        raise load_error
    if not placed and not classes:
        raise load_error
    return host


def _widget_tags(xml: str) -> List[Tuple[str, str]]:
    found: List[Tuple[str, str]] = []
    for match in _WIDGET_TAG.finditer(xml):
        attrs = dict(_ATTR.findall(match.group(1)))
        class_name = attrs.get("class")
        object_name = attrs.get("name")
        if class_name and object_name:
            found.append((class_name, object_name))
    return found
