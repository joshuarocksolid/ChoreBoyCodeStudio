"""What the Events sections show, and the one command a finished gesture becomes. Qt-free.

The three sections paint these rows. They do not build steps. ``finish`` is the
only place a gesture becomes a ``SetEventSteps`` (or a method request, a status
sentence, or nothing). Nothing here touches the undo log.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, Optional, Sequence, Tuple

from app.features.form_builder.engine.commands.catalog_ext.events import (
    EventEdit,
    MergeEventStorage,
    SetEventSteps,
    steps_added,
)
from app.features.form_builder.engine.logic import compat
from app.features.form_builder.engine.logic.codec import marker_read_only
from app.features.form_builder.engine.logic.events import (
    EventState,
    events_of_sender,
    read_event,
    read_events,
    sender_node,
)
from app.features.form_builder.engine.logic.events_catalog import (
    class_chain,
    default_event,
    event_clause,
    event_words,
    step_words,
)
from app.features.form_builder.engine.logic.events_codec import EventStep, slot_step
from app.features.form_builder.engine.logic.intents.m6 import command as intent_command
from app.features.form_builder.engine.logic.intents.m6 import edits as intent_edits
from app.features.form_builder.engine.logic.intents.m6 import intents_for
from app.features.form_builder.engine.logic.storage import signal_property
from app.features.form_builder.engine.query.tab_stops import display_name
from app.features.form_builder.engine.ui4.defaults import QtClassTable
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import ActionNode, LayoutNode, SpacerNode, WidgetNode

UNSAVABLE = (
    "This event has a step Code Studio can't save, so it is shown as it is and can't be changed here."
)
NEWER_NOTICE = (
    "This form's behavior was saved by a newer version of Code Studio. "
    "You can read it here but not change it. Layout edits still work."
)
NEWER_REFUSED = (
    "This form's behavior was saved by a newer version of Code Studio, so it can't be changed here."
)
UNREADABLE = "This event can't be read (line %d). It is kept as it is and does nothing when the form runs."
TWO_PLACES = "This event is stored in two places."
FIRST_STEP = "That is the first step."
LAST_STEP = "That is the last step."
MANY = "Select one widget to see what it does."
LAYOUT = "Layouts and spacers don't have events. Select a widget."
CODE_CAPTION = "Use + When\u2026 to pick what happens, or double-click it on the form to write code."

_CODE_DOUBLE = (
    "QPushButton",
    "QToolButton",
    "QCommandLinkButton",
    "QCheckBox",
    "QRadioButton",
    "QDialogButtonBox",
    "QAction",
)


@dataclass(frozen=True)
class StepView:
    index: int
    words: str
    accessible: str
    off: bool
    missing: bool
    unknown: bool
    readonly: bool
    problem: str
    method: str = ""


@dataclass(frozen=True)
class EventView:
    signal: str
    header: str
    qt: str
    accessible: str
    steps: Tuple[StepView, ...]
    locked: bool
    unreadable: bool
    banner: str
    stored_twice: bool
    property_name: str


@dataclass(frozen=True)
class SenderView:
    """One selection's Events section. ``kind`` is ``one``, ``many`` or ``layout``."""

    kind: str
    line: str
    display: str
    object_name: str
    friendly: str
    class_name: str
    events: Tuple[EventView, ...]
    empty: str
    caption: str
    notice: str
    read_only: bool
    message: str
    event_count: int
    default_signal: str


@dataclass(frozen=True)
class IncomingRow:
    sender: str
    signal: str
    index: int
    words: str


@dataclass(frozen=True)
class FormRow:
    sender: str
    signal: str
    index: int
    words: str
    missing: bool


@dataclass(frozen=True)
class Gesture:
    """What the list or a picker asks ``finish`` to do. The signal is the event being edited."""

    kind: str
    signal: str = ""
    index: int = -1
    direction: int = 0
    intent_id: str = ""
    target: str = ""
    slot: str = ""
    method: str = ""
    args: int = 0
    new_signal: str = ""


@dataclass(frozen=True)
class MethodAsk:
    """A new-method confirm. The installed handler service is the only writer of the window file."""

    label: str
    commands: Tuple[object, ...] = ()
    method: str = ""
    params: str = ""
    sender: str = ""
    event_words: str = ""


