"""Rename a method inside one form document.

Open forms apply these commands through their command log, one undo step.
Closed forms pass ``rename_method_in_document`` to ``rewrite_forms``. A document
that does not name the method returns None, so the closed writer leaves the
file bytes alone.
"""

from __future__ import annotations

import io
import tokenize
from dataclasses import is_dataclass, replace
from typing import List, Optional, Tuple

from app.features.form_builder.engine.commands.log import CommandLog, SelectionSnapshot
from app.features.form_builder.engine.commands.catalog import SetFormSlots, SetLogic
from app.features.form_builder.engine.commands.catalog_ext.events import SetEventSteps
from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.logic.codec import parse_json, write_json
from app.features.form_builder.engine.logic.compat import signature_text, split_signature
from app.features.form_builder.engine.logic.events import read_events
from app.features.form_builder.engine.logic.events_codec import EventStep
from app.features.form_builder.engine.logic.refs import map_json_formulas
from app.features.form_builder.engine.logic.storage import FORMULA_KEYS
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.engine.ui4.schema import SlotsDecl
from app.features.form_builder.engine.ui4.values import CStringValue, StringValue


def method_rename_commands(doc: UiDocument, old: str, new: str) -> Tuple[object, ...]:
    """Commands that point steps, connections, slots and ``window.old`` at ``new``."""

    commands: List[object] = []
    for node in doc.iter_preorder():
        if not isinstance(node, WidgetNode):
            continue
        for key in FORMULA_KEYS:
            text = _stored(node, key)
            if not text:
                continue
            updated = _window_call(text, old, new)
            if updated != text:
                commands.append(SetLogic(node.id, key, updated))
        validate = _stored(node, "cbcsValidate")
        if validate:
            updated_json = _rewrite_json(validate, old, new)
            if updated_json != validate:
                commands.append(SetLogic(node.id, "cbcsValidate", updated_json))
    for state in read_events(doc):
        steps = tuple(_rename_step(step, old, new) for step in state.steps)
        if steps != state.steps:
            commands.append(SetEventSteps(state.sender, state.signal_name, steps))
    declared = doc.ui.field("form_slots")
    if isinstance(declared, SlotsDecl):
        slots: List[str] = []
        changed = False
        for signature in declared.slots:
            name, params = split_signature(signature)
            if name == old:
                signature = signature_text(new, params)
                changed = True
            slots.append(signature)
        if changed:
            commands.append(SetFormSlots(tuple(declared.signals), tuple(slots)))
    return tuple(commands)


def rename_method_in_document(doc: UiDocument, old: str, new: str) -> Optional[UiDocument]:
    """Rename ``old`` inside ``doc``. None when the form does not name it."""

    if not old or old == new:
        return None
    commands = method_rename_commands(doc, old, new)
    if not commands:
        return None
    log = CommandLog(
        doc,
        _allocator_after(doc),
        selection_provider=lambda: SelectionSnapshot((), None),
    )
    with log.transaction("Rename %s to %s" % (old, new)):
        for command in commands:
            log.execute(command)
    return doc


def _allocator_after(doc: UiDocument) -> IdAllocator:
    high = 1
    for node in doc.iter_preorder():
        high = max(high, int(node.id) + 1)
    return IdAllocator(high)


def _rename_step(step: EventStep, old: str, new: str) -> EventStep:
    method = step.method
    slot = step.slot
    when = step.when
    raw = step.raw
    changed = False
    if step.verb == "call" and method == old:
        method = new
        changed = True
    if slot:
        name, params = split_signature(slot)
        if name == old:
            slot = signature_text(new, params)
            changed = True
    if isinstance(when, str):
        updated = _window_call(when, old, new)
        if updated != when:
            when = updated
            changed = True
    if raw is not None:
        renamed = _rename_raw(raw, old, new)
        if renamed is not raw:
            raw = renamed
            changed = True
    if not changed:
        return step
    return replace(step, method=method, slot=slot, when=when, raw=raw)


def _rename_raw(raw: object, old: str, new: str) -> object:
    fields = getattr(raw, "fields", None)
    when = getattr(raw, "when", None)
    if not isinstance(fields, tuple):
        return raw
    updated_fields = []
    changed = False
    for key, value in fields:
        if key == "method" and value == old:
            value = new
            changed = True
        elif isinstance(value, str) and key in ("when", "formula"):
            rewritten = _window_call(value, old, new)
            if rewritten != value:
                value = rewritten
                changed = True
        updated_fields.append((key, value))
    new_when = _window_call(when, old, new) if isinstance(when, str) else when
    if new_when != when:
        changed = True
    if not changed:
        return raw
    if is_dataclass(raw):
        try:
            return replace(raw, fields=tuple(updated_fields), when=new_when)  # type: ignore[type-var]
        except TypeError:
            return raw
    return raw


def _window_call(text: str, old: str, new: str) -> str:
    """Replace ``window.old`` name tokens. ``rename_formula`` skips a name after a dot."""

    if not text or not old or old == new or "window" not in text:
        return text
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, SyntaxError, IndentationError):
        return text
    older = None
    previous = None
    chosen = []
    for token in tokens:
        if (
            token.type == tokenize.NAME
            and token.string == old
            and previous is not None
            and previous.type == tokenize.OP
            and previous.string == "."
            and older is not None
            and older.type == tokenize.NAME
            and older.string == "window"
        ):
            chosen.append(token)
        older = previous
        previous = token
    if not chosen:
        return text
    starts: List[int] = []
    offset = 0
    for line in text.split("\n"):
        starts.append(offset)
        offset += len(line) + 1
    pieces: List[Tuple[int, int]] = []
    for token in chosen:
        row, column = token.start
        end_row, end_column = token.end
        if row != end_row or row - 1 >= len(starts):
            return text
        begin = starts[row - 1] + column
        end = starts[row - 1] + end_column
        if text[begin:end] != token.string:
            return text
        pieces.append((begin, end))
    result = text
    for begin, end in sorted(pieces, reverse=True):
        result = result[:begin] + new + result[end:]
    return result


def _rewrite_json(text: str, old: str, new: str) -> str:
    parsed = parse_json(text)
    if parsed.error is not None or parsed.value is None:
        return text
    mapped = map_json_formulas(parsed.value, lambda formula: _window_call(formula, old, new))
    if mapped == parsed.value:
        return text
    return write_json(mapped)


def _stored(node: object, key: str) -> Optional[str]:
    try:
        value = node.value(key)  # type: ignore[attr-defined]
    except Exception:
        return None
    if isinstance(value, (StringValue, CStringValue)):
        return value.text
    return None
