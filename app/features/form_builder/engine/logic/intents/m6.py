"""The M6 intents (UX-PICK-004; LOGIC_DESIGN 3.1 without the rule intents, UX D4). Qt-free.

An intent is a picker line that means "when this happens, do that": it adds one
or two plain steps (a Qt slot on a widget or the form). The rule intents of M7.2
register beside these. The package that discovers intents is M6.0s's
(``engine/logic/intents/__init__.py``) discovers ``register(registry)``. ``IntentSpec`` is
this lane's richer record (target filters, dialog-only); ``register`` turns each into the
registry's ``Intent``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional, Tuple

from app.features.form_builder.engine.commands.catalog_ext.events import EventEdit, SetEventSteps, steps_added
from app.features.form_builder.engine.logic import compat
from app.features.form_builder.engine.logic.intents import Intent
from app.features.form_builder.engine.logic.events_catalog import class_chain, event_words, step_words
from app.features.form_builder.engine.logic.events_codec import EventStep, slot_step
from app.features.form_builder.engine.query.tree import effective_tab_order, reading_order, takes_tab_focus
from app.features.form_builder.engine.ui4.defaults import QtClassTable
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import WidgetNode

_BUTTON_OR_ACTION = ("QAbstractButton", "QAction")
_STEP_WIDGETS = ("QSlider", "QSpinBox", "QDial")


@dataclass(frozen=True)
class IntentEdit:
    """One step an intent adds: on which event of which object."""

    sender: str
    signal_name: str
    step: EventStep


@dataclass(frozen=True)
class IntentSpec:
    """``sender_classes``: the intent is offered to a sender whose class chain holds one of these.
    ``event``: the signal the intent attaches to ("" when it names its own events).
    ``target_slot``: what a target must have ("" when no target is needed).
    ``target_classes``: when set, a target's class chain must hold one of these.
    ``dialog_only``: offered only when the form's root is a dialog."""

    intent_id: str
    words: str
    sender_classes: Tuple[str, ...]
    event: str
    needs_target: bool = False
    target_slot: str = ""
    target_classes: Tuple[str, ...] = ()
    dialog_only: bool = False
    target_title: str = ""


def _event_of(intent: IntentSpecSpec, sender_chain: Tuple[str, ...]) -> str:
    if intent.event == "clicked" and "QAction" in sender_chain:
        return "triggered"
    return intent.event


INTENTS: Tuple[IntentSpec, ...] = (
    IntentSpec("close-form", "Close this form", _BUTTON_OR_ACTION, "clicked"),
    IntentSpec("accept", "Accept (OK)", _BUTTON_OR_ACTION, "clicked", dialog_only=True),
    IntentSpec("reject", "Cancel", _BUTTON_OR_ACTION, "clicked", dialog_only=True),
    IntentSpec(
        "clear-field", "Clear a field…", _BUTTON_OR_ACTION, "clicked",
        needs_target=True, target_slot="clear()", target_title="Clear which field?",
    ),
    IntentSpec(
        "move-focus", "Move focus to…", _BUTTON_OR_ACTION, "clicked",
        needs_target=True, target_slot="setFocus()", target_title="Move focus to which field?",
    ),
    IntentSpec(
        "check-same-way", "Check another box the same way…", ("QCheckBox",), "toggled",
        needs_target=True, target_slot="setChecked(bool)", target_classes=("QCheckBox",),
        target_title="Which widget?",
    ),
    IntentSpec(
        "next-field", "Go to the next field when Enter is pressed…", ("QLineEdit",), "returnPressed",
        needs_target=True, target_slot="setFocus()", target_title="Move focus to which field?",
    ),
    IntentSpec(
        "show-page", "Show the matching page of…", ("QComboBox",), "currentIndexChanged",
        needs_target=True, target_slot="setCurrentIndex(int)",
        target_classes=("QTabWidget", "QStackedWidget"), target_title="Which widget?",
    ),
    IntentSpec(
        "keep-in-step", "Keep another one in step…", _STEP_WIDGETS, "valueChanged",
        needs_target=True, target_slot="setValue(int)", target_classes=_STEP_WIDGETS,
        target_title="Which widget?",
    ),
    IntentSpec("buttons-accept-reject", "OK accepts, Cancel closes", ("QDialogButtonBox",), "", dialog_only=True),
)


