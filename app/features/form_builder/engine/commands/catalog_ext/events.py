"""``SetEventSteps`` and ``MergeEventStorage`` (CONTRACTS section 15.6, UX-LST-004, UX-LST-005).

``SetEventSteps`` is the only command the Events list, the pickers, the canvas
link and the method gesture use to change an event. It takes the whole new list
of steps for one event and writes it the way the person never has to think
about:

* every step plain (a Qt slot or a method of the window, turned on, no
  condition): native ``<connection>`` elements, one per step;
* otherwise: one ``cbcsOn<Signal>`` step list, and no native connection of that
  event is left.

Unchanged connection elements and their ``<hints>`` are kept; only what the new
steps need is inserted, removed or moved. The whole change is one log entry.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import ClassVar, Dict, Hashable, List, Optional, Sequence, Tuple

from app.features.form_builder.engine.commands import planning
from app.features.form_builder.engine.commands.base import CommandRejected, PlanContext
from app.features.form_builder.engine.commands.ops import MoveNodeOp, RemoveNodeOp
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.logic import compat
from app.features.form_builder.engine.logic.events import (
    EventState,
    NativeRef,
    declared_methods,
    read_event,
    sender_node,
    signal_property,
    step_key,
)
from app.features.form_builder.engine.logic.events_codec import EventStep, WriteError, write_list
from app.features.form_builder.engine.logic.codec import checked_hint_points, marker_read_only
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.schema import ConnectionHint, SlotsDecl

Overloads = Tuple[Tuple[str, Tuple[str, ...]], ...]

EDIT_EVENTS = "Edit events"
MERGE_EVENT = "Merge event"


def register(registry: object) -> None:
    add = getattr(registry, "add", None)
    if add is None:
        return
    add(SetEventSteps)
    add(MergeEventStorage)


def require_logic_writable(doc: UiDocument) -> None:
    """FB402: the form's behavior is from a newer version, so no logic write is allowed (CONTRACTS 15.7)."""
    if marker_read_only(doc.root.prop("cbcsLogic")):  # newer, or a marker that can't be read (15.2)
        raise CommandRejected(
            "This form's behavior was saved by a newer version of Code Studio, so it can't be changed here.",
            code="FB402",
        )


@dataclass(frozen=True)
class EventEdit:
    """The full new steps of one more event, changed in the same undo step (an intent of two events)."""

    sender: str
    signal_name: str
    steps: Tuple[EventStep, ...]


@dataclass(frozen=True)
class SetEventSteps:
    """Replace the steps of the event ``(sender, signal_name)``. ``caption`` is the undo name (UX 13.3.8).

    ``also`` changes further events in the same entry ("Keep a and b in step").
    """

    command_type: ClassVar[str] = "set_event_steps"
    sender: str
    signal_name: str
    steps: Tuple[EventStep, ...]
    merge_token: Optional[str] = None
    caption: str = ""
    also: Tuple[EventEdit, ...] = ()

    @property
    def label(self) -> str:
        return self.caption or EDIT_EVENTS

    def merge_key(self) -> Optional[Hashable]:
        return None

    def apply(self, doc: UiDocument, ctx: PlanContext) -> None:
        require_logic_writable(doc)
        sender_id = _plan_event(doc, ctx, self.sender, self.signal_name, tuple(self.steps))
        for extra in self.also:
            _plan_event(doc, ctx, extra.sender, extra.signal_name, tuple(extra.steps))
        ctx.select((sender_id,), sender_id)


@dataclass(frozen=True)
class MergeEventStorage:
    """FB404's fix: the native steps first (they ran first), then the list's, stored by the usual choice."""

    command_type: ClassVar[str] = "merge_event_storage"
    sender: str
    signal_name: str
    merge_token: Optional[str] = None
    caption: str = ""

    @property
    def label(self) -> str:
        return self.caption or MERGE_EVENT

    def merge_key(self) -> Optional[Hashable]:
        return None

    def apply(self, doc: UiDocument, ctx: PlanContext) -> None:
        require_logic_writable(doc)
        state = read_event(doc, self.sender, self.signal_name)
        sender_id = _plan_event(doc, ctx, self.sender, self.signal_name, state.steps)
        ctx.select((sender_id,), sender_id)


def steps_added(
    doc: UiDocument, sender: str, signal_name: str, new_steps: Sequence[EventStep], caption: str = ""
) -> SetEventSteps:
    """The command that adds ``new_steps`` after the event's current ones (a picker's choice)."""
    state = read_event(doc, sender, signal_name)
    return SetEventSteps(sender, signal_name, state.steps + tuple(new_steps), caption=caption)


# --- planning ----------------------------------------------------------------------------


