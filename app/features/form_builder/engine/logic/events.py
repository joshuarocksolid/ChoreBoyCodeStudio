"""The event model over connections and step lists (CONTRACTS section 15.6). Qt-free.

An event is ``(sender object name, signal name)``. Its steps, in run order, are
the native ``<connection>`` elements of that sender and signal, in
``<connections>`` order, then the ``cbcsOn<Signal>`` list. Methods Qt connects
by name are shown by the code lane (M6.2) and never stored, so they are not
here. Reading never writes; ``SetEventSteps`` (``commands/catalog_ext/events.py``)
is the only writer.
"""

from __future__ import annotations

import weakref
from contextlib import contextmanager
from dataclasses import dataclass, replace
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple

from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.logic.codec import checked_hint_points
from app.features.form_builder.engine.logic.compat import signature_text, split_signature
from app.features.form_builder.engine.logic.events_codec import EventStep, StepList, read_list
from app.features.form_builder.engine.logic.storage import signal_of_property, signal_property
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import Node
from app.features.form_builder.engine.ui4.schema import ConnectionHint, SlotsDecl
from app.features.form_builder.engine.ui4.values import StringValue

@dataclass(frozen=True)
class NativeRef:
    """One native ``<connection>`` of an event, as a step."""

    node_id: NodeId
    signal: str
    receiver: str
    slot: str
    step: EventStep


@dataclass(frozen=True)
class EventState:
    """Everything stored for one event."""

    sender: str
    signal_name: str
    native: Tuple[NativeRef, ...]
    list_property: Optional[str]
    list_steps: Tuple[EventStep, ...]
    list_signal: Optional[str]
    list_error: Optional[Tuple[int, str]]
    list_extra: Tuple[Tuple[str, Any], ...] = ()

    @property
    def steps(self) -> Tuple[EventStep, ...]:
        """Run order: native steps, then the list's."""
        return tuple(ref.step for ref in self.native) + self.list_steps

    @property
    def stored_twice(self) -> bool:
        """Native connections and a step list together (FB404)."""
        return bool(self.native) and bool(self.list_steps)

    @property
    def has_unreadable_list(self) -> bool:
        return self.list_error is not None


def sender_node(doc: UiDocument, name: str) -> Optional[Node]:
    found = doc.by_name(name)
    return doc.node(found[0]) if found else None


def declared_methods(doc: UiDocument) -> Dict[str, Tuple[str, ...]]:
    """Method name -> parameter types of each ``<slots><slot>`` the form declares."""
    declared = doc.ui.field("form_slots")
    found: Dict[str, Tuple[str, ...]] = {}
    if isinstance(declared, SlotsDecl):
        for signature in declared.slots:
            name, params = split_signature(signature)
            found.setdefault(name, params)
    return found


def native_step(doc: UiDocument, receiver: str, slot: str) -> EventStep:
    """A connection's receiver and slot as a step.

    A slot the form declares, on the form itself, is the window's own method: a
    ``call`` step. Anything else is a ``slot`` step on its receiver.
    """
    name, params = split_signature(slot)
    if receiver == doc.root.object_name and name in declared_methods(doc):
        return EventStep("call", method=name, args=len(params))
    return EventStep("slot", target=receiver, slot=signature_text(name, params))


def _connection_hint_points(node: Node) -> Tuple[Tuple[str, int, int], ...]:
    """A connection's ``<hints>`` in document order, or empty when they are not typed points.

    An opaque ``<hints>`` block stays on the element. It has no step form, so a later
    conversion that deletes the element cannot copy it.
    """
    raw = node.field("hints")
    if not isinstance(raw, tuple) or not raw:
        return ()
    points: List[Tuple[object, ...]] = []
    for item in raw:
        if not isinstance(item, ConnectionHint):
            return ()
        points.append((item.type, item.x, item.y))
    checked = checked_hint_points(points)
    return checked if checked is not None else ()


def step_key(doc: UiDocument, step: EventStep) -> Tuple[object, ...]:
    """What makes two plain steps the same connection (CONTRACTS 15.6 rule 3): receiver and slot."""
    if step.verb == "call":
        return ("call", step.method, step.args)
    name, params = split_signature(step.slot)
    if step.target == doc.root.object_name and name in declared_methods(doc):
        return ("call", name, len(params))
    return ("slot", step.target, signature_text(name, params))


def read_event(doc: UiDocument, sender: str, signal_name: str) -> EventState:
    native: List[NativeRef] = []
    for node in doc.connections():
        if node.field("sender") != sender:
            continue
        signal = node.field("signal")
        receiver = node.field("receiver")
        slot = node.field("slot")
        if not (isinstance(signal, str) and isinstance(receiver, str) and isinstance(slot, str)):
            continue
        if split_signature(signal)[0] != signal_name:
            continue
        step = native_step(doc, receiver, slot)
        if step.verb == "slot":
            points = _connection_hint_points(node)
            if points:
                step = replace(step, hints=points)
        native.append(NativeRef(node.id, signal, receiver, slot, step))
    key = signal_property(signal_name)
    owner = sender_node(doc, sender)
    entry = owner.prop(key) if owner is not None else None
    parsed: Optional[StepList] = None
    if entry is not None and isinstance(entry.value, StringValue):
        parsed = read_list(entry.value.text)
    return EventState(
        sender=sender,
        signal_name=signal_name,
        native=tuple(native),
        list_property=key if parsed is not None else None,
        list_steps=parsed.steps if parsed is not None else (),
        list_signal=parsed.signal if parsed is not None else None,
        list_error=parsed.error if parsed is not None else None,
        list_extra=parsed.extra if parsed is not None else (),
    )


