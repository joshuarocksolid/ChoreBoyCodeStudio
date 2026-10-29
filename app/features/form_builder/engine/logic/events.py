"""The event model over connections and step lists (CONTRACTS section 15.6). Qt-free.

An event is ``(sender object name, signal name)``. Its steps, in run order, are
the native ``<connection>`` elements of that sender and signal, in
``<connections>`` order, then the ``cbcsOn<Signal>`` list. Methods Qt connects
by name are shown by the code lane (M6.2) and never stored, so they are not
here. Reading never writes; ``SetEventSteps`` (``commands/catalog_ext/events.py``)
is the only writer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.logic.compat import signature_text, split_signature
from app.features.form_builder.engine.logic.events_codec import EventStep, StepList, read_list
from app.features.form_builder.engine.logic.storage import signal_of_property, signal_property
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import Node
from app.features.form_builder.engine.ui4.schema import SlotsDecl
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
        native.append(NativeRef(node.id, signal, receiver, slot, native_step(doc, receiver, slot)))
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


def read_events(doc: UiDocument) -> Tuple[EventState, ...]:
    """Every event of the form that has a step. Events with native connections come first, in
    ``<connections>`` order of their first connection; list-only events follow in document order."""
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
