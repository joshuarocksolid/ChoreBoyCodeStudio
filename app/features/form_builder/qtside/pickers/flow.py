"""The event and step picker pages. Qt-free: a press returns the next page, a commit, or closed.

Nothing here calls the log. The widget does, and only for a commit.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Optional, Sequence, Tuple

from app.features.form_builder.engine.logic import compat
from app.features.form_builder.engine.logic.events import declared_methods, read_event, sender_node
from app.features.form_builder.engine.logic.events_catalog import (
    class_chain,
    common_events,
    event_words,
    more_events,
    step_words,
    value_words,
)
from app.features.form_builder.engine.logic.events_codec import slot_step
from app.features.form_builder.engine.logic.intents.m6 import IntentSpec, default_target, intents_for, target_candidates
from app.features.form_builder.engine.project.handler_names import suggest_method_name, value_param
from app.features.form_builder.engine.query.tree import reading_order
from app.features.form_builder.engine.ui4.defaults import QtClassTable
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.qtside.inspector.behavior_ext._rows import Gesture, display_name, dropped_count, friendly_class

_BASES = ("QWidget", "QObject")


@dataclass(frozen=True)
class PickerSource:
    """Who the picker is for. A signal means add a step to that event; empty means pick the event."""

    sender: str
    signal: str = ""
    replace_index: int = -1
    changing: str = ""

    @staticmethod
    def parse(source: object) -> "PickerSource":
        if isinstance(source, PickerSource):
            return source
        return PickerSource(str(source))


@dataclass(frozen=True)
class Item:
    kind: str
    payload: str
    text: str
    faint: str = ""
    note: str = ""
    enabled: bool = True
    header: bool = False


@dataclass(frozen=True)
class Page:
    kind: str
    title: str
    filter: str
    current: int
    rows: Tuple[Item, ...]
    check: str
    checked: bool
    field: str
    notice: str
    signal: str
    intent_id: str
    picked_target: str
    wide: bool
    replace_index: int
    back: str


@dataclass(frozen=True)
class Commit:
    gesture: Gesture


@dataclass(frozen=True)
class Closed:
    pass


@dataclass(frozen=True)
class Press:
    key: str
    text: str = ""


@dataclass(frozen=True)
class PickContext:
    doc: UiDocument
    classes: QtClassTable
    source: PickerSource
    target: str
    methods: Tuple[str, ...]
    window_file: str
    window_class: str
    show_base: bool
    taken: Tuple[str, ...] = ()
    inherited: Tuple[str, ...] = ()


def opening(ctx: PickContext) -> Page:
    source = ctx.source
    if source.changing:
        return _event_page(ctx, "")
    if source.signal and ctx.target:
        return _pair_page(ctx, source.signal, source.replace_index, "")
    if source.signal:
        return _step_page(ctx, source.signal, wide=False, replace_index=source.replace_index, back="")
    return _event_page(ctx, "")


def reduce(ctx: PickContext, page: Page, press: Press) -> object:
    """The next page, a ``Commit``, or ``Closed``. Esc on the first page is ``Closed``."""
    key = press.key
    if key == "esc":
        if not page.back:
            return Closed()
        return _go_back(ctx, page)
    if key == "toggle":
        return _retarget(ctx, replace(page, checked=not page.checked, filter=page.filter))
    if key == "type":
        return _retarget(ctx, replace(page, filter=page.filter + press.text, current=0))
    if key == "backspace":
        if page.filter:
            return _retarget(ctx, replace(page, filter=page.filter[:-1], current=0))
        return _go_back(ctx, page) if page.back else page
    if key == "left":
        if page.filter:
            return page
        return _go_back(ctx, page) if page.back else page
    if key == "up":
        return replace(page, current=_move(page, -1))
    if key == "down":
        return replace(page, current=_move(page, 1))
    if key == "field":
        return replace(page, field=press.text, notice=_method_notice(ctx, page, press.text))
    if key == "enter" or key == "right":
        return _enter(ctx, page)
    if key == "filter":
        return _retarget(ctx, replace(page, filter=press.text))
    if key == "check":
        return _retarget(ctx, replace(page, checked=press.text == "1"))
    return page


def _enter(ctx: PickContext, page: Page) -> object:
    item = _current(page)
    if item is None or item.header or not item.enabled:
        return page
    if page.kind == "confirm":
        if item.kind == "confirm-yes":
            return Commit(Gesture("change_event", signal=page.signal, new_signal=item.payload))
        return _event_page(ctx, page.filter)
    if item.kind == "event":
        return _picked_event(ctx, page, item.payload)
    if item.kind == "intent":
        return _picked_intent(ctx, page, item.payload)
    if item.kind == "new-method":
        return _method_page(ctx, page)
    if item.kind == "method":
        return Commit(Gesture("add_call", signal=page.signal, method=item.payload, args=0))
    if item.kind == "widget-action":
        return _target_page(ctx, page, "", "Which widget?", "slots")
    if item.kind == "target":
        if page.intent_id == "slots":
            return _slots_page(ctx, page, item.payload)
        return Commit(
            Gesture(
                "add_intent",
                signal=page.signal,
                intent_id=page.intent_id,
                target=item.payload,
                index=page.replace_index,
            )
        )
    if item.kind == "slot":
        if page.replace_index >= 0:
            return Commit(
                Gesture(
                    "replace_slot",
                    signal=page.signal,
                    index=page.replace_index,
                    target=page.picked_target,
                    slot=item.payload,
                )
            )
        return Commit(Gesture("add_slot", signal=page.signal, target=page.picked_target, slot=item.payload))
    if item.kind == "make":
        return Commit(
            Gesture(
                "add_call",
                signal=page.signal,
                method=page.field.strip(),
                args=1 if page.checked else 0,
            )
        )
    return page


def _picked_event(ctx: PickContext, page: Page, signal: str) -> object:
    source = ctx.source
    if source.changing:
        dropped = dropped_count(ctx.doc, ctx.classes, source.sender, source.changing, signal)
        if dropped:
            chain = _sender_chain(ctx)
            words = event_words(signal, chain).header
            sentence = "%d steps can't run on %s and will be removed." % (dropped, words)
            rows = (
                Item("notice", "", sentence, header=True),
                Item("confirm-yes", signal, "Change event"),
                Item("confirm-no", "", "Cancel"),
            )
            return Page(
                "confirm", "Change event", "", 1, rows, "", False, "", sentence,
                source.changing, "", "", False, -1, "event",
            )
        return Commit(Gesture("change_event", signal=source.changing, new_signal=signal))
    if ctx.target:
        return _pair_page(ctx, signal, -1, "event")
    return _step_page(ctx, signal, wide=True, replace_index=-1, back="event")


def _picked_intent(ctx: PickContext, page: Page, intent_id: str) -> object:
    spec = _intent(ctx, intent_id)
    if spec is None:
        return page
    if spec.needs_target:
        title = spec.target_title or "Which widget?"
        nxt = _target_page(ctx, page, intent_id, title, intent_id)
        if spec.intent_id == "next-field":
            start = default_target(ctx.doc, spec, ctx.source.sender) or ""
            if start:
                nxt = _select(nxt, start)
        return nxt
    return Commit(Gesture("add_intent", signal=page.signal, intent_id=intent_id, index=page.replace_index))


def _go_back(ctx: PickContext, page: Page) -> object:
    if page.back == "event":
        return _event_page(ctx, "")
    if page.back == "step":
        if ctx.target:
            return _pair_page(ctx, page.signal, page.replace_index, "event" if not ctx.source.signal else "")
        return _step_page(ctx, page.signal, page.wide, page.replace_index, "event" if page.wide else "")
    if page.back == "target":
        return _target_page(ctx, page, page.intent_id, "Which widget?", page.intent_id)
    if not page.back:
        return Closed()
    return Closed()


def _retarget(ctx: PickContext, page: Page) -> Page:
    """Rebuild the rows for a new filter or check, keeping the page's place."""
    if page.kind == "event":
        built = _event_page(ctx, page.filter, page.checked)
        return replace(built, current=_keep(page, built))
    if page.kind == "step":
        built = _step_page(ctx, page.signal, page.wide, page.replace_index, page.back, page.filter)
        return replace(built, current=_keep(page, built))
    if page.kind == "pair":
        built = _pair_page(ctx, page.signal, page.replace_index, page.back, page.filter, page.checked)
        return replace(built, current=_keep(page, built))
    if page.kind == "target":
        built = _target_page(ctx, page, page.intent_id, page.title, page.intent_id, page.filter)
        return replace(built, current=_keep(page, built))
    if page.kind == "slots":
        built = _slots_page(ctx, page, page.picked_target, page.filter, page.checked)
        return replace(built, current=_keep(page, built))
    return page


