"""GUI-thread request handler for the preview child."""

from __future__ import annotations

import base64
import os
import queue
import sys
import time
import traceback
import types
from typing import Dict, Optional

from app.features.form_builder.engine.ipc.protocol import (
    PROTOCOL_NAME,
    PROTOCOL_VERSION,
    ChildMessage,
    CloseView,
    ErrorReport,
    Grab,
    Hello,
    HostMessage,
    LoadForm,
    Log,
    NoiseLine,
    Ping,
    PromotedClass,
    ProtocolViolation,
    ProvideSecret,
    Response,
    SetAppearance,
    Shutdown,
    TryStart,
    TryStop,
    UpdateForm,
    ViewClosed,
    decode_line,
)
from app.features.form_builder.engine.ipc.timing import IDLE_EXIT_SECONDS
from app.qt.QtCore import QBuffer, QEvent, QIODevice, QObject, Qt
from app.qt.QtGui import QFont, QPixmap
from app.qt.QtWidgets import QApplication, QStyleFactory, QWidget

from app.features.form_builder.qtside.preview.child.materialize import FormMaterializer
from app.features.form_builder.qtside.preview.child.modules import (
    describe,
    install_promoted,
    install_resource_module,
    named_widgets,
    purge_project_modules,
    replace_sys_path,
    resolve_qt_class,
    restore_texts,
    snapshot_texts,
)
from app.features.form_builder.qtside.preview.child.stdio import FrameWriter


class _View:
    def __init__(self, widget: QWidget, revision: int, scale: float) -> None:
        self.widget = widget
        self.revision = revision
        self.scale = scale
        #: The size the form asked for, before a screen profile clamped it.
        self.natural = (widget.width(), widget.height())
        self.screen: tuple = ()


class _UserClose(QObject):
    """Esc on a preview window closes it, and a closed window tells the editor (UX-PREV-004, K20).

    One filter on the application: a key press goes to the focused widget, which can be any
    child of the window. A popup (an open combo list) is its own window, so Esc still closes only the popup.
    """

    def __init__(self, session: "ChildSession") -> None:
        super().__init__()
        self._session = session

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        kind = event.type()
        event_type = getattr(QEvent, "Type", QEvent)
        if kind == event_type.KeyPress and isinstance(watched, QWidget):
            if event.key() == Qt.Key_Escape and not event.modifiers():  # type: ignore[attr-defined]
                if self._session.close_window_of(watched):
                    return True
        elif kind == event_type.Close and isinstance(watched, QWidget):
            self._session.window_closed(watched)
        return False