def _plain_steps(spec: IntentSpec):  # type: ignore[no-untyped-def]
    """The registry's ``steps(sender, target)``: mappings of the logic schema, each with its ``event``.
    A step with no ``target`` key acts on the form."""

    def steps(sender: str, target: Optional[str]) -> Tuple[Mapping[str, Any], ...]:
        form = {"close-form": "close()", "accept": "accept()", "reject": "reject()"}
        if spec.intent_id in form:
            return ({"do": "slot", "slot": form[spec.intent_id], "event": spec.event},)
        if spec.intent_id == "buttons-accept-reject":
            return (
                {"do": "slot", "slot": "accept()", "event": "accepted"},
                {"do": "slot", "slot": "reject()", "event": "rejected"},
            )
        if target is None:
            return ()
        if spec.intent_id == "keep-in-step":
            return (
                {"do": "slot", "target": target, "slot": "setValue(int)", "event": "valueChanged"},
                {"do": "slot", "target": sender, "slot": "setValue(int)", "event": "valueChanged", "sender": target},
            )
        return ({"do": "slot", "target": target, "slot": spec.target_slot, "event": spec.event},)

    return steps


def register(registry: object) -> None:
    """Register the M6 intents with ``engine/logic/intents`` (M6.0s)."""
    add = getattr(registry, "add", None)
    if add is None:
        return
    for spec in INTENTS:
        add(
            Intent(
                spec.intent_id,
                spec.words,
                _plain_steps(spec),
                sender_classes=spec.sender_classes,
                event=spec.event,
                needs_target=spec.needs_target,
            )
        )


def _sender_chain(doc: UiDocument, classes: QtClassTable, sender: str) -> Tuple[str, ...]:
    found = doc.by_name(sender)
    if not found:
        return ()
    class_name, _declared = compat.node_class(doc, classes, doc.node(found[0]))
    return class_chain(classes, class_name)


def _root_is_dialog(doc: UiDocument, classes: QtClassTable) -> bool:
    return "QDialog" in class_chain(classes, compat.node_class(doc, classes, doc.root)[0])


def intents_for(
    doc: UiDocument, classes: QtClassTable, sender: str, event: Optional[str] = None
) -> Tuple[IntentSpec, ...]:
    """The intents offered for ``sender``, in table order.

    From "+ Then…" (``event`` given) only intents of that event are listed; from
    "+ When…" (``event`` None) every intent of the sender is.
    """
    chain = _sender_chain(doc, classes, sender)
    if not chain:
        return ()
    dialog = _root_is_dialog(doc, classes)
    found = []
    for intent in INTENTS:
        if not any(name in chain for name in intent.sender_classes):
            continue
        if intent.dialog_only and not dialog:
            continue
        if event is not None and _event_of(intent, chain) != event:
            continue
        found.append(intent)
    return tuple(found)


def target_candidates(doc: UiDocument, classes: QtClassTable, intent: IntentSpec, sender: str) -> Tuple[str, ...]:
    """Object names that fit the intent's target page (UX-PICK-005): reading order, the form first when it fits."""
    if not intent.needs_target:
        return ()
    names = []
    root = doc.root.object_name
    ordered = [root] + [name for name in _all_widget_names(doc) if name != root]
    for name in ordered:
        if name == sender:
            continue
        found = doc.by_name(name)
        if not found:
            continue
        node = doc.node(found[0])
        class_name, declared = compat.node_class(doc, classes, node)
        chain = class_chain(classes, class_name)
        if intent.target_classes and not any(item in chain for item in intent.target_classes):
            continue
        slots = [compat.signature_text(*_split(item)) for item in compat.slots_of(classes, class_name, declared)]
        if intent.target_slot not in slots:
            continue
        if intent.target_slot == "setFocus()":
            if not isinstance(node, WidgetNode) or name == root or not takes_tab_focus(node):
                continue
        names.append(name)
    return tuple(names)