def _event_page(ctx: PickContext, text: str, show_base: Optional[bool] = None) -> Page:
    checked = ctx.show_base if show_base is None else show_base
    chain = _sender_chain(ctx)
    class_name = chain[0] if chain else ""
    declared = _declared_signals(ctx)
    rows = [Item("header", "", "COMMON", header=True)]
    for name in common_events(ctx.classes, class_name, declared):
        rows.append(_event_item(name, chain))
    rows.append(Item("header", "", "MORE EVENTS", header=True))
    extra = list(more_events(ctx.classes, class_name, declared))
    if checked:
        extra.extend(_base_names(ctx.classes, class_name, "signals"))
    seen = {item.payload for item in rows}
    for name in sorted(set(extra)):
        if name and name not in seen:
            rows.append(_event_item(name, chain))
            seen.add(name)
    title = "When\u2026 (%s \u00b7 %s)" % (display_name(ctx.doc, ctx.source.sender), friendly_class(class_name))
    page = Page("event", title, text, 0, _filter(tuple(rows), text), "Show events from QWidget and QObject", checked, "", "", "", "", "", False, -1, "")
    default = _default_signal(ctx)
    return _select(page, default) if default else _select_first(page)


def _step_page(
    ctx: PickContext, signal: str, wide: bool, replace_index: int, back: str, text: str = ""
) -> Page:
    rows = _intent_rows(ctx, signal if not wide else None)
    rows.extend(_code_rows(ctx, signal))
    rows.append(Item("header", "", "EVERYTHING ELSE", header=True))
    rows.append(Item("widget-action", "", "A widget's own action\u2026"))
    chain = _sender_chain(ctx)
    header = event_words(signal, chain).header
    title = "Then\u2026 (When %s is %s)" % (display_name(ctx.doc, ctx.source.sender), header)
    page = Page(
        "step", title, text, 0, _filter(tuple(rows), text, keep=("widget-action",)),
        "", False, "", "", signal, "", "", wide, replace_index, back,
    )
    return _select_first(page)


