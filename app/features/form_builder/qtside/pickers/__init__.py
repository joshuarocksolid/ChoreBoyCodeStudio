"""Open the event picker, and turn a commit into one undo step.

The picker never calls the log. ``set_method_actions`` is how the method page
reaches the handler service: this package cannot import ``integration``.
"""

from __future__ import annotations

import os
from dataclasses import replace
from typing import Optional

from app.qt.QtWidgets import QWidget

from app.features.form_builder.engine.project.handler_names import value_param
from app.features.form_builder.engine.ui4.defaults import QtClassTable
from app.features.form_builder.qtside.inspector._services import Dropped, Rejected
from app.features.form_builder.qtside.inspector.behavior_ext._rows import (
    Gesture,
    MethodAsk,
    Outcome,
    finish,
    unused_method_sentence,
)
from app.features.form_builder.qtside.pickers.flow import PickerSource
from app.features.form_builder.qtside.pickers.popover import EventPicker, build_context
from app.features.form_builder.qtside.theme.chrome import default_chrome

_SERVICE: object = None


def set_method_actions(service: object) -> None:
    """Install the handler service (``make_method``, ``go_to``, ``methods``)."""
    global _SERVICE
    _SERVICE = service


def method_actions() -> object:
    return _SERVICE


def open_for_link(surface: QWidget, source_id: object, target_id: object = None, *, at: object = None, caption: Optional[str] = None) -> EventPicker:
    """Open the step picker for a canvas link. ``source_id`` and ``target_id`` are node ids.

    Services come from the surface. The caption defaults to "Connect {sender} to {receiver}".
    """
    from app.qt.QtCore import QPoint

    from app.features.form_builder.engine.query.tab_stops import display_name

    doc = surface.session.document
    sender = _named(doc, source_id)
    receiver = _named(doc, target_id) if target_id is not None else ""
    if caption is None:
        other = display_name(doc, receiver) if receiver else "\u2026"
        caption = "Connect %s to %s" % (display_name(doc, sender), other)
    parsed = PickerSource.parse(sender)
    services = _services(surface)
    chrome = services.chrome if services is not None else default_chrome()
    picker = EventPicker(surface, chrome, lambda gesture: _commit(surface, parsed, gesture, caption))
    methods, window_file, window_class, infos, read_line = _window(surface)
    ctx = build_context(doc, parsed, receiver, methods, window_file, window_class, infos, read_line)
    point = at if isinstance(at, QPoint) else None
    picker.open_at(surface, ctx, point)
    return picker


def _named(doc: object, node_id: object) -> str:
    if node_id is None:
        return ""
    node = doc.node(node_id)  # type: ignore[attr-defined]
    if node is None:
        return ""
    return str(getattr(node, "object_name", "") or "")


def open_for_step(
    surface: QWidget, source_id: object, signal: str, index: int, *, at: object = None, caption: Optional[str] = None
) -> EventPicker:
    """Open the step picker on one existing step. A double-clicked arrow uses this.

    ``signal`` may be Designer text (``clicked()``) or the bare name. ``index`` is
    that step in the sender's list. Esc writes nothing.
    """
    from app.qt.QtCore import QPoint

    from app.features.form_builder.engine.logic.compat import split_signature

    doc = surface.session.document
    sender = _named(doc, source_id)
    parsed = PickerSource(sender, split_signature(signal)[0], int(index))
    services = _services(surface)
    chrome = services.chrome if services is not None else default_chrome()
    picker = EventPicker(surface, chrome, lambda gesture: _commit(surface, parsed, gesture))
    methods, window_file, window_class, infos, read_line = _window(surface)
    ctx = build_context(doc, parsed, "", methods, window_file, window_class, infos, read_line)
    point = at if isinstance(at, QPoint) else None
    picker.open_at(surface, ctx, point)
    if caption and picker._page is not None:
        picker._apply(replace(picker._page, title=caption))
    return picker


def open_method_page(host: QWidget, sender: str, signal: str) -> EventPicker:
    """Write code for an event: the method page, with the suggested name selected."""
    from app.features.form_builder.qtside.pickers.flow import Page
    from app.features.form_builder.qtside.pickers.method_page import method_page

    parsed = PickerSource(sender, signal)
    services = _services(host)
    chrome = services.chrome if services is not None else default_chrome()
    picker = EventPicker(host, chrome, lambda gesture: _commit(host, parsed, gesture))
    doc = services.session.document if services is not None else None
    if doc is None:
        picker.hide()
        return picker
    methods, window_file, window_class, infos, read_line = _window(host)
    ctx = build_context(doc, parsed, "", methods, window_file, window_class, infos, read_line)
    picker.open_at(host, ctx)
    stub = Page("step", "", "", 0, (), "", False, "", "", signal, "", "", False, -1, "")
    picker._apply(method_page(ctx, stub))
    picker.field.setFocus()
    picker.field.selectAll()
    return picker


def open_event_picker(host: QWidget, source: object, target: object = "") -> EventPicker:
    """Open the picker under ``host``. ``source`` is a sender name or a ``PickerSource``.

    ``target`` is the receiver object name for a drop, or empty. Esc on the first
    page closes and writes nothing. A choice calls ``finish`` and then one execute.
    """
    parsed = PickerSource.parse(source)
    receiver = "" if target is None else str(target)
    services = _services(host)
    chrome = services.chrome if services is not None else default_chrome()
    picker = EventPicker(host, chrome, lambda gesture: _commit(host, parsed, gesture))
    doc = services.session.document if services is not None else None
    if doc is None:
        picker.hide()
        return picker
    methods, window_file, window_class, infos, read_line = _window(host)
    ctx = build_context(doc, parsed, receiver, methods, window_file, window_class, infos, read_line)
    picker.open_at(host, ctx)
    return picker


