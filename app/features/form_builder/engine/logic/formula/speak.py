"""One speaker for a formula tree. The builder and Read as text both call this.

Empty when the builder would refuse the shape. The phrase tables are the ones
the builder menus already use.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional, Tuple

from app.features.form_builder.engine.logic.formula.env import FormulaEnv
from app.features.form_builder.engine.logic.formula.kind_words import family_of
from app.features.form_builder.engine.logic.formula.nodes import (
    Bin,
    Bool,
    Call,
    Compare,
    IfElse,
    ListLit,
    Lit,
    Node,
    Ref,
    Unary,
)
from app.features.form_builder.engine.logic.formula.parse import parse_text

_GLYPH = {"+": "+", "-": "−", "*": "×", "/": "÷"}
_PREC = {"+": 1, "-": 1, "*": 2, "/": 2}
_ROW = {
    "checked": "is checked",
    "unchecked": "is not checked",
    "blank": "is blank",
    "not_blank": "is not blank",
    "today": "is today",
    "eq": "is",
    "ne": "is not",
    "lt": "is before",
    "gt": "is after",
    "le": "is at most",
    "ge": "is at least",
    "contains": "contains",
    "starts": "starts with",
    "between": "between",
    "one_of": "is one of",
}
_NUMBER_ROW = {
    "eq": "is",
    "ne": "is not",
    "lt": "is less than",
    "le": "is at most",
    "gt": "is more than",
    "ge": "is at least",
    "between": "is between",
}
_CMP = {"==": "eq", "!=": "ne", "<": "lt", "<=": "le", ">": "gt", ">=": "ge"}


def speak_text(text: str, env: FormulaEnv, kind: str) -> str:
    """English for ``text``, or "" when the builder cannot load it."""
    raw = text.strip()
    if not raw:
        return ""
    parsed = parse_text(raw, env)
    tree = parsed.tree
    if tree is None:
        return ""
    if kind == "condition":
        return _condition(tree, raw, env)
    if kind == "value":
        return _value(tree, raw, env)
    return ""


def _condition(node: Node, text: str, env: FormulaEnv) -> str:
    if isinstance(node, Bool) and node.op in ("and", "or"):
        parts = [_row(part, text, env) for part in node.values]
        if any(not part for part in parts) or len(parts) < 2:
            return ""
        joiner = " or " if node.op == "or" else " and "
        return joiner.join(parts)
    return _row(node, text, env)


def _row(node: Node, text: str, env: FormulaEnv) -> str:
    if isinstance(node, Ref):
        if family_of(env, node.name) != "yesno":
            return ""
        return "%s is checked" % _widget(env, node.name)
    if isinstance(node, Unary) and node.op == "not":
        return _not_row(node, env)
    if isinstance(node, Call):
        return _call_row(node, text, env)
    if isinstance(node, Compare):
        return _compare_row(node, text, env)
    return ""


def _not_row(node: Unary, env: FormulaEnv) -> str:
    inner = node.x
    if isinstance(inner, Ref) and family_of(env, inner.name) == "yesno":
        return "%s is not checked" % _widget(env, inner.name)
    if (
        isinstance(inner, Call)
        and inner.func == "is_blank"
        and len(inner.args) == 1
        and isinstance(inner.args[0], Ref)
    ):
        return "%s is not blank" % _widget(env, inner.args[0].name)
    return ""


def _call_row(node: Call, text: str, env: FormulaEnv) -> str:
    if not node.args or not isinstance(node.args[0], Ref):
        return ""
    name = _widget(env, node.args[0].name)
    if node.func == "is_blank" and len(node.args) == 1:
        return "%s is blank" % name
    if node.func == "contains" and len(node.args) == 2:
        other = _atom(node.args[1], text, env)
        if other is None or other[0] not in ("text", "field"):
            return ""
        return "%s contains %s" % (name, other[1])
    if node.func == "starts_with" and len(node.args) == 2:
        other = _atom(node.args[1], text, env)
        if other is None or other[0] not in ("text", "field"):
            return ""
        return "%s starts with %s" % (name, other[1])
    return ""


def _compare_row(node: Compare, text: str, env: FormulaEnv) -> str:
    pairs = node.pairs
    if len(pairs) == 2:
        op1, mid = pairs[0]
        op2, right = pairs[1]
        if op1 == "<=" and op2 == "<=" and isinstance(mid, Ref):
            if family_of(env, mid.name) != "number":
                return ""
            lo = _atom(node.first, text, env)
            hi = _atom(right, text, env)
            if lo is None or hi is None or lo[0] != "number" or hi[0] != "number":
                return ""
            return "%s between %s and %s" % (_widget(env, mid.name), lo[1], hi[1])
        return ""
    if len(pairs) != 1 or not isinstance(node.first, Ref):
        return ""
    op, right = pairs[0]
    field = node.first.name
    name = _widget(env, field)
    if op == "==" and isinstance(right, Call) and right.func == "today" and not right.args:
        if family_of(env, field) not in ("date", "datetime"):
            return ""
        return "%s is today" % name
    if op == "in" and isinstance(right, ListLit):
        listed = []
        for item in right.items:
            atom = _atom(item, text, env)
            if atom is None or atom[0] != "text":
                return ""
            listed.append(atom[1])
        if not listed:
            return ""
        return "%s is one of %s" % (name, ", ".join(listed))
    key = _CMP.get(op)
    if key is None:
        return ""
    atom = _atom(right, text, env)
    if atom is None:
        return ""
    label = (_NUMBER_ROW if family_of(env, field) == "number" else _ROW).get(key, key)
    return "%s %s %s" % (name, label, atom[1])


def _value(node: Node, text: str, env: FormulaEnv) -> str:
    if isinstance(node, IfElse):
        test = _condition(node.test, text, env)
        then_value = _piece(node.then, text, env)
        other = _piece(node.other, text, env)
        if not test or not then_value or not other:
            return ""
        return "If %s, then %s, otherwise %s" % (test, then_value, other)
    return _piece(node, text, env)


def _piece(node: Node, text: str, env: FormulaEnv) -> str:
    if isinstance(node, IfElse):
        return ""
    flat = _flatten(node, text, env)
    if flat is None:
        return ""
    atoms, ops = flat
    if len(atoms) == 1 and not ops:
        return atoms[0]
    if not (2 <= len(atoms) <= 4 and len(ops) == len(atoms) - 1):
        return ""
    shown = atoms[0]
    for op, atom in zip(ops, atoms[1:]):
        shown = "%s %s %s" % (shown, _GLYPH.get(op, op), atom)
    return shown


def _flatten(node: Node, text: str, env: FormulaEnv) -> Optional[Tuple[Tuple[str, ...], Tuple[str, ...]]]:
    atom = _value_atom(node, text, env)
    if atom is not None:
        return ((atom,), ())
    if not isinstance(node, Bin) or node.op not in _PREC:
        return None
    if not _side_ok(node.a, node.op, True, text) or not _side_ok(node.b, node.op, False, text):
        return None
    left = _flatten(node.a, text, env)
    right = _flatten(node.b, text, env)
    if left is None or right is None:
        return None
    return (left[0] + right[0], left[1] + (node.op,) + right[1])


def _side_ok(child: Node, parent_op: str, left: bool, text: str) -> bool:
    if _value_atom(child, text, None) is not None:
        return True
    if not isinstance(child, Bin) or child.op not in _PREC:
        return False
    child_prec = _PREC[child.op]
    parent_prec = _PREC[parent_op]
    if child_prec < parent_prec:
        return False
    if child_prec == parent_prec and not left:
        return False
    return True


def _value_atom(node: Node, text: str, env: Optional[FormulaEnv]) -> Optional[str]:
    atom = _atom(node, text, env)
    if atom is None or atom[0] not in ("field", "number"):
        return None
    return atom[1]


def _atom(node: Node, text: str, env: Optional[FormulaEnv]) -> Optional[Tuple[str, str]]:
    if isinstance(node, Ref):
        shown = node.name if env is None else _widget(env, node.name)
        return ("field", shown)
    if isinstance(node, Lit):
        if isinstance(node.value, bool):
            return ("yesno", "yes" if node.value else "no")
        if isinstance(node.value, str):
            return ("text", node.value)
        if isinstance(node.value, (int, Decimal)):
            return ("number", _number_slice(node, text))
        return None
    if (
        isinstance(node, Unary)
        and node.op == "-"
        and isinstance(node.x, Lit)
        and isinstance(node.x.value, (int, Decimal))
        and not isinstance(node.x.value, bool)
    ):
        return ("number", "-" + _number_slice(node.x, text).lstrip("-"))
    if isinstance(node, Call) and node.func == "date" and len(node.args) == 3:
        parts = []
        for arg in node.args:
            if not isinstance(arg, Lit) or isinstance(arg.value, bool) or not isinstance(arg.value, int):
                return None
            parts.append(int(arg.value))
        return ("date", "%04d-%02d-%02d" % (parts[0], parts[1], parts[2]))
    return None


def _number_slice(node: Node, text: str) -> str:
    if not text:
        return ""
    raw = text[node.span.start : node.span.end]
    return "".join(raw.split())


def _widget(env: FormulaEnv, name: str) -> str:
    facts = env.widgets.get(name)
    if facts is None or not facts.display:
        return name
    return facts.display
