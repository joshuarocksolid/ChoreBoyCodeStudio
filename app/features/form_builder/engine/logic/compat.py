"""Signal and slot compatibility (CONTRACTS section 15.6, UX-PICK-006). Qt-free.

A slot (or method) with parameter types *p* fits a signal overload with types
*s* when *p* is a prefix of *s* after normalising. The engine decides this; a
picker never asks Qt. Signatures come from the class table and, for a
promoted class, from its ``<customwidget><slots>`` declaration. Nothing here
imports or runs project code (UX-PICK-011).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Tuple

from app.features.form_builder.engine.ui4.defaults import QtClassTable
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import (
    ActionGroupNode,
    ActionNode,
    ButtonGroupNode,
    LayoutNode,
    Node,
    SpacerNode,
    WidgetNode,
)
from app.features.form_builder.engine.ui4.schema import SlotsDecl

_ALIASES = {"qreal": "double"}

#: How a type reads in a sentence (UX-PICK-006 "Type words").
_TYPE_WORDS = {
    "bool": "yes or no",
    "int": "a whole number",
    "double": "a number",
    "QString": "text",
    "QDate": "a date",
}


def split_signature(signature: str) -> Tuple[str, Tuple[str, ...]]:
    """``"valueChanged(int)"`` -> ``("valueChanged", ("int",))``. Types are normalised.

    A text without parentheses is a bare name with no parameters. Commas inside
    ``<...>`` do not split.
    """
    text = signature.strip()
    open_at = text.find("(")
    if open_at < 0:
        return text, ()
    name = text[:open_at].strip()
    close_at = text.rfind(")")
    inner = text[open_at + 1 : close_at if close_at > open_at else len(text)]
    return name, tuple(normalize_type(item) for item in _split_top_level(inner))


def normalize_type(text: str) -> str:
    """``const T&`` -> ``T``, whitespace removed, Qt 6 aliases (``qreal`` -> ``double``)."""
    value = text.strip()
    if value.startswith("const "):
        value = value[len("const ") :]
    if value.endswith("&"):
        value = value[:-1]
    value = re.sub(r"\s+", "", value)
    return _ALIASES.get(value, value)


def signature_text(name: str, params: Sequence[str]) -> str:
    """The signature the way Designer writes it: no spaces, Qt type names."""
    return "%s(%s)" % (name, ",".join(params))


def fits(slot_params: Sequence[str], signal_params: Sequence[str]) -> bool:
    """True when ``slot_params`` is a prefix of ``signal_params`` (both already normalised)."""
    if len(slot_params) > len(signal_params):
        return False
    return tuple(signal_params[: len(slot_params)]) == tuple(slot_params)


def overloads_of(signatures: Iterable[str], signal_name: str) -> Tuple[Tuple[str, Tuple[str, ...]], ...]:
    """Every ``(signature, params)`` of ``signal_name`` in ``signatures``, in order, once each."""
    found: List[Tuple[str, Tuple[str, ...]]] = []
    seen = set()
    for item in signatures:
        name, params = split_signature(item)
        if name != signal_name:
            continue
        text = signature_text(name, params)
        if text in seen:
            continue
        seen.add(text)
        found.append((text, params))
    return tuple(found)


def widest_overload(overloads: Sequence[Tuple[str, Tuple[str, ...]]]) -> Optional[Tuple[str, Tuple[str, ...]]]:
    """The overload with the most arguments; the first of equals (a step list's own overload)."""
    best = None
    for item in overloads:
        if best is None or len(item[1]) > len(best[1]):
            best = item
    return best


def narrowest_covering(
    overloads: Sequence[Tuple[str, Tuple[str, ...]]],
    slot_params: Sequence[str],
    min_args: int = 0,
) -> Optional[Tuple[str, Tuple[str, ...]]]:
    """The overload with the fewest arguments that covers the step (CONTRACTS 15.6 rule 2).

    Covers means ``slot_params`` is a prefix and the overload has at least
    ``min_args`` arguments (a ``call`` step's ``args``). The first of equals wins.
    """
    best = None
    for item in overloads:
        if len(item[1]) < min_args or not fits(slot_params, item[1]):
            continue
        if best is None or len(item[1]) < len(best[1]):
            best = item
    return best


@dataclass(frozen=True)
class SlotFit:
    """Whether a slot can be picked for an event, and why not."""

    ok: bool
    reason: str = ""


def slot_fit(slot_signature: str, overloads: Sequence[Tuple[str, Tuple[str, ...]]], event_words: str) -> SlotFit:
    """UX-PICK-006: a slot fits when it fits one overload. The reason is the grey second line."""
    _name, params = split_signature(slot_signature)
    for _text, signal_params in overloads:
        if fits(params, signal_params):
            return SlotFit(True)
    widest = widest_overload(overloads)
    sends = widest[1] if widest is not None else ()
    return SlotFit(
        False,
        "Needs %s; %s sends %s." % (type_words(params), event_words, type_words(sends) if sends else "nothing"),
    )


def type_words(types: Sequence[str]) -> str:
    """``("bool",)`` -> ``"yes or no"``; several types are joined with "and"."""
    words = [_TYPE_WORDS.get(item, item) for item in types]
    if not words:
        return "nothing"
    if len(words) == 1:
        return words[0]
    return ", ".join(words[:-1]) + " and " + words[-1]


# --- reading signals and slots off an object of the form --------------------------------


def node_class(doc: UiDocument, classes: QtClassTable, node: Node) -> Tuple[str, Optional[SlotsDecl]]:
    """``(table class, declared signals and slots)`` of an object.

    A promoted class resolves to its ``extends`` base for the table and brings the
    declaration of its ``<customwidget>``. Actions, action groups and button
    groups are their Qt class. Layouts and spacers have no events (UX D23): the
    result is ``("", None)``.
    """
    if isinstance(node, ActionNode):
        return "QAction", None
    if isinstance(node, ActionGroupNode):
        return "QActionGroup", None
    if isinstance(node, ButtonGroupNode):
        return "QButtonGroup", None
    if isinstance(node, (LayoutNode, SpacerNode)) or not isinstance(node, WidgetNode):
        return "", None
    class_name = node.class_name
    custom = doc.custom_widget(class_name)
    declared = None
    extends = None
    if custom is not None:
        value = custom.field("extends")
        extends = value if isinstance(value, str) else None
        slots = custom.field("slots")
        declared = slots if isinstance(slots, SlotsDecl) else None
    return classes.effective_class(class_name, extends), declared


def signals_of(classes: QtClassTable, class_name: str, declared: Optional[SlotsDecl]) -> Tuple[str, ...]:
    """Every signal signature of an object: its class chain's, then its own declared ones."""
    found = list(classes.signals(class_name)) if class_name else []
    if declared is not None:
        found.extend(declared.signals)
    return tuple(found)


def slots_of(classes: QtClassTable, class_name: str, declared: Optional[SlotsDecl]) -> Tuple[str, ...]:
    """Every slot signature of an object: its class chain's, then its own declared ones."""
    found = list(classes.slots(class_name)) if class_name else []
    if declared is not None:
        found.extend(declared.slots)
    return tuple(found)


def _split_top_level(text: str) -> List[str]:
    parts: List[str] = []
    depth = 0
    current: List[str] = []
    for char in text:
        if char == "<":
            depth += 1
        elif char == ">":
            depth = max(0, depth - 1)
        if char == "," and depth == 0:
            parts.append("".join(current))
            current = []
            continue
        current.append(char)
    tail = "".join(current)
    if tail.strip() or parts:
        parts.append(tail)
    return [item for item in parts if item.strip()]