def _commit(host: QWidget, source: PickerSource, gesture: Gesture, link_caption: Optional[str] = None) -> None:
    services = _services(host)
    if services is None:
        return
    doc = services.session.document
    outcome = finish(doc, QtClassTable.shared(), source.sender, gesture)
    if outcome is None:
        return
    if outcome.method is not None:
        _note(host, outcome)
        _method(host, gesture, outcome.method)
        return
    if outcome.command is None:
        _narrate(host, outcome.status)
        return
    _note(host, outcome)
    command = outcome.command
    if link_caption and command is not None and hasattr(command, "caption"):
        command = replace(command, caption=link_caption)
    result = services.execute(command)
    if isinstance(result, Rejected):
        _narrate(host, result.message)
        return
    if isinstance(result, Dropped):
        return
    if outcome.status:
        _narrate(host, _status_sentence(host, outcome.status, outcome.unused_method))


def _method(host: QWidget, gesture: Gesture, ask: MethodAsk) -> None:
    """A new method goes through the installed service. With none installed, nothing is written."""
    service = method_actions()
    if service is None:
        return
    surface = _surface(host)
    if surface is None:
        return
    if gesture.args:
        ask = replace(ask, params=value_param(gesture.signal + "()"))
    make = getattr(service, "make_method", None)
    if not callable(make):
        return
    result = make(surface, ask)
    if result is not None and not getattr(result, "ok", True):
        _narrate(host, str(getattr(result, "reason", "")))


def _note(host: QWidget, outcome: Outcome) -> None:
    if not outcome.focus_signal:
        return
    window = host.window()
    body = window.findChild(QWidget, "formBuilder.events") if window is not None else None
    note = getattr(body, "note_added", None)
    if callable(note):
        note(outcome.focus_signal, outcome.focus_index)


def _status_sentence(host: QWidget, status: str, method: str = "") -> str:
    if status != "METHOD_UNUSED":
        return status
    _methods, file_name, _klass, _infos, _line = _window(host)
    return unused_method_sentence(method, file_name)


def _narrate(host: QWidget, sentence: str) -> None:
    if not sentence:
        return
    surface = _surface(host)
    narrate = getattr(surface, "narrate", None)
    if callable(narrate):
        narrate(sentence)


def _services(widget: QWidget) -> object:
    current: Optional[QWidget] = widget
    while current is not None:
        services = getattr(current, "_services", None)
        if services is not None and getattr(services, "session", None) is not None:
            return services
        workbench = getattr(current, "workbench", None)
        inspector = getattr(workbench, "inspector", None) if workbench is not None else None
        found = getattr(inspector, "_services", None) if inspector is not None else None
        if found is not None and getattr(found, "session", None) is not None:
            return found
        current = current.parentWidget()
    return None


def _surface(widget: QWidget) -> object:
    current: Optional[QWidget] = widget
    while current is not None:
        if callable(getattr(current, "narrate", None)) and callable(getattr(current, "toggle_source_view", None)):
            return current
        current = current.parentWidget()
    return None


def _unlistable(scope: object, file_name: str) -> str:
    if scope is None or not getattr(scope, "project_root", None):
        return "This form isn't in a project, so it has no window file."
    if not getattr(scope, "generates", False):
        return "This form isn't in forms/, so Code Studio doesn't write Python for it."
    if not file_name:
        return "This form isn't in a project, so it has no window file."
    return ""


def _window(host: QWidget) -> tuple:
    surface = _surface(host)
    services = _services(host)
    if services is None:
        return (), "", "", (), "This form isn't in a project, so it has no window file."
    path = ""
    scope = getattr(services.session, "scope", None)
    if scope is not None:
        path = getattr(scope, "window_path", None) or ""
    file_name = os.path.basename(path) if path else ""
    klass = ""
    read_line = _unlistable(scope, file_name)
    methods: tuple = ()
    infos: tuple = ()
    service = method_actions()
    reading = getattr(service, "reading", None)
    if read_line == "" and callable(reading) and surface is not None:
        read = reading(surface)
        status = getattr(read, "status", "ok")
        facts = getattr(read, "facts", None)
        if status == "syntax_error" or status == "refused":
            read_line = "%s can't be read: %s" % (file_name or "The window file", getattr(read, "reason", "") or "it could not be read")
        elif status == "ok" and facts is not None and not getattr(facts, "class_name", ""):
            read_line = "%s has no class that calls self.ui.setupUi(self)." % (file_name or "The window file")
        elif status == "ok" and facts is not None:
            klass = str(getattr(facts, "class_name", "") or "")
    if not klass and services is not None:
        from app.features.form_builder.engine.codegen.names import python_class_stem

        klass = "%sWindow" % python_class_stem(services.session.document.form_class_name())
    listed = getattr(service, "methods", None)
    if read_line == "" and callable(listed) and surface is not None:
        found = listed(surface)
        if isinstance(found, tuple):
            infos = found
            methods = tuple(str(getattr(item, "name", "")) for item in found)
    return methods, file_name, klass, infos, read_line