class ChildSession:
    """Serves host frames on the GUI thread. A blocked ``drain`` misses pings."""

    def __init__(self, writer: FrameWriter, app: QApplication) -> None:
        self._writer = writer
        self._app = app
        self._queue: queue.Queue[Optional[str]] = queue.Queue()
        self._views: Dict[str, _View] = {}
        self._previous_root: Optional[str] = None
        self._sys_path: list[str] = []
        self._materializer = FormMaterializer()
        self._secrets: Dict[str, Optional[str]] = {}
        self._current_view: Optional[str] = None
        self._exit_code = 0
        self._closed = False
        self._last_view_change = time.monotonic()
        font = app.font()
        size = font.pointSizeF()
        if size <= 0:
            size = float(font.pointSize() if font.pointSize() > 0 else 12)
        self._base_point_size = size
        self._base_font = QFont(font)
        self._user_close = _UserClose(self)
        app.installEventFilter(self._user_close)

    @property
    def exit_code(self) -> int:
        return self._exit_code

    @property
    def finished(self) -> bool:
        return self._closed

    @property
    def current_view(self) -> Optional[str]:
        return self._current_view

    def push_line(self, line: Optional[str]) -> None:
        self._queue.put(line)

    def log_stdout(self, text: str) -> None:
        if text:
            self._log(stream="stdout", level="info", text=text, view_id=self._current_view)

    def log_qt(self, level: str, text: str) -> None:
        if text:
            self._log(stream="qt", level=level, text=text, view_id=self._current_view)

    def drain(self) -> None:
        while True:
            try:
                line = self._queue.get_nowait()
            except queue.Empty:
                return
            if line is None:
                self._finish(0)
                return
            self._handle_line(line)

    def check_idle(self) -> None:
        if self._views or self._closed:
            return
        if time.monotonic() - self._last_view_change >= IDLE_EXIT_SECONDS:
            self._finish(0)

    def _handle_line(self, line: str) -> None:
        decoded = decode_line(line.rstrip("\r\n"))
        if isinstance(decoded, NoiseLine):
            return
        if isinstance(decoded, ProtocolViolation):
            self._log(stream="stderr", level="error", text=decoded.reason, view_id=None)
            return
        if isinstance(decoded, Response):
            return
        try:
            self._dispatch(decoded)
        except Exception as exc:
            request_id = getattr(decoded, "request_id", "")
            self._writer.send(
                Response(
                    request_id=request_id if isinstance(request_id, str) else "",
                    ok=False,
                    error="internal",
                    detail="%s\n%s" % (exc, traceback.format_exc()),
                )
            )

    def _dispatch(self, message: HostMessage) -> None:
        if isinstance(message, Hello):
            self._hello(message)
        elif isinstance(message, LoadForm):
            self._load(message)
        elif isinstance(message, UpdateForm):
            self._update(message)
        elif isinstance(message, SetAppearance):
            self._set_appearance(message)
        elif isinstance(message, TryStart):
            self._try_start(message)
        elif isinstance(message, TryStop):
            self._try_stop(message)
        elif isinstance(message, ProvideSecret):
            self._provide_secret(message)
        elif isinstance(message, Grab):
            self._grab(message)
        elif isinstance(message, CloseView):
            self._close(message)
        elif isinstance(message, Ping):
            self._writer.send(Response(request_id=message.request_id, ok=True, result="pong"))
        elif isinstance(message, Shutdown):
            self._shutdown(message)
        else:
            request_id = getattr(message, "request_id", "")
            self._writer.send(
                Response(
                    request_id=request_id if isinstance(request_id, str) else "",
                    ok=False,
                    error="bad_request",
                    detail="unsupported",
                )
            )

    def _hello(self, message: Hello) -> None:
        if message.version != PROTOCOL_VERSION or message.protocol != PROTOCOL_NAME:
            self._writer.send(
                Response(
                    request_id=message.request_id,
                    ok=False,
                    error="protocol_mismatch",
                    detail="child version %s" % PROTOCOL_VERSION,
                )
            )
            self._finish(3, hard=True)
            return
        self._writer.send(
            Response(
                request_id=message.request_id,
                ok=True,
                result={
                    "protocol": PROTOCOL_NAME,
                    "version": PROTOCOL_VERSION,
                    "session_token": message.session_token,
                },
            )
        )

    def _load(self, message: LoadForm) -> None:
        self._current_view = message.view_id
        saved = {}
        existing = self._views.get(message.view_id)
        if existing is not None and message.keep_values:
            saved = snapshot_texts(existing.widget)
        try:
            purge_project_modules(self._previous_root)
            self._previous_root = message.project_root
            self._sys_path = replace_sys_path(self._sys_path, message.sys_path)
            for resource in message.resource_modules:
                install_resource_module(resource.name, resource.source)
            classes: Dict[str, type] = {}
            extends: Dict[str, str] = {}
            import_failures: list[tuple[PromotedClass, BaseException]] = []
            for promoted in message.promoted:
                cls, error = install_promoted(promoted)
                classes[promoted.class_name] = cls
                extends[promoted.class_name] = promoted.extends
                if error is not None:
                    import_failures.append((promoted, error))
            def announce(name: str, view_id: str = message.view_id) -> None:
                self._writer.send(
                    Log(
                        view_id=view_id,
                        stream="try",
                        level="info",
                        text="",
                        ts_ms=int(time.time() * 1000),
                        kind="would_call",
                        method=name,
                    )
                )

            self._materializer.on_would_call = announce
            built = self._materializer.build(message, classes, extends)
            if message.keep_values and saved:
                restore_texts(built.widget, saved)
            self._apply_appearance(message.appearance)
            scale = float(message.appearance.scale)
            self._replace_view(message.view_id, built.widget, message.revision, scale)
            self._dress(message.view_id, message.appearance, first=True)
        except Exception:
            self._writer.send(
                Response(
                    request_id=message.request_id,
                    ok=False,
                    error="load_failed",
                    detail=traceback.format_exc(),
                )
            )
            return
        for promoted, error in import_failures:
            self._writer.send(self._widget_error(message.view_id, promoted.class_name, error))
        for class_name, error in built.failures:
            self._writer.send(self._widget_error(message.view_id, class_name, error))
        names, texts, bases, stubs = describe(built.widget)
        self._writer.send(
            Response(
                request_id=message.request_id,
                ok=True,
                result={
                    "view_id": message.view_id,
                    "revision": message.revision,
                    "object_names": list(names),
                    "texts": texts,
                    "bases": bases,
                    "stubs": list(stubs),
                    **self._look(message.view_id),
                },
            )
        )

    def _update(self, message: UpdateForm) -> None:
        view = self._views.get(message.view_id)
        if view is None:
            self._fail(message.request_id, "unknown_view", message.view_id)
            return
        if view.revision != message.base_revision:
            self._fail(message.request_id, "stale", "at revision %s" % view.revision)
            return
        for patch in message.patches:
            matches = named_widgets(view.widget, patch.object_name)
            if len(matches) != 1:
                self._fail(
                    message.request_id,
                    "bad_request",
                    "object %s is not unique" % patch.object_name,
                )
                return
            if not _apply_patch(matches[0], patch.name, patch.value):
                self._fail(message.request_id, "bad_request", "cannot set %s" % patch.name)
                return
        view.revision = message.revision
        self._writer.send(
            Response(
                request_id=message.request_id,
                ok=True,
                result={"view_id": message.view_id, "revision": message.revision},
            )
        )

    def _set_appearance(self, message: SetAppearance) -> None:
        view = self._views.get(message.view_id)
        if view is None:
            self._fail(message.request_id, "unknown_view", message.view_id)
            return
        self._apply_appearance(message.appearance)
        view.scale = float(message.appearance.scale)
        self._dress(message.view_id, message.appearance, first=False)
        result = {"view_id": message.view_id}
        result.update(self._look(message.view_id))
        self._writer.send(Response(request_id=message.request_id, ok=True, result=result))

    def _try_start(self, message: TryStart) -> None:
        """Run the module. Database plans are stored and not executed here."""
        self._current_view = message.view_id
        try:
            standin = _window_standin(message.window_class_name, message.base_class, message.window_values)
            module = types.ModuleType(message.module_name)
            module.__file__ = "<%s>" % message.module_name
            module.__dict__[message.window_class_name] = standin
            sys.modules[message.module_name] = module
            exec(compile(message.module_source, module.__file__, "exec"), module.__dict__)
        except Exception:
            detail = traceback.format_exc()
            self._writer.send(
                ErrorReport(
                    view_id=message.view_id,
                    code="FB604",
                    message="Try mode hit an exception.",
                    traceback=detail,
                )
            )
            self._writer.send(
                Response(
                    request_id=message.request_id,
                    ok=False,
                    error="user_code_error",
                    detail=detail,
                )
            )
            return
        self._writer.send(
            Response(
                request_id=message.request_id,
                ok=True,
                result={"started": True, "connections": len(message.data.connections)},
            )
        )

    def _try_stop(self, message: TryStop) -> None:
        self._writer.send(Response(request_id=message.request_id, ok=True, result={"stopped": True}))

    def _provide_secret(self, message: ProvideSecret) -> None:
        # The secret stays in memory. It is not written to a log frame.
        self._secrets[message.connection] = message.secret
        self._writer.send(
            Response(request_id=message.request_id, ok=True, result={"stored": message.secret is not None})
        )

    def _grab(self, message: Grab) -> None:
        view = self._views.get(message.view_id)
        if view is None:
            self._fail(message.request_id, "unknown_view", message.view_id)
            return
        pixmap = view.widget.grab()
        if view.scale not in (1, 1.0) and pixmap.width() > 0:
            width = max(1, int(pixmap.width() * view.scale))
            height = max(1, int(pixmap.height() * view.scale))
            pixmap = pixmap.scaled(width, height)
        encoded = _png_base64(pixmap)
        self._writer.send(Response(request_id=message.request_id, ok=True, result={"png_base64": encoded}))

    def _close(self, message: CloseView) -> None:
        view = self._views.pop(message.view_id, None)
        if view is not None:
            view.widget.hide()
            view.widget.deleteLater()
            self._writer.send(ViewClosed(view_id=message.view_id, reason="host"))
        if not self._views:
            self._last_view_change = time.monotonic()
        self._writer.send(Response(request_id=message.request_id, ok=True, result={"closed": view is not None}))

    def _shutdown(self, message: Shutdown) -> None:
        for view_id in list(self._views):
            view = self._views.pop(view_id)
            view.widget.hide()
            self._writer.send(ViewClosed(view_id=view_id, reason="host"))
        self._writer.send(Response(request_id=message.request_id, ok=True, result={"bye": True}))
        self._finish(0)

    def _replace_view(self, view_id: str, widget: QWidget, revision: int, scale: float) -> None:
        previous = self._views.pop(view_id, None)
        if previous is not None:
            previous.widget.hide()
            previous.widget.deleteLater()
        self._views[view_id] = _View(widget, revision, scale)
        self._last_view_change = time.monotonic()

    def _apply_appearance(self, appearance: object) -> None:
        """Style and font are the application's, so every open window follows (no restart)."""
        style_name = getattr(appearance, "style", "") or ""
        if style_name and self._app.style().objectName().lower() != style_name.lower():
            style = QStyleFactory.create(style_name)
            if style is not None:
                self._app.setStyle(style)
        scale = float(getattr(appearance, "font_scale", 1.0) or 1.0)
        font = QFont(self._base_font)
        family = getattr(appearance, "font_family", None)
        if family:
            font.setFamily(str(family))
        size = getattr(appearance, "font_point_size", None)
        base = float(size) if size else self._base_point_size
        font.setPointSizeF(max(1.0, base * scale))
        self._app.setFont(font)

    def _dress(self, view_id: str, appearance: object, *, first: bool) -> None:
        """The window title, and its size clamped to the profile's screen (UX-PREV-001)."""
        view = self._views.get(view_id)
        if view is None:
            return
        title = getattr(appearance, "title", None)
        if title:
            view.widget.setWindowTitle(str(title))
        width = getattr(appearance, "screen_width", None)
        height = getattr(appearance, "screen_height", None)
        zoom = float(getattr(appearance, "scale", 1.0) or 1.0)
        screen = (int(width), int(height), zoom) if width and height else ()
        if screen == view.screen and not first:
            return
        view.screen = screen
        natural_width, natural_height = view.natural
        if screen:
            natural_width = min(natural_width, max(1, int(screen[0] / zoom)))
            natural_height = min(natural_height, max(1, int(screen[1] / zoom)))
        view.widget.resize(natural_width, natural_height)

    def _look(self, view_id: str) -> Dict[str, object]:
        """What the editor shows back: the styles this runtime has, and how the window came out."""
        view = self._views.get(view_id)
        look: Dict[str, object] = {"styles": list(QStyleFactory.keys()), "style": self._app.style().objectName()}
        if view is not None:
            look["title"] = view.widget.windowTitle()
            look["size"] = [view.widget.width(), view.widget.height()]
            look["font"] = self._app.font().family()
        return look

    def close_window_of(self, widget: QWidget) -> bool:
        """Close the preview window that holds ``widget`` (Esc). False when it is not one of ours."""
        top = widget.window()
        for view in self._views.values():
            if view.widget is top:
                top.close()
                return True
        return False

    def window_closed(self, widget: QWidget) -> None:
        """A preview window was closed by the user: forget it and tell the editor."""
        for view_id, view in list(self._views.items()):
            if view.widget is widget:
                self._views.pop(view_id)
                widget.deleteLater()
                self._last_view_change = time.monotonic()
                self._writer.send(ViewClosed(view_id=view_id, reason="user"))
                return

    def _widget_error(self, view_id: str, class_name: str, error: BaseException) -> ErrorReport:
        return ErrorReport(
            view_id=view_id,
            code="FB602",
            message="Custom widget %s could not load. The base class was used." % class_name,
            traceback="%s: %s" % (type(error).__name__, error),
        )

    def _fail(self, request_id: str, error: str, detail: object) -> None:
        self._writer.send(Response(request_id=request_id, ok=False, error=error, detail=str(detail)))

    def _log(self, *, stream: str, level: str, text: str, view_id: Optional[str]) -> None:
        self._writer.send(
            Log(
                view_id=view_id,
                stream=stream,  # type: ignore[arg-type]
                level=level,  # type: ignore[arg-type]
                text=text,
                ts_ms=int(time.time() * 1000),
            )
        )

    def _finish(self, code: int, *, hard: bool = False) -> None:
        if self._closed and not hard:
            return
        self._closed = True
        self._exit_code = code
        if hard:
            os._exit(code)
        self._app.quit()