def _pair_page(
    ctx: PickContext, signal: str, replace_index: int, back: str, text: str = "", show_base: Optional[bool] = None
) -> Page:
    checked = ctx.show_base if show_base is None else show_base
    rows = [item for item in _intent_rows(ctx, signal) if item.header or _intent_fits_target(ctx, item.payload)]
    rows.extend(_slot_items(ctx, signal, ctx.target, checked))
    chain = _sender_chain(ctx)
    header = event_words(signal, chain).header
    title = "Then\u2026 (When %s is %s)" % (display_name(ctx.doc, ctx.source.sender), header)
    page = Page(
        "pair", title, text, 0, _filter(tuple(rows), text),
        "Show actions from QWidget and QObject", checked, "", "",
        signal, "", ctx.target, False, replace_index, back,
    )
    return _select_first(page)


def _target_page(
    ctx: PickContext, page: Page, intent_id: str, title: str, marker: str, text: str = ""
) -> Page:
    spec = _intent(ctx, intent_id) if intent_id and intent_id != "slots" else None
    names = target_candidates(ctx.doc, ctx.classes, spec, ctx.source.sender) if spec is not None else _widget_names(ctx)
    rows = []
    for name in names:
        rows.append(Item("target", name, _target_line(ctx, name)))
    built = Page(
        "target", title, text, 0, _filter(tuple(rows), text),
        "", False, "", "", page.signal, marker, "", page.wide, page.replace_index, "step",
    )
    return _select_first(built)