@dataclass(frozen=True)
class Outcome:
    """A command, a method request, a status sentence, or nothing to write.

    ``command`` None means the log is not touched. ``focus_index`` is the step
    to show after a write (``-1`` when the event itself is the row).
    """

    command: Optional[object] = None
    status: str = ""
    method: Optional[MethodAsk] = None
    focus_signal: str = ""
    focus_index: int = -1
    unused_method: str = ""


def count_events(doc: UiDocument, sender: str) -> int:
    """Events of ``sender`` that have at least one step. By-name methods count as 0 until M6.2b."""
    if not sender:
        return 0
    return sum(1 for state in events_of_sender(doc, sender) if state.steps)


def project_sender(
    doc: UiDocument,
    classes: QtClassTable,
    sender: str,
    *,
    qt_names: bool = False,
    kind: str = "one",
) -> SenderView:
    """Rows for the Events section. ``kind`` ``many`` or ``layout`` is the sentence and nothing else."""
    if kind == "many":
        return _blank("many", MANY)
    if kind == "layout":
        return _blank("layout", LAYOUT)
    node = sender_node(doc, sender)
    if node is None:
        return _blank("one", MANY)
    if isinstance(node, (LayoutNode, SpacerNode)):
        return _blank("layout", LAYOUT)
    class_name, _declared = compat.node_class(doc, classes, node)
    if not class_name:
        return _blank("layout", LAYOUT)
    chain = class_chain(classes, class_name)
    display = display_name(doc, sender)
    friendly = _friendly(class_name)
    line = "%s \u00b7 %s" % (display, sender)
    read_only = marker_read_only(doc.root.prop("cbcsLogic"))
    notice = NEWER_NOTICE if read_only else ""
    default = default_event(classes, class_name) or ""
    cache_key = (id(doc), doc.revision, sender, bool(qt_names))
    cached = _SENDER_CACHE.get(cache_key)
    if cached is not None:
        return cached
    events = tuple(
        _event_view(doc, classes, state, chain, qt_names, read_only)
        for state in events_of_sender(doc, sender)
    )
    empty = _empty_sentence(display, default, chain)
    caption = "" if read_only else (CODE_CAPTION if _goes_to_code(chain) and not events else "")
    view = SenderView(
        "one",
        line,
        display,
        sender,
        friendly,
        class_name,
        events,
        empty,
        caption,
        notice,
        read_only,
        "",
        count_events(doc, sender),
        default,
    )
    if len(_SENDER_CACHE) > 24:
        _SENDER_CACHE.clear()
    _SENDER_CACHE[cache_key] = view
    return view


def project_incoming(doc: UiDocument, classes: QtClassTable, target: str) -> Tuple[IncomingRow, ...]:
    """Steps other senders aim at ``target``, in run order."""
    if not target:
        return ()
    cache_key = (id(doc), doc.revision, target)
    cached = _INCOMING_CACHE.get(cache_key)
    if cached is not None:
        return cached
    found = []
    for state in read_events(doc):
        if state.sender == target or state.has_unreadable_list:
            continue
        aimed = [(index, step) for index, step in enumerate(state.steps) if _aims_at(doc, step, target)]
        if not aimed:
            continue
        chain = _chain_of(doc, classes, state.sender)
        sender_display = display_name(doc, state.sender)
        for index, step in aimed:
            words = "When %s: %s" % (event_clause(state.signal_name, chain, sender_display), _short_words(doc, classes, step))
            found.append(IncomingRow(state.sender, state.signal_name, index, words))
    rows = tuple(found)
    if len(_INCOMING_CACHE) > 24:
        _INCOMING_CACHE.clear()
    _INCOMING_CACHE[cache_key] = rows
    return rows