def _window_standin(class_name: str, base_name: str, values: tuple) -> type:
    base = resolve_qt_class(base_name)
    mapping = {key: value for key, value in values}

    def init(self: QWidget, parent: Optional[QWidget] = None) -> None:
        base.__init__(self, parent)

    namespace = {"__init__": init}
    for method_name in mapping:
        namespace[method_name] = _returning(mapping[method_name])
    return type(class_name, (base,), namespace)


def _returning(value: object):
    def method(self: object, *args: object, **kwargs: object) -> object:
        del self, args, kwargs
        return value

    return method


def _apply_patch(widget: QWidget, name: str, value: object) -> bool:
    if value is None:
        return False
    changed = widget.setProperty(name, value)
    if changed:
        return True
    if name == "text" and isinstance(value, str):
        setter = getattr(widget, "setText", None)
        if callable(setter):
            setter(value)
            return True
    return False


def _png_base64(pixmap: QPixmap) -> str:
    buffer = QBuffer()
    buffer.open(QIODevice.WriteOnly)
    if not pixmap.save(buffer, "PNG"):
        raise RuntimeError("preview grab could not encode PNG")
    return base64.b64encode(_qbytearray_bytes(buffer.data())).decode("ascii")


def _qbytearray_bytes(data: object) -> bytes:
    if isinstance(data, (bytes, bytearray)):
        return bytes(data)
    reader = getattr(data, "data", None)
    if callable(reader):
        value = reader()
        if isinstance(value, (bytes, bytearray)):
            return bytes(value)
    return bytes(data)  # type: ignore[arg-type]