def _slots_page(
    ctx: PickContext, page: Page, target: str, text: str = "", show_base: Optional[bool] = None
) -> Page:
    checked = ctx.show_base if show_base is None else show_base
    title = "Everything %s can do" % display_name(ctx.doc, target)
    rows = _slot_items(ctx, page.signal, target, checked)
    built = Page(
        "slots", title, text, 0, _filter(tuple(rows), text),
        "Show actions from QWidget and QObject", checked, "", "",
        page.signal, "", target, page.wide, page.replace_index, "target",
    )
    return _select_first(built)


def _method_page(ctx: PickContext, page: Page) -> Page:
    chain = _sender_chain(ctx)
    class_name = chain[0] if chain else ""
    node = sender_node(ctx.doc, ctx.source.sender)
    text = ""
    if node is not None:
        from app.features.form_builder.engine.query.actions import text_of

        text = text_of(node)
    suggested = suggest_method_name(
        class_name=class_name,
        object_name=ctx.source.sender,
        text=text,
        signal=page.signal,
        form_class=ctx.doc.form_class_name(),
        taken=ctx.taken or ctx.methods,
        inherited=ctx.inherited,
    )
    sends = _sends(ctx, page.signal)
    check = ""
    if sends:
        check = "My method receives %s" % value_words(sends[0], page.signal, chain)
    notice = _method_line(ctx, suggested)
    return Page(
        "method", "Call a new method\u2026", "", 0,
        (Item("make", suggested, "Add %s()" % suggested),),
        check, False, suggested, notice, page.signal, "", "", page.wide, page.replace_index, "step",
    )


def _intent_rows(ctx: PickContext, event: Optional[str]) -> list:
    specs = intents_for(ctx.doc, ctx.classes, ctx.source.sender, event)
    rows = []
    if specs:
        rows.append(Item("header", "", "DO THIS", header=True))
        for spec in specs:
            rows.append(Item("intent", spec.intent_id, spec.words))
    return rows


def _code_rows(ctx: PickContext, signal: str) -> list:
    rows = [Item("header", "", "YOUR CODE", header=True), Item("new-method", "", "Call a new method\u2026")]
    if not ctx.window_file and not ctx.methods:
        rows.append(Item("header", "", "This form isn't in a project, so it has no window file.", header=True))
        return rows
    file_name = ctx.window_file or "the window file"
    rows.append(Item("header", "", "METHODS IN %s" % file_name, header=True))
    if not ctx.methods:
        return rows
    used = _used_methods(ctx, signal)
    sends = len(_sends(ctx, signal))
    for name in ctx.methods:
        mark = " already here" if name in used else ""
        rows.append(Item("method", name, "Call %s()%s" % (name, mark)))
    del sends
    return rows