_READ: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()
_FULL = object()
# doc -> _FULL, or [base revision, set of (sender, signal) edited since that revision]
_TOUCH: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()
_SCOPE: Dict[int, Set[Tuple[str, str]]] = {}


@contextmanager
def event_edits(doc: UiDocument, pairs: Tuple[Tuple[str, str], ...]) -> Iterator[None]:
    """The bumps inside this block rewrite only these events. Anything else rereads the form."""
    _bind_revision(doc)
    previous = _SCOPE.get(id(doc))
    _SCOPE[id(doc)] = set(pairs)
    try:
        yield
    finally:
        if previous is None:
            _SCOPE.pop(id(doc), None)
        else:
            _SCOPE[id(doc)] = previous


def _bind_revision(doc: UiDocument) -> None:
    if getattr(doc, "_event_rev_hook", False):
        return
    doc._event_rev_hook = True  # type: ignore[attr-defined]
    current = doc._revision_listener

    def _hook(document: UiDocument) -> None:
        _on_revision(document)
        if current is not None:
            current(document)

    doc._revision_listener = _hook


def _on_revision(doc: UiDocument) -> None:
    scope = _SCOPE.get(id(doc))
    current = _TOUCH.get(doc, None)
    if scope is None or current is _FULL:
        _TOUCH[doc] = _FULL
        return
    if not isinstance(current, list):
        _TOUCH[doc] = [doc.revision - 1, set(scope)]
        return
    current[1].update(scope)


def read_events(doc: UiDocument) -> Tuple[EventState, ...]:
    """Every event of the form that has a step. Events with native connections come first, in
    ``<connections>`` order of their first connection; list-only events follow in document order.

    One tuple per document revision. A step commit rereads only the senders it edited.
    """
    cached = _READ.get(doc)
    if cached is not None and cached[0] == doc.revision:
        return cached[1]
    touch = _TOUCH.get(doc, None)
    if (
        cached is not None
        and isinstance(touch, list)
        and touch[0] == cached[0]
    ):
        result = _splice(doc, cached[1], touch[1])
    else:
        result = _read_events(doc)
    _TOUCH.pop(doc, None)
    _READ[doc] = (doc.revision, result)
    return result


def _splice(
    doc: UiDocument,
    previous: Tuple[EventState, ...],
    pairs: Set[Tuple[str, str]],
) -> Tuple[EventState, ...]:
    by_key = {(state.sender, state.signal_name): state for state in previous}
    for sender, signal_name in pairs:
        state = read_event(doc, sender, signal_name)
        if state.native or state.list_steps or state.list_error is not None:
            by_key[(sender, signal_name)] = state
        else:
            by_key.pop((sender, signal_name), None)
    ordered: List[EventState] = []
    seen: Set[Tuple[str, str]] = set()
    for state in previous:
        key = (state.sender, state.signal_name)
        if key not in by_key:
            continue
        ordered.append(by_key[key])
        seen.add(key)
    for key, state in by_key.items():
        if key not in seen:
            ordered.append(state)
    return tuple(ordered)


def _read_events(doc: UiDocument) -> Tuple[EventState, ...]:
    keys: List[Tuple[str, str]] = []
    seen: Set[Tuple[str, str]] = set()
    for node in doc.connections():
        sender = node.field("sender")
        signal = node.field("signal")
        if isinstance(sender, str) and isinstance(signal, str):
            key = (sender, split_signature(signal)[0])
            if key not in seen:
                seen.add(key)
                keys.append(key)
    for node in doc.iter_preorder():
        for entry in node.properties():
            signal_name = signal_of_property(entry.name)
            if signal_name is None:
                continue
            owner = _owner_name(node)
            if owner is None:
                continue
            key = (owner, signal_name)
            if key not in seen:
                seen.add(key)
                keys.append(key)
    return tuple(read_event(doc, sender, signal_name) for sender, signal_name in keys)


def _owner_name(node: Node) -> Optional[str]:
    for field in ("object_name", "name"):
        value = node.field(field)
        if isinstance(value, str) and value:
            return value
    return None


def events_of_sender(doc: UiDocument, sender: str) -> Tuple[EventState, ...]:
    return tuple(state for state in read_events(doc) if state.sender == sender)


def step_targets(doc: UiDocument, step: EventStep) -> Optional[str]:
    """The object a step acts on (``slot`` steps only); a ``call`` acts on the form."""
    if step.verb == "slot":
        return step.target
    if step.verb == "call":
        return doc.root.object_name
    return None