def project_form(doc: UiDocument, classes: QtClassTable) -> Tuple[FormRow, ...]:
    """Every step on the form, senders in outline order, steps in run order."""
    order = {name: index for index, name in enumerate(outline_names(doc))}
    states = sorted(read_events(doc), key=lambda state: order.get(state.sender, len(order)))
    found = []
    names = doc.names()
    for state in states:
        chain = _chain_of(doc, classes, state.sender)
        header = event_words(state.signal_name, chain).header
        sender_display = display_name(doc, state.sender)
        missing_sender = state.sender not in names
        for index, step in enumerate(state.steps):
            target = step.target if step.verb == "slot" else ""
            missing = missing_sender or (step.verb == "slot" and bool(target) and target not in names)
            if missing_sender:
                lead = "%s (missing)" % state.sender
            else:
                lead = sender_display
            words = "%s \u00b7 When %s \u2192 %s" % (lead, header, _row_words(doc, classes, step))
            if step.verb == "slot" and _layout_named(doc, step.target):
                words = "%s \u00b7 kept" % words
            found.append(FormRow(state.sender, state.signal_name, index, words, missing))
    return tuple(found)


def dropped_count(doc: UiDocument, classes: QtClassTable, sender: str, old: str, new: str) -> int:
    """How many steps of ``old`` cannot run on ``new``."""
    if old == new:
        return 0
    state = read_event(doc, sender, old)
    overloads = _overloads(doc, classes, sender, new, read_event(doc, sender, new))
    return sum(1 for step in state.steps if not _fits(step, overloads))


def finish(doc: UiDocument, classes: QtClassTable, key: str, gesture: Gesture) -> Optional[Outcome]:
    """One gesture, one outcome. No command means the caller leaves the log alone."""
    if marker_read_only(doc.root.prop("cbcsLogic")):
        return Outcome(status=NEWER_REFUSED)
    if gesture.kind == "add_intent":
        return _add_intent(doc, classes, key, gesture)
    if gesture.kind == "add_slot":
        return _add_slot(doc, classes, key, gesture)
    if gesture.kind == "add_call":
        return _add_call(doc, classes, key, gesture)
    if gesture.kind == "merge":
        return _merge(doc, classes, key, gesture)
    if gesture.kind == "change_event":
        return _change_event(doc, classes, key, gesture)
    state = read_event(doc, key, gesture.signal)
    if state.has_unreadable_list or _bad_name(state):
        return None
    if gesture.kind == "toggle":
        return _toggle(doc, classes, key, state, gesture)
    if gesture.kind == "move":
        return _move(doc, classes, key, state, gesture)
    if gesture.kind == "delete":
        return _delete(doc, classes, key, state, gesture, event=False)
    if gesture.kind == "delete_event":
        return _delete(doc, classes, key, state, gesture, event=True)
    if gesture.kind == "duplicate":
        return _duplicate(doc, classes, key, state, gesture)
    if gesture.kind == "replace_slot":
        return _replace_slot(doc, classes, key, state, gesture)
    return None


_SENDER_CACHE: Dict[Tuple[object, ...], "SenderView"] = {}
_INCOMING_CACHE: Dict[Tuple[object, ...], Tuple["IncomingRow", ...]] = {}


def outline_names(doc: UiDocument) -> Tuple[str, ...]:
    """Every widget and action, in outline order, then the form if it was not first."""
    names = []
    for node in doc.iter_preorder():
        if isinstance(node, WidgetNode) and node.object_name:
            names.append(node.object_name)
        elif isinstance(node, ActionNode) and node.name:
            names.append(node.name)
    return tuple(names)


def friendly_class(class_name: str) -> str:
    return _friendly(class_name)


# --- rows --------------------------------------------------------------------------------


def _blank(kind: str, message: str) -> SenderView:
    return SenderView(kind, "", "", "", "", "", (), "", "", "", False, message, 0, "")