def _slot_items(ctx: PickContext, signal: str, target: str, show_base: bool) -> list:
    node = sender_node(ctx.doc, target)
    if node is None:
        return []
    class_name, declared = compat.node_class(ctx.doc, ctx.classes, node)
    chain = class_chain(ctx.classes, class_name)
    sender_chain = _sender_chain(ctx)
    header = event_words(signal, sender_chain).header
    overloads = _overloads(ctx, signal)
    names = _slot_names(ctx.classes, class_name, declared, show_base)
    rows = [Item("header", "", "EVERYTHING %s CAN DO" % display_name(ctx.doc, target).upper(), header=True)]
    form = target == ctx.doc.root.object_name
    for signature in names:
        fit = compat.slot_fit(signature, overloads, header)
        label = step_words(
            slot_step(target, signature),
            display_name(ctx.doc, target),
            is_form=form,
            target_chain=chain,
        )
        rows.append(Item("slot", signature, label, faint=signature, note="" if fit.ok else fit.reason, enabled=fit.ok))
    return rows


def _event_item(name: str, chain: Sequence[str]) -> Item:
    words = event_words(name, chain)
    text = words.header if words.header != name else name
    return Item("event", name, text, faint=name + "()")


def _filter(rows: Tuple[Item, ...], text: str, keep: Tuple[str, ...] = ()) -> Tuple[Item, ...]:
    needle = text.strip().casefold()
    if not needle:
        return rows
    found = []
    pending = None
    for item in rows:
        if item.header:
            pending = item
            continue
        hay = " ".join((item.text, item.faint, item.payload)).casefold()
        if needle in hay or item.kind in keep:
            if pending is not None:
                found.append(pending)
                pending = None
            found.append(item)
        else:
            pending = None
    if not any(not item.header for item in found):
        sentence = "Nothing matches \u201c%s\u201d." % text
        extra = [item for item in rows if item.kind in keep]
        return tuple([Item("header", "", sentence, header=True)] + extra)
    return tuple(found)


def _current(page: Page) -> Optional[Item]:
    if 0 <= page.current < len(page.rows):
        return page.rows[page.current]
    return None


def _move(page: Page, direction: int) -> int:
    count = len(page.rows)
    if count == 0:
        return 0
    index = page.current
    for _ in range(count):
        index = (index + direction) % count
        item = page.rows[index]
        if not item.header:
            return index
    return page.current


def _select_first(page: Page) -> Page:
    for index, item in enumerate(page.rows):
        if not item.header and item.enabled:
            return replace(page, current=index)
    return page


def _select(page: Page, payload: str) -> Page:
    for index, item in enumerate(page.rows):
        if item.payload == payload and not item.header:
            return replace(page, current=index)
    return _select_first(page)


def _keep(previous: Page, built: Page) -> int:
    item = _current(previous)
    if item is not None:
        for index, other in enumerate(built.rows):
            if other.kind == item.kind and other.payload == item.payload:
                return index
    return _select_first(built).current


def _intent(ctx: PickContext, intent_id: str) -> Optional[IntentSpec]:
    for spec in intents_for(ctx.doc, ctx.classes, ctx.source.sender):
        if spec.intent_id == intent_id:
            return spec
    return None


def _intent_fits_target(ctx: PickContext, intent_id: str) -> bool:
    spec = _intent(ctx, intent_id)
    if spec is None:
        return False
    if not spec.needs_target:
        return True
    return ctx.target in target_candidates(ctx.doc, ctx.classes, spec, ctx.source.sender)


def _sender_chain(ctx: PickContext) -> Tuple[str, ...]:
    node = sender_node(ctx.doc, ctx.source.sender)
    if node is None:
        return ()
    class_name, _declared = compat.node_class(ctx.doc, ctx.classes, node)
    return class_chain(ctx.classes, class_name)


def _declared_signals(ctx: PickContext) -> Tuple[str, ...]:
    node = sender_node(ctx.doc, ctx.source.sender)
    if node is None:
        return ()
    _class_name, declared = compat.node_class(ctx.doc, ctx.classes, node)
    return declared.signals if declared is not None else ()


def _default_signal(ctx: PickContext) -> str:
    chain = _sender_chain(ctx)
    if not chain:
        return ""
    from app.features.form_builder.engine.logic.events_catalog import default_event

    return default_event(ctx.classes, chain[0]) or ""


