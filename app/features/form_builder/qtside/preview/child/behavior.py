"""Stand-in window for Try mode. The window file is never imported.

Call methods log "Would call". ``window.m()`` reads the Window values strip, or
logs "needs a window value" once and returns blank. ``_cbcs_trace`` is recorded
and folded into "What ran" on the next turn of the event loop.
"""

from __future__ import annotations

import time
import traceback
import types
from typing import Dict, List, Optional, Tuple

from app.features.form_builder.engine.ipc.protocol import Log, TryStart
from app.features.form_builder.qtside.preview.child.materialize import host_kinds
from app.features.form_builder.qtside.preview.try_log import (
    TryEvent,
    TryLine,
    fold,
    handler_ref,
    step_counts,
)
from app.features.form_builder.qtside.preview.try_plan import wire_to_value
from app.features.form_builder.qtside.preview.what_ran import TryChrome
from app.qt.QtCore import Qt, QTimer
from app.qt.QtWidgets import QWidget


class TrySink:
    """Collects one burst and writes the log lines."""

    def __init__(
        self,
        writer: object,
        view_id: str,
        source: str,
        names: Optional[Dict[str, str]] = None,
    ) -> None:
        self._writer = writer
        self._view_id = view_id
        self._source = source
        self._names = dict(names or ())
        self._counts = step_counts(source)
        self._events: List[TryEvent] = []
        self._asked: set = set()
        self._values: Dict[str, object] = {}
        self._scheduled = False
        self._in_setup = False
        self._ui: object = None
        self.chrome: Optional[TryChrome] = None

    def bind(self, ui: object, chrome: TryChrome, values: Dict[str, object]) -> None:
        self._ui = ui
        self.chrome = chrome
        self._values = values
        chrome.what_ran.set_names(self._names)
        chrome.what_ran.activated.connect(self._open)
        chrome.run_toggled.connect(self._toggle)
        chrome.values.changed.connect(self._value_changed)

    def trace(self, kind: object, ref: object, value: object) -> None:
        self._events.append(TryEvent(str(kind or ""), str(ref or ""), value))
        self._schedule()

    def would_call(self, name: str) -> None:
        self._events.append(TryEvent("would_call", method=name))
        self._schedule()

    def needs(self, name: str) -> object:
        """The strip's value, or blank. The needs-a-value line is once per method."""
        if name in self._values:
            return self._values[name]
        if name not in self._asked:
            self._asked.add(name)
            self._events.append(TryEvent("needs_value", method=name))
            self._schedule()
        return ""

    def failed(self, handler: str) -> None:
        ref = handler_ref(self._source, handler)
        detail = traceback.format_exc()
        first = detail.strip().splitlines()
        last = first[-1] if first else "Error"
        self._events.append(TryEvent("error", ref, "%s: %s" % (ref, last)))
        self._schedule()

    def entering_setup(self, active: bool) -> None:
        self._in_setup = active

    @property
    def in_setup(self) -> bool:
        return self._in_setup

    def flush(self) -> None:
        self._scheduled = False
        events = list(self._events)
        self._events = []
        if not events:
            return
        if self.chrome is not None:
            self.chrome.what_ran.set_names(self._names)
        lines = fold(events, self._counts, {}, self._names)
        self._publish(lines)

    def _schedule(self) -> None:
        if self._scheduled:
            return
        self._scheduled = True
        QTimer.singleShot(0, self.flush)

    def _publish(self, lines: Tuple[TryLine, ...]) -> None:
        ts = int(time.time() * 1000)
        if self.chrome is not None:
            self.chrome.what_ran.add(lines, ts)
        for line in lines:
            level = "error" if line.kind == "step" and line.sentence.startswith(line.ref + ":") else "info"
            self._writer.send(  # type: ignore[attr-defined]
                Log(
                    view_id=self._view_id,
                    stream="try",
                    level=level,  # type: ignore[arg-type]
                    text=line.sentence,
                    ts_ms=ts,
                    source=line.source,
                    kind=line.kind,
                    method=line.method,
                )
            )

    def _open(self, line: object) -> None:
        if not isinstance(line, TryLine):
            return
        self._writer.send(  # type: ignore[attr-defined]
            Log(
                view_id=self._view_id,
                stream="try",
                level="info",
                text=line.sentence,
                ts_ms=int(time.time() * 1000),
                source=line.source,
                kind="open",
                method=line.method,
            )
        )

    def _toggle(self, on: bool) -> None:
        self._writer.send(  # type: ignore[attr-defined]
            Log(
                view_id=self._view_id,
                stream="try",
                level="info",
                text="on" if on else "off",
                ts_ms=int(time.time() * 1000),
                kind="run_behavior",
            )
        )

    def _value_changed(self, name: str, text: str) -> None:
        annotation = ""
        if self.chrome is not None:
            annotation = self.chrome.values._annotations.get(name, "")  # noqa: SLF001
        value = wire_to_value(text, annotation)
        if value is None:
            self._values.pop(name, None)
        else:
            self._values[name] = value
        refresh = getattr(self._ui, "cbcs_refresh", None)
        if callable(refresh):
            refresh()
        self._writer.send(  # type: ignore[attr-defined]
            Log(
                view_id=self._view_id,
                stream="try",
                level="info",
                text=text,
                ts_ms=int(time.time() * 1000),
                kind="window_value",
                method=name,
            )
        )