def _event_view(
    doc: UiDocument,
    classes: QtClassTable,
    state: EventState,
    chain: Sequence[str],
    qt_names: bool,
    read_only: bool,
) -> EventView:
    words = event_words(state.signal_name, chain)
    signal = _qt_line(doc, classes, state)
    qt = signal if qt_names else ""
    clause = (", Qt signal %s" % signal) if signal else ""
    prop = state.list_property or signal_property(state.signal_name)
    if state.has_unreadable_list:
        line = state.list_error[0] if state.list_error else 1
        return EventView(
            state.signal_name,
            "When %s" % words.header,
            "",
            "Event, %s, can't be read" % state.signal_name,
            (),
            True,
            True,
            UNREADABLE % line,
            False,
            prop,
        )
    if _bad_name(state):
        steps = tuple(
            _step_view(doc, classes, state, index, step, words.header, True)
            for index, step in enumerate(state.steps)
        )
        return EventView(
            state.signal_name,
            "When %s" % words.header,
            qt,
            "Event, %s%s" % (state.signal_name, clause),
            steps,
            True,
            False,
            _bad_sentence(state),
            False,
            prop,
        )
    steps = tuple(
        _step_view(doc, classes, state, index, step, words.header, read_only)
        for index, step in enumerate(state.steps)
    )
    return EventView(
        state.signal_name,
        "When %s" % words.header,
        qt,
        "Event, %s%s" % (words.header, clause),
        steps,
        read_only,
        False,
        "",
        state.stored_twice,
        prop,
    )


def _step_view(
    doc: UiDocument,
    classes: QtClassTable,
    state: EventState,
    index: int,
    step: EventStep,
    header: str,
    read_only: bool,
) -> StepView:
    unknown = step.raw is not None or step.verb not in ("slot", "call")
    missing = _missing(doc, step)
    if unknown:
        words = "A step Code Studio can't edit (%s)" % step.verb
    elif missing:
        words = "%s (missing)" % step.target
    else:
        words = _row_words(doc, classes, step)
    spoken = words
    if not unknown and not missing and not step.enabled:
        words = "%s (off)" % words
    problem = ""
    if missing:
        problem = "Step %d of %s %s acts on %s, which isn't on this form." % (
            index + 1,
            state.sender,
            header,
            step.target,
        )
    accessible = "When %s, step %d of %d: %s" % (header, index + 1, max(len(state.steps), 1), spoken)
    if not step.enabled and not unknown:
        accessible += ", turned off"
    if problem:
        accessible += ", problem: %s" % problem
    return StepView(
        index,
        words,
        accessible,
        not step.enabled and not unknown,
        missing,
        unknown,
        read_only or unknown,
        problem,
        step.method if step.verb == "call" else "",
    )


def _row_words(doc: UiDocument, classes: QtClassTable, step: EventStep) -> str:
    target = step.target if step.verb == "slot" else doc.root.object_name
    return step_words(
        step,
        _named(doc, target),
        is_form=(target == doc.root.object_name),
        target_chain=_chain_of(doc, classes, target),
    )


def _short_words(doc: UiDocument, classes: QtClassTable, step: EventStep) -> str:
    """The same sentence with the display name only, for "When Clear is clicked: Clear Name"."""
    target = step.target if step.verb == "slot" else doc.root.object_name
    return step_words(
        step,
        display_name(doc, target),
        is_form=(target == doc.root.object_name),
        target_chain=_chain_of(doc, classes, target),
    )


def _named(doc: UiDocument, name: str) -> str:
    display = display_name(doc, name)
    if not name or display == name:
        return display or name
    return "%s (%s)" % (display, name)


def _empty_sentence(display: str, signal: str, chain: Sequence[str]) -> str:
    if not signal:
        return "Nothing happens yet for %s." % display
    return "Nothing happens yet when %s." % event_clause(signal, chain, display)


def _goes_to_code(chain: Sequence[str]) -> bool:
    return any(name in _CODE_DOUBLE for name in chain)


def _friendly(class_name: str) -> str:
    from app.features.form_builder.qtside.inspector.words import class_words

    return class_words(class_name).friendly


def _chain_of(doc: UiDocument, classes: QtClassTable, name: str) -> Tuple[str, ...]:
    node = sender_node(doc, name)
    if node is None:
        return ()
    class_name, _declared = compat.node_class(doc, classes, node)
    return class_chain(classes, class_name)


def _qt_line(doc: UiDocument, classes: QtClassTable, state: EventState) -> str:
    node = sender_node(doc, state.sender)
    if node is None:
        return state.signal_name + "()"
    class_name, declared = compat.node_class(doc, classes, node)
    signatures = [item for item in compat.signals_of(classes, class_name, declared) if compat.split_signature(item)[0] == state.signal_name]
    signatures.extend(ref.signal for ref in state.native if compat.split_signature(ref.signal)[0] == state.signal_name)
    if not signatures:
        return state.signal_name + "()"
    return min(signatures, key=lambda item: len(compat.split_signature(item)[1]))