def _sends(ctx: PickContext, signal: str) -> Tuple[str, ...]:
    overloads = _overloads(ctx, signal)
    if not overloads:
        return ()
    widest = max(overloads, key=lambda item: len(item[1]))
    return widest[1]


def _overloads(ctx: PickContext, signal: str) -> Tuple[Tuple[str, Tuple[str, ...]], ...]:
    node = sender_node(ctx.doc, ctx.source.sender)
    if node is None:
        return ()
    class_name, declared = compat.node_class(ctx.doc, ctx.classes, node)
    state = read_event(ctx.doc, ctx.source.sender, signal)
    signatures = list(compat.signals_of(ctx.classes, class_name, declared))
    signatures.extend(ref.signal for ref in state.native)
    return compat.overloads_of(signatures, signal)


def _base_names(classes: QtClassTable, class_name: str, kind: str) -> Tuple[str, ...]:
    names = []
    started = False
    for info in classes.chain(class_name):
        if info.name in _BASES:
            started = True
        if not started:
            continue
        signatures = classes.signals(info.name) if kind == "signals" else classes.slots(info.name)
        parent = classes.class_info(info.name)
        inherited = set()
        if parent is not None and parent.super_name:
            inherited = set(classes.signals(parent.super_name) if kind == "signals" else classes.slots(parent.super_name))
        for signature in signatures:
            if signature in inherited:
                continue
            names.append(compat.split_signature(signature)[0] if kind == "signals" else signature)
    return tuple(names)


def _slot_names(classes: QtClassTable, class_name: str, declared: object, show_base: bool) -> Tuple[str, ...]:
    all_slots = list(compat.slots_of(classes, class_name, declared))  # type: ignore[arg-type]
    if show_base:
        return tuple(dict.fromkeys(all_slots))
    hidden = set()
    for base in _BASES:
        hidden.update(classes.slots(base))
    return tuple(item for item in dict.fromkeys(all_slots) if item not in hidden)


def _widget_names(ctx: PickContext) -> Tuple[str, ...]:
    ordered = list(reading_order(ctx.doc))
    root = ctx.doc.root.object_name
    if root and root not in ordered:
        ordered.insert(0, root)
    return tuple(name for name in ordered if name and name != ctx.source.sender)


def _target_line(ctx: PickContext, name: str) -> str:
    node = sender_node(ctx.doc, name)
    class_name = ""
    if node is not None:
        class_name, _declared = compat.node_class(ctx.doc, ctx.classes, node)
    friendly = friendly_class(class_name) if class_name else ""
    if name == ctx.doc.root.object_name:
        return "This form (%s)" % name
    return "%s (%s) \u00b7 %s" % (display_name(ctx.doc, name), name, friendly)


def _used_methods(ctx: PickContext, signal: str) -> set:
    state = read_event(ctx.doc, ctx.source.sender, signal)
    return {step.method for step in state.steps if step.verb == "call" and step.method}


def _method_notice(ctx: PickContext, page: Page, name: str) -> str:
    return _method_line(ctx, name, page.signal)


def _method_line(ctx: PickContext, name: str, signal: str = "") -> str:
    del signal
    if not compat.is_name(name):
        return "Use a method name like print_receipt: letters, digits and _, starting with a letter."
    if name in ctx.methods or name in declared_methods(ctx.doc):
        return "%s already has %s. This event will call it." % (ctx.window_class or "The window", name)
    file_name = ctx.window_file or "the window file"
    klass = ctx.window_class or ctx.doc.form_class_name()
    return "Adds %s() to %s in %s." % (name, klass, file_name)


def param_name(ctx: PickContext, signal: str) -> str:
    chain = _sender_chain(ctx)
    class_name = chain[0] if chain else ""
    return value_param(signal + "()", class_name)