def default_target(doc: UiDocument, intent: IntentSpec, sender: str) -> Optional[str]:
    """The target page starts on the next field in tab order (UX-PICK-004 "next field")."""
    if intent.intent_id != "next-field":
        return None
    order = effective_tab_order(doc)
    if sender not in order:
        return None
    index = order.index(sender)
    return order[index + 1] if index + 1 < len(order) else None


def edits(doc: UiDocument, classes: QtClassTable, intent: IntentSpec, sender: str, target: Optional[str] = None) -> Tuple[IntentEdit, ...]:
    """The plain steps an intent adds, each on its event."""
    chain = _sender_chain(doc, classes, sender)
    root = doc.root.object_name
    event = _event_of(intent, chain)
    if intent.intent_id == "close-form":
        return (IntentEdit(sender, event, slot_step(root, "close()")),)
    if intent.intent_id == "accept":
        return (IntentEdit(sender, event, slot_step(root, "accept()")),)
    if intent.intent_id == "reject":
        return (IntentEdit(sender, event, slot_step(root, "reject()")),)
    if intent.intent_id == "buttons-accept-reject":
        return (
            IntentEdit(sender, "accepted", slot_step(root, "accept()")),
            IntentEdit(sender, "rejected", slot_step(root, "reject()")),
        )
    if target is None:
        raise ValueError("%s needs a target" % intent.intent_id)
    if intent.intent_id == "keep-in-step":
        return (
            IntentEdit(sender, "valueChanged", slot_step(target, "setValue(int)")),
            IntentEdit(target, "valueChanged", slot_step(sender, "setValue(int)")),
        )
    return (IntentEdit(sender, event, slot_step(target, intent.target_slot)),)


def command(
    doc: UiDocument,
    classes: QtClassTable,
    intent: IntentSpec,
    sender: str,
    target: Optional[str] = None,
    display: Callable[[str], str] = lambda name: name,
) -> SetEventSteps:
    """One ``SetEventSteps`` (one undo step, named per UX 13.3.8) that adds the intent's steps after the current ones."""
    planned = edits(doc, classes, intent, sender, target)
    first, rest = planned[0], planned[1:]
    base = steps_added(doc, first.sender, first.signal_name, (first.step,))
    also = []
    for edit in rest:
        current = steps_added(doc, edit.sender, edit.signal_name, (edit.step,))
        also.append(EventEdit(edit.sender, edit.signal_name, current.steps))
    caption = _caption(doc, classes, intent, planned, display)
    return SetEventSteps(base.sender, base.signal_name, base.steps, caption=caption, also=tuple(also))


def _caption(
    doc: UiDocument, classes: QtClassTable, intent: IntentSpec, planned: Tuple[IntentEdit, ...], display: Callable[[str], str]
) -> str:
    if intent.intent_id == "keep-in-step":
        return "Keep %s and %s in step" % (display(planned[0].sender), display(planned[1].sender))
    if intent.intent_id == "buttons-accept-reject":
        return "Make OK accept and Cancel close"
    edit = planned[0]
    chain = _sender_chain(doc, classes, edit.sender)
    target = edit.step.target
    target_chain: Tuple[str, ...] = ()
    found = doc.by_name(target)
    if found:
        target_chain = class_chain(classes, compat.node_class(doc, classes, doc.node(found[0]))[0])
    words = step_words(edit.step, display(target), is_form=(target == doc.root.object_name), target_chain=target_chain)
    return "Add %s to %s %s" % (words, display(edit.sender), event_words(edit.signal_name, chain).header)


def _split(signature: str) -> Tuple[str, Tuple[str, ...]]:
    return compat.split_signature(signature)


def _all_widget_names(doc: UiDocument) -> Tuple[str, ...]:
    ordered = list(reading_order(doc))
    for widget in doc.iter_widgets():
        if widget.object_name and widget.object_name not in ordered:
            ordered.append(widget.object_name)
    return tuple(ordered)