def _plan_event(
    doc: UiDocument, ctx: PlanContext, sender: str, signal_name: str, steps: Tuple[EventStep, ...]
) -> NodeId:
    node = sender_node(doc, sender)
    if node is None:
        raise CommandRejected("%s is not on this form." % sender)
    class_name, declared = compat.node_class(doc, ctx.classes, node)
    if not class_name:
        raise CommandRejected("Layouts and spacers don't have events. Select a widget.")
    state = read_event(doc, sender, signal_name)
    if state.list_error is not None:
        raise CommandRejected(
            "This event can't be read (line %d). It is kept as it is and does nothing when the form runs."
            % state.list_error[0],
            code="FB401",
        )
    overloads = _overloads(ctx, class_name, declared, state)
    if not overloads:
        raise CommandRejected("%s has no event %s." % (sender, signal_name))
    existing_keys = {step_key(doc, step) for step in state.steps if step.verb in ("slot", "call")}
    for step in steps:
        _check_step(doc, step, overloads, existing_keys)
    steps = tuple(_with_d7_hints(state.steps, step) for step in steps)
    if not steps:
        _remove_natives(ctx, state.native)
        _write_list(doc, ctx, state, node.id, (), None)
        return node.id
    if all(step.plain for step in steps):
        _write_native(doc, ctx, state, sender, overloads, steps)
        _write_list(doc, ctx, state, node.id, (), None)
    else:
        wrapper = state.list_signal
        _remove_natives(ctx, state.native)
        _write_list(doc, ctx, state, node.id, steps, wrapper)
    _declare_methods(doc, ctx, overloads, steps)
    return node.id


def _overloads(ctx: PlanContext, class_name: str, declared: Optional[SlotsDecl], state: EventState) -> Overloads:
    signatures = list(compat.signals_of(ctx.classes, class_name, declared))
    signatures.extend(ref.signal for ref in state.native)
    return compat.overloads_of(signatures, state.signal_name)


def _check_step(
    doc: UiDocument, step: EventStep, overloads: Overloads, existing_keys: set
) -> None:
    if step.verb not in ("slot", "call"):
        if step.raw is None:
            raise CommandRejected("Code Studio can't write a step of kind %s." % step.verb)
        return
    if step.raw is not None:
        return
    if step.verb == "slot":
        name, params = compat.split_signature(step.slot)
        if not compat.is_name(step.target) or not compat.is_signature(step.slot):
            raise CommandRejected("A step needs a target and a signature such as clear().")
        if step.hints and checked_hint_points(step.hints) is None:
            raise CommandRejected("A step's label points aren't ones a .ui file can hold.")
        known = step_key(doc, step) in existing_keys
        if step.target not in doc.names() and not known:
            raise CommandRejected("%s isn't on this form." % step.target)
        if not any(compat.fits(params, shown[1]) for shown in overloads):
            raise CommandRejected("%s can't run on this event: it needs more values than the event sends." % step.slot)
        return
    if not compat.is_name(step.method):
        raise CommandRejected("%s isn't a name a method can have." % step.method)
    if step.args < 0 or not any(len(shown[1]) >= step.args for shown in overloads):
        raise CommandRejected("%s() asks for more values than the event sends." % step.method)


def _remove_natives(ctx: PlanContext, natives: Sequence[NativeRef]) -> None:
    for ref in natives:
        ctx.do(RemoveNodeOp(ref.node_id))


def _write_list(
    doc: UiDocument,
    ctx: PlanContext,
    state: EventState,
    owner: NodeId,
    steps: Tuple[EventStep, ...],
    signal: Optional[str],
) -> None:
    key = signal_property(state.signal_name)
    if not steps:
        if state.list_property is not None:
            planning.set_logic(doc, ctx, owner, key, None)
        return
    if state.list_property is not None and state.list_steps == steps and state.list_signal == signal:
        return  # the same steps: keep the text exactly as it was read
    try:
        text = write_list(steps, signal, state.list_extra)
    except WriteError as error:
        raise CommandRejected("This step list can't be written: %s" % error, code="FB401") from error
    planning.set_logic(doc, ctx, owner, key, text)


def _write_native(
    doc: UiDocument,
    ctx: PlanContext,
    state: EventState,
    sender: str,
    overloads: Overloads,
    steps: Tuple[EventStep, ...],
) -> None:
    """Minimal diff (CONTRACTS 15.6 rule 3)."""
    existing = list(state.native)
    used: Dict[NodeId, int] = {}
    matched: List[Optional[NativeRef]] = []
    for step in steps:
        found = _take_existing(doc, step, existing, used)
        if found is not None:
            used[found.node_id] = len(used)
        matched.append(found)
    _remove_natives(ctx, [ref for ref in existing if ref.node_id not in used])
    live = [node.id for node in doc.connections()]
    stay = _stay_set([ref.node_id for ref in matched if ref is not None], live)
    kept_ids = [ref.node_id for ref in matched if ref is not None]
    previous: Optional[NodeId] = None
    for step, ref in zip(steps, matched):
        if ref is not None:
            if ref.node_id not in stay:
                live.remove(ref.node_id)
                at = _slot_index(doc, live, previous, kept_ids, sender, ref.node_id)
                ctx.do(MoveNodeOp(ref.node_id, doc.ui.id, "connections", at))
                live.insert(at, ref.node_id)
            previous = ref.node_id
            continue
        signal, receiver, slot = _new_connection(doc, step, overloads)
        at = _slot_index(doc, live, previous, kept_ids, sender, None)
        added = planning.add_connection(doc, ctx, sender, signal, receiver, slot, at)
        if step.hints:
            planning.set_field(
                doc,
                ctx,
                added,
                "hints",
                tuple(ConnectionHint(kind, x, y) for kind, x, y in step.hints),
            )
        live.insert(at, added)
        kept_ids.append(added)
        previous = added