def make_host_factory(sink: TrySink, message: TryStart):
    """A ``host_factory`` for :class:`FormMaterializer`."""
    specs = tuple(message.window_methods)
    window_names = {name for name, _annotation in specs}
    values = {name: value for name, value in message.window_values}
    sink._values = values  # noqa: SLF001

    def factory(ui_cls: type, source: str) -> QWidget:
        guard_handlers(ui_cls, sink)
        chrome = TryChrome()
        order = host_kinds(source)
        error: Optional[AttributeError] = None
        host: Optional[QWidget] = None
        ui = None
        for kind in order:
            made = _stand_in(kind, message.form_methods, window_names, sink, values)(chrome.form_parent())
            host = made
            _as_child(made)
            sink.entering_setup(True)
            try:
                ui = ui_cls()
                ui.setupUi(made)
                error = None
                break
            except AttributeError as exc:
                error = exc
                made.setParent(None)
                made.deleteLater()
                host = None
            finally:
                sink.entering_setup(False)
        if host is None or ui is None:
            assert error is not None
            raise error
        chrome.adopt(host)
        chrome.form_ui = ui  # type: ignore[attr-defined]
        chrome.values.set_methods(specs, values)
        sink.bind(ui, chrome, values)
        chrome.resize(780, 480)
        return chrome

    return factory


def guard_handlers(ui_cls: type, sink: TrySink) -> None:
    """A raised step becomes one log line. During ``setupUi`` the error still fails the load."""
    for name, fn in list(vars(ui_cls).items()):
        if not isinstance(fn, types.FunctionType):
            continue
        if not name.startswith("_cbcs_") or name == "_cbcs_trace":
            continue

        def wrapped(self: object, *args: object, _fn: object = fn, _name: str = name, **kwargs: object) -> object:
            try:
                return _fn(self, *args, **kwargs)  # type: ignore[operator]
            except Exception:
                if sink.in_setup:
                    raise
                sink.failed(_name)
                return None

        wrapped.__name__ = name
        setattr(ui_cls, name, wrapped)


def snapshot_form(widget: QWidget) -> Dict[str, object]:
    """Field values to put back after a reload. Preview chrome is skipped."""
    texts: Dict[str, str] = {}
    checks: Dict[str, bool] = {}
    spins: Dict[str, object] = {}
    for item in widget.findChildren(QWidget):
        name = item.objectName()
        if not name or name.startswith("preview."):
            continue
        kind = type(item).__name__
        if kind in ("QCheckBox", "QRadioButton"):
            checks[name] = bool(item.isChecked())  # type: ignore[attr-defined]
            continue
        if "Spin" in kind and callable(getattr(item, "value", None)):
            spins[name] = item.value()  # type: ignore[attr-defined]
            continue
        reader = getattr(item, "text", None)
        if callable(reader):
            try:
                value = reader()
            except Exception:
                continue
            if isinstance(value, str):
                texts[name] = value
    return {"texts": texts, "checks": checks, "spins": spins}


def restore_form(widget: QWidget, saved: Dict[str, object]) -> None:
    texts = saved.get("texts") or {}
    checks = saved.get("checks") or {}
    spins = saved.get("spins") or {}
    for item in widget.findChildren(QWidget):
        name = item.objectName()
        if not name or name.startswith("preview."):
            continue
        if name in checks and type(item).__name__ in ("QCheckBox", "QRadioButton"):
            item.setChecked(bool(checks[name]))  # type: ignore[attr-defined, index]
        if name in spins and callable(getattr(item, "setValue", None)):
            item.setValue(spins[name])  # type: ignore[attr-defined, index]
        if name in texts:
            setter = getattr(item, "setText", None)
            if callable(setter) and "Spin" not in type(item).__name__:
                setter(texts[name])  # type: ignore[index]


def _stand_in(
    kind: type,
    methods: Tuple[Tuple[str, int], ...],
    window_names: set,
    sink: TrySink,
    values: Dict[str, object],
) -> type:
    def init(self: QWidget, parent: Optional[QWidget] = None) -> None:
        kind.__init__(self, parent)

    def trace(self: QWidget, kind_name: object, ref: object, value: object) -> None:
        del self
        sink.trace(kind_name, ref, value)

    namespace = {"__init__": init, "_cbcs_trace": trace}
    names = [name for name, _count in methods]
    for name in window_names:
        if name not in names:
            names.append(name)
    for name in names:
        if name in window_names:
            namespace[name] = _window_method(name, sink, values)
        else:
            namespace[name] = _call_method(name, sink)
    return type(kind.__name__, (kind,), namespace)


def _window_method(name: str, sink: TrySink, values: Dict[str, object]):
    def method(self: object, *args: object, **kwargs: object) -> object:
        del self, args, kwargs
        if name in values:
            return values[name]
        return sink.needs(name)

    method.__name__ = name
    return method


def _call_method(name: str, sink: TrySink):
    def method(self: object, *args: object, **kwargs: object) -> object:
        del self, args, kwargs
        sink.would_call(name)
        return None

    method.__name__ = name
    return method


def _as_child(widget: QWidget) -> None:
    kind = getattr(Qt, "WindowType", None)
    flag = getattr(kind, "Widget", None) if kind is not None else None
    if flag is None:
        flag = getattr(Qt, "Widget", None)
    if flag is not None:
        widget.setWindowFlags(flag)