def _layout_named(doc: UiDocument, name: str) -> bool:
    from app.features.form_builder.engine.ui4.nodes import LayoutNode

    found = doc.by_name(name) if name else ()
    if not found:
        return False
    return isinstance(doc.node(found[0]), LayoutNode)


def _aims_at(doc: UiDocument, step: EventStep, target: str) -> bool:
    del doc
    if step.verb == "slot":
        return step.target == target
    return False


def _missing(doc: UiDocument, step: EventStep) -> bool:
    return step.verb == "slot" and bool(step.target) and step.target not in doc.names()


def _bad_name(state: EventState) -> bool:
    return any(_bad_step(step) for step in state.steps)


def _bad_sentence(state: EventState) -> str:
    name = ""
    for step in state.steps:
        if _bad_step(step):
            name = _bad_token(step)
            break
    return "%s %s has a step whose name Code Studio can't use (%s). It is kept as it is and does nothing." % (
        state.sender,
        event_words(state.signal_name).header,
        name,
    )


def _bad_token(step: EventStep) -> str:
    if step.verb == "slot":
        if not compat.is_name(step.target):
            return step.target
        return step.slot
    if step.verb == "call":
        return step.method
    return ""


def bad_names(state: EventState) -> Tuple[str, ...]:
    """The unusable names in this event, including a native connection."""
    return tuple(_bad_token(step) for step in state.steps if _bad_step(step))


def _bad_step(step: EventStep) -> bool:
    """A typed step whose name cannot be saved. An unknown verb (``raw`` set) is not this."""
    if step.raw is not None:
        return False
    if step.verb == "slot":
        return not compat.is_name(step.target) or not compat.is_signature(step.slot)
    if step.verb == "call":
        return not compat.is_name(step.method)
    return False


def _readonly_step(step: EventStep) -> bool:
    return step.raw is not None or step.verb not in ("slot", "call")


# --- gestures ----------------------------------------------------------------------------


def _toggle(
    doc: UiDocument, classes: QtClassTable, sender: str, state: EventState, gesture: Gesture
) -> Optional[Outcome]:
    if gesture.index < 0 or gesture.index >= len(state.steps):
        return None
    step = state.steps[gesture.index]
    if _readonly_step(step):
        return None
    steps = list(state.steps)
    steps[gesture.index] = replace(step, enabled=not step.enabled)
    verb = "Turn on" if step.enabled is False else "Turn off"
    caption = "%s %s" % (verb, _short_words(doc, classes, step))
    return _written(sender, state.signal_name, tuple(steps), caption, "", gesture.index)


def _move(
    doc: UiDocument, classes: QtClassTable, sender: str, state: EventState, gesture: Gesture
) -> Optional[Outcome]:
    index = gesture.index
    if index < 0 or index >= len(state.steps):
        return None
    if _readonly_step(state.steps[index]):
        return None
    nxt = index + (1 if gesture.direction > 0 else -1)
    if nxt < 0:
        return Outcome(status=FIRST_STEP)
    if nxt >= len(state.steps):
        return Outcome(status=LAST_STEP)
    steps = list(state.steps)
    steps[index], steps[nxt] = steps[nxt], steps[index]
    caption = "Move %s" % _short_words(doc, classes, state.steps[index])
    return _written(sender, state.signal_name, tuple(steps), caption, "", nxt)


