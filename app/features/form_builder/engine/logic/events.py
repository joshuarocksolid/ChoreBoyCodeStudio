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
_NARROW_UNSET = object()
# doc -> _FULL, or [base revision, set of (sender, signal) edited since that revision]
_TOUCH: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()
_SCOPE: Dict[int, Set[Tuple[str, str]]] = {}
# Where each edited event sits after the command, so the splice does not walk the form.
# (sender, signal, "native", previous key or None) or (sender, signal, "other", None).
_ANCHORS: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()


@contextmanager
def event_edits(doc: UiDocument, pairs: Tuple[Tuple[str, str], ...]) -> Iterator[None]:
    """The bumps inside this block rewrite only these events. Anything else rereads the form.

    They also leave ``doc.structure_revision`` alone. An event edit sets ``cbcs*``
    properties and adds or removes connections and declared slots. It adds, removes
    and moves no widget, layout or action, and it touches no picture.
    """
    _bind_revision(doc)
    previous = _SCOPE.get(id(doc))
    _SCOPE[id(doc)] = set(pairs)
    try:
        with doc.event_only_edits():
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
        doc._event_narrow = None  # type: ignore[attr-defined]
        return
    if not isinstance(current, list):
        _TOUCH[doc] = [doc.revision - 1, set(scope)]
    else:
        current[1].update(scope)
    marker = getattr(doc, "_event_narrow", _NARROW_UNSET)
    if marker is None:
        return
    if marker is _NARROW_UNSET:
        doc._event_narrow = set(scope)  # type: ignore[attr-defined]
        return
    marker.update(scope)


def take_event_narrow(doc: UiDocument) -> Optional[Set[Tuple[str, str]]]:
    """Pairs the edits since the last publish touched, or None when the form must be rescanned."""
    marker = getattr(doc, "_event_narrow", _NARROW_UNSET)
    doc._event_narrow = _NARROW_UNSET  # type: ignore[attr-defined]
    if marker is _NARROW_UNSET or marker is None:
        return None
    return marker


def note_event_anchors(doc: UiDocument, pairs: Tuple[Tuple[str, str], ...]) -> None:
    """Record where the edited events sit, from the connection list the command already built.

    A later ``read_events`` uses this instead of walking widgets.
    """
    wanted = set(pairs)
    previous_notes = _ANCHORS.get(doc)
    if isinstance(previous_notes, list):
        for item in previous_notes:
            wanted.add((item[0], item[1]))
    found: List[Tuple[str, str, str, Optional[Tuple[str, str]]]] = []
    seen: Set[Tuple[str, str]] = set()
    previous: Optional[Tuple[str, str]] = None
    for node in doc.connections():
        sender = node.field("sender")
        signal = node.field("signal")
        if not isinstance(sender, str) or not isinstance(signal, str):
            continue
        key = (sender, split_signature(signal)[0])
        if key in seen:
            continue
        seen.add(key)
        if key in wanted:
            found.append((key[0], key[1], "native", previous))
        previous = key
    noted = {(item[0], item[1]) for item in found}
    for sender, signal_name in wanted:
        if (sender, signal_name) not in noted:
            found.append((sender, signal_name, "other", None))
    _ANCHORS[doc] = found


def read_events(doc: UiDocument) -> Tuple[EventState, ...]:
    """Every event of the form that has a step. Events with native connections come first, in
    ``<connections>`` order of their first connection; list-only events follow in document order.

    One tuple per document revision. A step commit rereads only the senders it edited,
    unless the root was renamed, a declared slot was removed or retyped, a new slot
    is already the target of an untouched connection, or the command did not record
    where the edited events sit. Those reread the form. The order check uses that
    record, not a walk of the widgets.
    """
    cached = _READ.get(doc)
    if cached is not None and cached[0] == doc.revision:
        return cached[1]
    touch = _TOUCH.get(doc, None)
    result: Optional[Tuple[EventState, ...]] = None
    keys: Optional[Tuple[Tuple[str, str], ...]] = None
    native_count = 0
    widget_order: Tuple[str, ...] = ()
    if (
        cached is not None
        and len(cached) >= 6
        and isinstance(touch, list)
        and touch[0] == cached[0]
    ):
        spliced = _splice(doc, cached[1], cached[2], cached[3], cached[4], cached[5], touch[1])
        if spliced is not None:
            result, keys, native_count = spliced
            widget_order = cached[5]
    if result is None or keys is None:
        result, keys, native_count, widget_order = _read_events(doc)
    _TOUCH.pop(doc, None)
    _ANCHORS.pop(doc, None)
    _READ[doc] = (doc.revision, result, _event_fingerprint(doc), keys, native_count, widget_order)
    return result


def _event_fingerprint(doc: UiDocument) -> Tuple[object, ...]:
    """Root name and ``<slots>``. ``read_event`` for an untouched sender depends on both."""
    root = doc.root
    name = root.object_name if root is not None else ""
    declared = doc.ui.field("form_slots")
    if isinstance(declared, SlotsDecl):
        slots: Tuple[object, ...] = ("slots", tuple(declared.signals), tuple(declared.slots))
    elif declared is None:
        slots = ("none",)
    else:
        slots = ("other", type(declared).__name__)
    return (name, slots)


