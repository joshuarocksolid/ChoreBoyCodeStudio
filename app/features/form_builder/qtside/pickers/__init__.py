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
from app.features.form_builder.qtside.inspector.behavior_ext._rows import Gesture, MethodAsk, Outcome, finish
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
    methods, window_file, window_class = _window(host)
    ctx = build_context(doc, parsed, receiver, methods, window_file, window_class)
    picker.open_at(host, ctx)
    return picker


def _commit(host: QWidget, source: PickerSource, gesture: Gesture) -> None:
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
    result = services.execute(outcome.command)
    if isinstance(result, Rejected):
        _narrate(host, result.message)
        return
    if isinstance(result, Dropped):
        return
    if outcome.status:
        _narrate(host, outcome.status)


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
        current = current.parentWidget()
    return None


def _surface(widget: QWidget) -> object:
    current: Optional[QWidget] = widget
    while current is not None:
        if callable(getattr(current, "narrate", None)) and callable(getattr(current, "toggle_source_view", None)):
            return current
        current = current.parentWidget()
    return None


def _window(host: QWidget) -> tuple:
    surface = _surface(host)
    services = _services(host)
    if services is None:
        return (), "", ""
    path = ""
    scope = getattr(services.session, "scope", None)
    if scope is not None:
        path = getattr(scope, "window_path", None) or ""
    file_name = os.path.basename(path) if path else ""
    klass = services.session.document.form_class_name()
    methods: tuple = ()
    service = method_actions()
    listed = getattr(service, "methods", None)
    if callable(listed) and surface is not None:
        found = listed(surface)
        if isinstance(found, tuple):
            methods = tuple(str(getattr(item, "name", "")) for item in found)
    return methods, file_name, klass
