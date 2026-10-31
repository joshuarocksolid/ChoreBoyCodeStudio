"""The snapshot ``analyze`` reads (CONTRACTS.md section 17.5).

The caller builds one env per document revision. This module does not open a
document or the class table. The inheritance walk is a function the caller passes
in, so formula code stays free of that table's file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Mapping, Optional, Tuple

from app.features.form_builder.engine.commands.refs import FORMULA_NAMES, RESERVED_NAMES
from app.features.form_builder.engine.logic.formula.types import FType
from app.features.form_builder.engine.project.window_facts import MethodFacts


def _self_chain(class_name: str) -> Tuple[str, ...]:
    return (class_name,)


@dataclass(frozen=True)
class WidgetFacts:
    """What a formula needs to know about one widget. ``also`` is empty until M8."""

    class_name: str
    display: str = ""
    kind: str = ""
    decimals: int = 2
    prefix: str = ""
    tristate: bool = False
    allow_blank: bool = False
    has_items_data: bool = False
    pages: Tuple[str, ...] = ()
    also: Tuple[str, ...] = ()


@dataclass(frozen=True)
class SlotKind:
    """What the slot must hold. ``target`` is set for value, default, set, and range."""

    name: str
    target: Optional[FType] = None

    @staticmethod
    def condition() -> "SlotKind":
        return SlotKind("condition")

    @staticmethod
    def value(target: FType) -> "SlotKind":
        return SlotKind("value", target)

    @staticmethod
    def default(target: FType) -> "SlotKind":
        return SlotKind("default", target)

    @staticmethod
    def check() -> "SlotKind":
        return SlotKind("check")

    @staticmethod
    def when() -> "SlotKind":
        return SlotKind("when")

    @staticmethod
    def set(target: FType) -> "SlotKind":
        return SlotKind("set", target)

    @staticmethod
    def message() -> "SlotKind":
        return SlotKind("message")

    @staticmethod
    def range_bound(target: FType) -> "SlotKind":
        return SlotKind("range_bound", target)


YESNO_SLOTS = frozenset({"condition", "check", "when"})
VALUE_SLOTS = frozenset({"value", "default", "set", "range_bound"})


def reserved_names() -> frozenset:
    """Names a widget must not use, plus the function library."""
    return frozenset(RESERVED_NAMES | FORMULA_NAMES)


def is_reserved_word(name: str, reserved: frozenset) -> bool:
    return name in reserved or name.startswith("cbcs")


@dataclass(frozen=True)
class FormulaEnv:
    """Widgets, window methods, and the class-chain function. ``data`` is None until M8.

    ``returns`` holds each method's return annotation as source text (``bool``,
    ``int``, ``Decimal``, ``float``, ``str``, ``date``). ``MethodFacts`` does not
    store that string, so the env carries it beside the method.
    """

    widgets: Mapping[str, WidgetFacts]
    methods: Mapping[str, MethodFacts]
    reserved: frozenset
    data: Optional[object] = None
    class_chain: Callable[[str], Tuple[str, ...]] = _self_chain
    returns: Mapping[str, str] = field(default_factory=dict)
    class_name: str = "Window"
    window_file: str = "window.py"

    @staticmethod
    def for_test(
        widgets: Optional[Mapping[str, WidgetFacts]] = None,
        methods: Optional[Mapping[str, MethodFacts]] = None,
        *,
        data: Optional[object] = None,
        returns: Optional[Mapping[str, str]] = None,
        class_chain: Optional[Callable[[str], Tuple[str, ...]]] = None,
        class_name: str = "Window",
        window_file: str = "window.py",
        reserved: Optional[frozenset] = None,
    ) -> "FormulaEnv":
        """Build an env without a document. Tests and M7.1b use this."""
        return FormulaEnv(
            widgets=dict(widgets or ()),
            methods=dict(methods or ()),
            reserved=reserved if reserved is not None else reserved_names(),
            data=data,
            class_chain=class_chain or _self_chain,
            returns=dict(returns or ()),
            class_name=class_name,
            window_file=window_file,
        )

    def page_names(self) -> frozenset:
        found = []
        for facts in self.widgets.values():
            found.extend(facts.pages)
        return frozenset(found)