def _delete(
    doc: UiDocument,
    classes: QtClassTable,
    sender: str,
    state: EventState,
    gesture: Gesture,
    *,
    event: bool,
) -> Optional[Outcome]:
    chain = _chain_of(doc, classes, sender)
    header = event_words(state.signal_name, chain).header
    if event:
        caption = "Delete the %s event" % header
        return _written(sender, state.signal_name, (), caption, "", -1)
    if gesture.index < 0 or gesture.index >= len(state.steps):
        return None
    step = state.steps[gesture.index]
    if _readonly_step(step):
        return None
    steps = tuple(item for index, item in enumerate(state.steps) if index != gesture.index)
    caption = "Delete %s" % _short_words(doc, classes, step)
    status = ""
    unused = ""
    if step.verb == "call" and step.method and not _method_used_elsewhere(
        doc, step.method, sender, state.signal_name, gesture.index
    ):
        status = "METHOD_UNUSED"
        unused = step.method
    focus = min(gesture.index, len(steps) - 1)
    return _written(sender, state.signal_name, steps, caption, status, focus, unused)


def _method_used_elsewhere(
    doc: UiDocument, method: str, sender: str, signal: str, index: int
) -> bool:
    for state in read_events(doc):
        for step_index, step in enumerate(state.steps):
            if state.sender == sender and state.signal_name == signal and step_index == index:
                continue
            if step.verb == "call" and step.method == method:
                return True
    return False


def _duplicate(
    doc: UiDocument, classes: QtClassTable, sender: str, state: EventState, gesture: Gesture
) -> Optional[Outcome]:
    if gesture.index < 0 or gesture.index >= len(state.steps):
        return None
    step = state.steps[gesture.index]
    if _readonly_step(step):
        return None
    steps = list(state.steps)
    steps.insert(gesture.index + 1, step)
    caption = "Duplicate %s" % _short_words(doc, classes, step)
    return _written(sender, state.signal_name, tuple(steps), caption, "", gesture.index + 1)


def _replace_slot(
    doc: UiDocument, classes: QtClassTable, sender: str, state: EventState, gesture: Gesture
) -> Optional[Outcome]:
    if gesture.index < 0 or gesture.index >= len(state.steps) or not gesture.slot or not gesture.target:
        return None
    old = state.steps[gesture.index]
    if _readonly_step(old):
        return None
    # Carry the old step so its Designer hints survive when the arrow end is unchanged;
    # the engine drops them when the target or slot changes (D7).
    if old.verb == "slot" and old.target == gesture.target and old.slot == gesture.slot:
        return None
    if old.verb == "slot":
        new = replace(old, target=gesture.target, slot=gesture.slot)
    else:
        new = slot_step(gesture.target, gesture.slot)
    steps = list(state.steps)
    steps[gesture.index] = new
    caption = "Change %s to %s" % (_short_words(doc, classes, old), _short_words(doc, classes, new))
    return _written(sender, state.signal_name, tuple(steps), caption, "", gesture.index)


def _add_slot(doc: UiDocument, classes: QtClassTable, sender: str, gesture: Gesture) -> Optional[Outcome]:
    if not gesture.signal or not gesture.target or not gesture.slot:
        return None
    step = slot_step(gesture.target, gesture.slot)
    state = read_event(doc, sender, gesture.signal)
    if state.has_unreadable_list or _bad_name(state):
        return None
    chain = _chain_of(doc, classes, sender)
    caption = "Add %s to %s %s" % (
        _short_words(doc, classes, step),
        display_name(doc, sender),
        event_words(gesture.signal, chain).header,
    )
    command = steps_added(doc, sender, gesture.signal, (step,), caption)
    return Outcome(command, "", None, gesture.signal, len(state.steps))


def _add_intent(doc: UiDocument, classes: QtClassTable, sender: str, gesture: Gesture) -> Optional[Outcome]:
    found = next((item for item in intents_for(doc, classes, sender) if item.intent_id == gesture.intent_id), None)
    if found is None:
        return None
    target = gesture.target or None
    if found.needs_target and not target:
        return None
    state = read_event(doc, sender, found.event or gesture.signal)
    if state.has_unreadable_list or _bad_name(state):
        return None
    if gesture.index >= 0:
        planned = intent_edits(doc, classes, found, sender, target)
        if len(planned) == 1 and planned[0].sender == sender and 0 <= gesture.index < len(state.steps):
            old = state.steps[gesture.index]
            if not _readonly_step(old):
                steps = list(state.steps)
                steps[gesture.index] = planned[0].step
                caption = "Change %s to %s" % (
                    _short_words(doc, classes, old),
                    _short_words(doc, classes, planned[0].step),
                )
                return _written(sender, planned[0].signal_name, tuple(steps), caption, "", gesture.index)
    built = intent_command(doc, classes, found, sender, target, display=lambda name: display_name(doc, name))
    focus_signal = built.signal_name
    focus_index = len(read_event(doc, built.sender, built.signal_name).steps)
    return Outcome(built, "", None, focus_signal, focus_index)