def _splice(
    doc: UiDocument,
    previous: Tuple[EventState, ...],
    fingerprint: Tuple[object, ...],
    previous_keys: Tuple[Tuple[str, str], ...],
    native_count: int,
    widget_order: Tuple[str, ...],
    pairs: Set[Tuple[str, str]],
) -> Optional[Tuple[Tuple[EventState, ...], Tuple[Tuple[str, str], ...], int]]:
    """Edited pairs, in the form's event order. None when the rest of the form must be reread."""
    current = _event_fingerprint(doc)
    if _slots_need_full_read(previous, fingerprint, current, pairs):
        return None
    anchors = _ANCHORS.get(doc)
    if not isinstance(anchors, list):
        return None
    native: List[Tuple[str, str]] = [key for key in previous_keys[:native_count] if key not in pairs]
    props: List[Tuple[str, str]] = [key for key in previous_keys[native_count:] if key not in pairs]
    by_key = {(state.sender, state.signal_name): state for state in previous}
    order = {name: index for index, name in enumerate(widget_order)}
    for sender, signal_name, kind, after in anchors:
        key = (sender, signal_name)
        if key not in pairs:
            continue
        state = read_event(doc, sender, signal_name)
        if state.native or state.list_steps or state.list_error is not None:
            by_key[key] = state
        else:
            by_key.pop(key, None)
            continue
        if state.native:
            if kind != "native" or not _insert_after(native, key, after):
                return None
            continue
        if not _insert_prop(props, key, sender, order):
            return None
    keys = tuple(native + props)
    ordered: List[EventState] = []
    for key in keys:
        state = by_key.get(key)
        if state is None:
            return None
        ordered.append(state)
    return tuple(ordered), keys, len(native)


def _insert_after(
    native: List[Tuple[str, str]],
    key: Tuple[str, str],
    after: Optional[Tuple[str, str]],
) -> bool:
    if after is None:
        native.insert(0, key)
        return True
    try:
        index = native.index(after)
    except ValueError:
        return False
    native.insert(index + 1, key)
    return True


def _insert_prop(
    props: List[Tuple[str, str]],
    key: Tuple[str, str],
    sender: str,
    order: Dict[str, int],
) -> bool:
    rank = order.get(sender)
    if rank is None:
        return False
    at = 0
    for index, (owner, _signal) in enumerate(props):
        other = order.get(owner)
        if other is None:
            return False
        if other > rank:
            break
        at = index + 1
    props.insert(at, key)
    return True


def _declared_map(slots: object) -> Dict[str, Tuple[str, ...]]:
    if not isinstance(slots, tuple) or not slots or slots[0] != "slots":
        return {}
    found: Dict[str, Tuple[str, ...]] = {}
    for signature in slots[2]:
        if isinstance(signature, str):
            name, params = split_signature(signature)
            found.setdefault(name, params)
    return found


def _slots_need_full_read(
    previous: Tuple[EventState, ...],
    fingerprint: Tuple[object, ...],
    current: Tuple[object, ...],
    pairs: Set[Tuple[str, str]],
) -> bool:
    """True when an untouched sender's call-or-slot step can have changed.

    A new method name does not. A slot removed, retyped, or already aimed at
    the form from some other sender does, and so does a renamed root. The
    other sender is taken from the cached events, not from a fresh walk.
    """
    if current[0] != fingerprint[0]:
        return True
    old_slots = fingerprint[1]
    new_slots = current[1]
    old_kind = old_slots[0] if isinstance(old_slots, tuple) and old_slots else ""
    new_kind = new_slots[0] if isinstance(new_slots, tuple) and new_slots else ""
    if old_kind == "other" or new_kind == "other":
        return old_slots != new_slots
    old_map = _declared_map(old_slots)
    new_map = _declared_map(new_slots)
    if any(name not in new_map or new_map[name] != params for name, params in old_map.items()):
        return True
    added = [name for name in new_map if name not in old_map]
    if not added:
        return False
    root_name = current[0]
    added_names = set(added)
    for state in previous:
        if (state.sender, state.signal_name) in pairs:
            continue
        for ref in state.native:
            if ref.receiver != root_name or split_signature(ref.slot)[0] not in added_names:
                continue
            return True
    return False


def _event_keys(doc: UiDocument) -> Tuple[Tuple[Tuple[str, str], ...], int]:
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
    native_count = len(keys)
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
    return tuple(keys), native_count


def _read_events(
    doc: UiDocument,
) -> Tuple[Tuple[EventState, ...], Tuple[Tuple[str, str], ...], int, Tuple[str, ...]]:
    keys, native_count = _event_keys(doc)
    names: List[str] = []
    seen: Set[str] = set()
    for node in doc.iter_preorder():
        name = _owner_name(node)
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    states = tuple(read_event(doc, sender, signal_name) for sender, signal_name in keys)
    return states, keys, native_count, tuple(names)


def _owner_name(node: Node) -> Optional[str]:
    for field_name in ("object_name", "name"):
        try:
            value = node.field(field_name)
        except KeyError:
            continue
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