def _arrow_end(step: EventStep) -> Tuple[str, str]:
    name, params = compat.split_signature(step.slot)
    return step.target, compat.signature_text(name, params)


def _with_d7_hints(old: Sequence[EventStep], step: EventStep) -> EventStep:
    """Drop hint points that were copied onto a different receiver or slot (UX D7).

    The same points on the same arrow end stay. Points that no previous step
    carried are new and stay too.
    """
    if step.verb != "slot" or not step.hints:
        return step
    end = _arrow_end(step)
    same = False
    copied = False
    for prior in old:
        if prior.verb != "slot" or prior.hints != step.hints:
            continue
        if _arrow_end(prior) == end:
            same = True
        else:
            copied = True
    if copied and not same:
        return replace(step, hints=())
    return step


def _take_existing(
    doc: UiDocument, step: EventStep, existing: Sequence[NativeRef], used: Dict[NodeId, int]
) -> Optional[NativeRef]:
    """The element for ``step``. Prefer the one whose hint points already match."""
    key = step_key(doc, step)
    candidates = [ref for ref in existing if ref.node_id not in used and step_key(doc, ref.step) == key]
    if not candidates:
        return None
    for ref in candidates:
        if ref.step.hints == step.hints:
            return ref
    return candidates[0]


def _stay_set(matched_ids: Sequence[NodeId], live: Sequence[NodeId]) -> set:
    """The matched elements that keep their place: the longest run whose file order already
    agrees with the new step order."""
    positions = [live.index(node_id) for node_id in matched_ids]
    count = len(positions)
    if count == 0:
        return set()
    best = [1] * count
    back = [-1] * count
    for i in range(count):
        for j in range(i):
            if positions[j] < positions[i] and best[j] + 1 > best[i]:
                best[i] = best[j] + 1
                back[i] = j
    end = max(range(count), key=lambda index: best[index])
    keep = set()
    while end != -1:
        keep.add(matched_ids[end])
        end = back[end]
    return keep


def _slot_index(
    doc: UiDocument,
    live: Sequence[NodeId],
    previous: Optional[NodeId],
    event_ids: Sequence[NodeId],
    sender: str,
    skip: Optional[NodeId],
) -> int:
    """Where the next element of the event goes: right after the previous step's element; the first
    step goes before the event's first remaining element, else after the sender's last connection,
    else at the end of ``<connections>``."""
    if previous is not None:
        return list(live).index(previous) + 1
    remaining = [live.index(node_id) for node_id in event_ids if node_id in live and node_id != skip]
    if remaining:
        return min(remaining)
    last = -1
    for index, node_id in enumerate(live):
        if doc.node(node_id).field("sender") == sender:
            last = index
    return last + 1 if last >= 0 else len(live)


def _new_connection(doc: UiDocument, step: EventStep, overloads: Overloads) -> Tuple[str, str, str]:
    """``(signal, receiver, slot)`` of the connection a plain step needs (rule 2)."""
    if step.verb == "slot":
        _name, params = compat.split_signature(step.slot)
        chosen = compat.narrowest_covering(overloads, params)
        receiver, slot = step.target, compat.signature_text(_name, params)
    else:
        chosen = compat.narrowest_covering(overloads, (), step.args)
        receiver = doc.root.object_name
        slot = ""
    if chosen is None:
        raise CommandRejected("No event fits that step.")
    if step.verb == "call":
        slot = compat.signature_text(step.method, chosen[1][: step.args])
    return chosen[0], receiver, slot


def _declare_methods(doc: UiDocument, ctx: PlanContext, overloads: Overloads, steps: Sequence[EventStep]) -> None:
    """Rule 4: a method a ``call`` step names is declared on the form when the form has none of that name."""
    declared = doc.ui.field("form_slots")
    if declared is not None and not isinstance(declared, SlotsDecl):
        return  # an unknown <slots> shape is kept as it is
    known = declared_methods(doc)
    slots: List[str] = list(declared.slots) if isinstance(declared, SlotsDecl) else []
    signals: Tuple[str, ...] = declared.signals if isinstance(declared, SlotsDecl) else ()
    added = False
    for step in steps:
        if step.verb != "call" or step.raw is not None or step.method in known:
            continue
        chosen = compat.narrowest_covering(overloads, (), step.args)
        if chosen is None:
            continue
        slots.append(compat.signature_text(step.method, chosen[1][: step.args]))
        known[step.method] = chosen[1][: step.args]
        added = True
    if added:
        planning.set_form_slots(doc, ctx, signals, tuple(slots))