def _add_call(doc: UiDocument, classes: QtClassTable, sender: str, gesture: Gesture) -> Optional[Outcome]:
    if not gesture.method or not compat.is_name(gesture.method) or not gesture.signal:
        return None
    state = read_event(doc, sender, gesture.signal)
    if state.has_unreadable_list or _bad_name(state):
        return None
    step = EventStep("call", method=gesture.method, args=max(0, gesture.args))
    chain = _chain_of(doc, classes, sender)
    header = event_words(gesture.signal, chain).header
    caption = "Write code for %s %s" % (display_name(doc, sender), header)
    command = steps_added(doc, sender, gesture.signal, (step,), caption)
    ask = MethodAsk(caption, (command,), gesture.method, "", sender, header)
    return Outcome(None, "", ask, gesture.signal, len(state.steps))


def _merge(doc: UiDocument, classes: QtClassTable, sender: str, gesture: Gesture) -> Optional[Outcome]:
    state = read_event(doc, sender, gesture.signal)
    if not state.stored_twice or state.has_unreadable_list or _bad_name(state):
        return None
    chain = _chain_of(doc, classes, sender)
    caption = "Merge the %s event" % event_words(gesture.signal, chain).header
    return Outcome(MergeEventStorage(sender, gesture.signal, caption=caption), "", None, gesture.signal, 0)


def _change_event(doc: UiDocument, classes: QtClassTable, sender: str, gesture: Gesture) -> Optional[Outcome]:
    old, new = gesture.signal, gesture.new_signal
    if not old or not new or old == new:
        return None
    state = read_event(doc, sender, old)
    if state.has_unreadable_list or _bad_name(state):
        return None
    destination = read_event(doc, sender, new)
    if destination.has_unreadable_list or _bad_name(destination):
        return None
    overloads = _overloads(doc, classes, sender, new, destination)
    kept = tuple(step for step in state.steps if _fits(step, overloads))
    chain = _chain_of(doc, classes, sender)
    caption = "Change the event to %s" % event_words(new, chain).header
    combined = destination.steps + kept
    command = SetEventSteps(
        sender,
        new,
        combined,
        caption=caption,
        also=(EventEdit(sender, old, ()),),
    )
    return Outcome(command, "", None, new, len(destination.steps))


def unused_method_sentence(method: str, file_name: str) -> str:
    """§13.3.8. Empty when the method or the window file is missing."""
    if not method or not file_name:
        return ""
    return "Removed the step. %s() is still in %s. \u00b7 Undo" % (method, file_name)


def _written(
    sender: str,
    signal: str,
    steps: Tuple[EventStep, ...],
    caption: str,
    status: str,
    focus: int,
    unused: str = "",
) -> Outcome:
    return Outcome(
        SetEventSteps(sender, signal, steps, caption=caption),
        status,
        None,
        signal,
        focus,
        unused,
    )


def _fits(step: EventStep, overloads: Tuple[Tuple[str, Tuple[str, ...]], ...]) -> bool:
    if step.raw is not None or step.verb not in ("slot", "call"):
        return False
    if step.verb == "slot":
        params = compat.split_signature(step.slot)[1]
        return any(compat.fits(params, shown[1]) for shown in overloads)
    return any(len(shown[1]) >= step.args for shown in overloads)


def _overloads(
    doc: UiDocument, classes: QtClassTable, sender: str, signal_name: str, state: EventState
) -> Tuple[Tuple[str, Tuple[str, ...]], ...]:
    node = sender_node(doc, sender)
    if node is None:
        return ()
    class_name, declared = compat.node_class(doc, classes, node)
    signatures = list(compat.signals_of(classes, class_name, declared))
    signatures.extend(ref.signal for ref in state.native)
    return compat.overloads_of(signatures, signal_name)
