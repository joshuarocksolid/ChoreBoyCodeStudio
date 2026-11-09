"""The typed formula tree (CONTRACTS.md section 17.3).

Every node carries the span in the original text and the type the checker filled
in. ``tree`` is None when the text never became a formula.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet, Optional, Tuple, Union

from app.features.form_builder.engine.logic.formula.types import FType


@dataclass(frozen=True)
class Span:
    """Character offsets into the original formula text. ``end`` is exclusive."""

    start: int
    end: int


@dataclass(frozen=True)
class FormulaProblem:
    """One problem. ``fix_id`` names a ``Fix`` when a rewrite is offered."""

    code: str
    span: Span
    message: str
    fix_id: Optional[str] = None


@dataclass(frozen=True)
class Fix:
    """One Excel-habit rewrite. ``apply_fix`` splices ``replacement`` into ``span``."""

    fix_id: str
    span: Span
    message: str
    replacement: str


@dataclass(frozen=True)
class Lit:
    span: Span
    type: FType
    value: object


@dataclass(frozen=True)
class Ref:
    span: Span
    type: FType
    name: str


@dataclass(frozen=True)
class Attr:
    """``widget.text``, ``grid.selected.qty``, ``form.isNew``.

    ``sub`` is the third name when the chain is three long. Longer chains are rejected.
    """

    span: Span
    type: FType
    base: "Node"
    name: str
    sub: Optional[str] = None


@dataclass(frozen=True)
class Call:
    span: Span
    type: FType
    func: str
    args: Tuple["Node", ...]


@dataclass(frozen=True)
class WindowCall:
    span: Span
    type: FType
    method: str
    args: Tuple["Node", ...]


@dataclass(frozen=True)
class Unary:
    span: Span
    type: FType
    op: str
    x: "Node"


@dataclass(frozen=True)
class Bin:
    span: Span
    type: FType
    op: str
    a: "Node"
    b: "Node"


@dataclass(frozen=True)
class Bool:
    """``and`` / ``or``. The chain stays one node so blank rules see every operand."""

    span: Span
    type: FType
    op: str
    values: Tuple["Node", ...]


@dataclass(frozen=True)
class Compare:
    """A comparison chain. ``pairs`` is ``(op, right)`` in source order."""

    span: Span
    type: FType
    first: "Node"
    pairs: Tuple[Tuple[str, "Node"], ...]


@dataclass(frozen=True)
class IfElse:
    span: Span
    type: FType
    test: "Node"
    then: "Node"
    other: "Node"


@dataclass(frozen=True)
class ListLit:
    """A list or tuple of literals. Legal only on the right of ``in`` / ``not in``."""

    span: Span
    type: FType
    items: Tuple["Node", ...]


Node = Union[Lit, Ref, Attr, Call, WindowCall, Unary, Bin, Bool, Compare, IfElse, ListLit]


@dataclass(frozen=True)
class Analysis:
    """What ``analyze`` returns. ``bool_wraps`` are the spans M7.1b wraps in ``_cbcs_bool``."""

    text: str
    tree: Optional[Node]
    type: Optional[FType]
    problems: Tuple[FormulaProblem, ...]
    fixes: Tuple[Fix, ...]
    reads: FrozenSet[str]
    window_calls: Tuple[str, ...]
    bool_wraps: Tuple[Span, ...] = ()
