"""Builder rows and the formula text they stand for.

The builder stores nothing. ``load_formula`` reads a formula through the
existing tree, and ``write_formula`` prints the same shapes back. A formula
that is not one of those shapes comes back as None, which disables Builder.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Tuple, Union

from app.features.form_builder.engine.logic.formula.env import FormulaEnv
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
from app.features.form_builder.engine.logic.formula.normalize import normalize
from app.features.form_builder.engine.logic.formula.kind_words import family_of as family_of
from app.features.form_builder.engine.logic.formula.kind_words import kind_words as _kind
from app.features.form_builder.engine.logic.formula.parse import parse_text

BLOCKED = "This is too complex for the builder. Edit it as a formula."

_PREC = {"+": 1, "-": 1, "*": 2, "/": 2}
_CMP = {"==": "eq", "!=": "ne", "<": "lt", "<=": "le", ">": "gt", ">=": "ge"}
_SYMBOL = {value: key for key, value in _CMP.items()}


@dataclass(frozen=True)
class Atom:
    """One field, number, text, date, or yes/no literal."""

    kind: str
    text: str


@dataclass(frozen=True)
class Row:
    """One condition line. ``op`` is the builder key, not the menu label."""

    field: str
    op: str
    values: Tuple[Atom, ...] = ()


@dataclass(frozen=True)
class Condition:
    """``and`` is all of. ``or`` is any of. One row still uses ``and``."""

    join: str
    rows: Tuple[Row, ...]


@dataclass(frozen=True)
class Simple:
    atom: Atom


@dataclass(frozen=True)
class Arithmetic:
    """Two to four atoms. ``ops`` sits between them, left to right."""

    atoms: Tuple[Atom, ...]
    ops: Tuple[str, ...]


@dataclass(frozen=True)
class IfThen:
    test: Condition
    then_value: "Piece"
    other: "Piece"


Piece = Union[Simple, Arithmetic]
Value = Union[Simple, Arithmetic, IfThen]
Model = Union[Condition, Value]


def empty_model(kind: str) -> Model:
    if kind == "condition":
        return Condition("and", ())
    return Simple(Atom("field", ""))


def load_formula(text: str, env: FormulaEnv, kind: str) -> Optional[Model]:
    """The builder model for ``text``, or None when Builder must stay off."""

    raw = text.strip()
    if raw == "":
        return empty_model(kind)
    parsed = parse_text(raw, env)
    tree = parsed.tree
    if tree is None:
        return None
    if kind == "condition":
        model: Optional[Model] = _condition(tree, raw, env)
    elif kind == "value":
        model = _value(tree, raw, env)
    else:
        return None
    if model is None:
        return None
    written = write_formula(model)
    if written != raw and written != normalize(raw):
        return None
    return model


def write_formula(model: Model) -> str:
    if isinstance(model, Condition):
        return _write_condition(model)
    return _write_value(model)


def picker_label(env: FormulaEnv, name: str) -> str:
    """Display name, then the Kind in words. The inserted text is ``name``."""

    facts = env.widgets.get(name)
    if facts is None:
        return name
    display = facts.display or name
    kind = _kind(env, facts)
    return "%s · %s" % (display, kind)


def _condition(node: Node, text: str, env: FormulaEnv) -> Optional[Condition]:
    if isinstance(node, Bool) and node.op in ("and", "or"):
        rows = []
        for part in node.values:
            row = _row(part, text, env)
            if row is None:
                return None
            rows.append(row)
        if len(rows) < 2:
            return None
        return Condition(node.op, tuple(rows))
    row = _row(node, text, env)
    if row is None:
        return None
    return Condition("and", (row,))


def _row(node: Node, text: str, env: FormulaEnv) -> Optional[Row]:
    if isinstance(node, Ref):
        if family_of(env, node.name) != "yesno":
            return None
        return Row(node.name, "checked")
    if isinstance(node, Unary) and node.op == "not":
        return _not_row(node, text, env)
    if isinstance(node, Call):
        return _call_row(node, text)
    if isinstance(node, Compare):
        return _compare_row(node, text, env)
    return None


def _not_row(node: Unary, text: str, env: FormulaEnv) -> Optional[Row]:
    del text
    inner = node.x
    if isinstance(inner, Ref) and family_of(env, inner.name) == "yesno":
        return Row(inner.name, "unchecked")
    if (
        isinstance(inner, Call)
        and inner.func == "is_blank"
        and len(inner.args) == 1
        and isinstance(inner.args[0], Ref)
    ):
        return Row(inner.args[0].name, "not_blank")
    return None


def _call_row(node: Call, text: str) -> Optional[Row]:
    if not node.args or not isinstance(node.args[0], Ref):
        return None
    field = node.args[0].name
    if node.func == "is_blank" and len(node.args) == 1:
        return Row(field, "blank")
    if node.func in ("contains", "starts_with") and len(node.args) == 2:
        atom = _atom(node.args[1], text)
        if atom is None or atom.kind not in ("text", "field"):
            return None
        op = "contains" if node.func == "contains" else "starts"
        return Row(field, op, (atom,))
    return None


def _compare_row(node: Compare, text: str, env: FormulaEnv) -> Optional[Row]:
    pairs = node.pairs
    if len(pairs) == 2:
        op1, mid = pairs[0]
        op2, right = pairs[1]
        if op1 == "<=" and op2 == "<=" and isinstance(mid, Ref):
            if family_of(env, mid.name) != "number":
                return None
            lo = _atom(node.first, text)
            hi = _atom(right, text)
            if lo is None or hi is None or lo.kind != "number" or hi.kind != "number":
                return None
            return Row(mid.name, "between", (lo, hi))
        return None
    if len(pairs) != 1 or not isinstance(node.first, Ref):
        return None
    op, right = pairs[0]
    field = node.first.name
    if op == "==" and isinstance(right, Call) and right.func == "today" and not right.args:
        if family_of(env, field) not in ("date", "datetime"):
            return None
        return Row(field, "today")
    if op == "in" and isinstance(right, ListLit):
        vals = []
        for item in right.items:
            atom = _atom(item, text)
            if atom is None or atom.kind != "text":
                return None
            vals.append(atom)
        if not vals:
            return None
        return Row(field, "one_of", tuple(vals))
    key = _CMP.get(op)
    if key is None:
        return None
    atom = _atom(right, text)
    if atom is None:
        return None
    return Row(field, key, (atom,))


def _value(node: Node, text: str, env: FormulaEnv) -> Optional[Value]:
    if isinstance(node, IfElse):
        test = _condition(node.test, text, env)
        then_value = _piece(node.then, text)
        other = _piece(node.other, text)
        if test is None or then_value is None or other is None:
            return None
        return IfThen(test, then_value, other)
    return _piece(node, text)


def _piece(node: Node, text: str) -> Optional[Piece]:
    if isinstance(node, IfElse):
        return None
    flat = _flatten(node, text)
    if flat is None:
        return None
    atoms, ops = flat
    if len(atoms) == 1 and not ops:
        return Simple(atoms[0])
    if 2 <= len(atoms) <= 4 and len(ops) == len(atoms) - 1:
        return Arithmetic(tuple(atoms), tuple(ops))
    return None


def _flatten(node: Node, text: str) -> Optional[Tuple[Tuple[Atom, ...], Tuple[str, ...]]]:
    atom = _value_atom(node, text)
    if atom is not None:
        return ((atom,), ())
    if not isinstance(node, Bin) or node.op not in _PREC:
        return None
    if not _side_ok(node.a, node.op, True) or not _side_ok(node.b, node.op, False):
        return None
    left = _flatten(node.a, text)
    right = _flatten(node.b, text)
    if left is None or right is None:
        return None
    return (left[0] + right[0], left[1] + (node.op,) + right[1])


def _side_ok(child: Node, parent_op: str, left: bool) -> bool:
    if _value_atom(child, "") is not None:
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


def _value_atom(node: Node, text: str) -> Optional[Atom]:
    atom = _atom(node, text)
    if atom is None:
        return None
    if atom.kind in ("field", "number"):
        return atom
    return None


def _atom(node: Node, text: str) -> Optional[Atom]:
    if isinstance(node, Ref):
        return Atom("field", node.name)
    if isinstance(node, Lit):
        if isinstance(node.value, bool):
            return Atom("yesno", "yes" if node.value else "no")
        if isinstance(node.value, str):
            return Atom("text", node.value)
        if isinstance(node.value, (int, Decimal)):
            return Atom("number", _number_slice(node, text))
        return None
    if (
        isinstance(node, Unary)
        and node.op == "-"
        and isinstance(node.x, Lit)
        and isinstance(node.x.value, (int, Decimal))
        and not isinstance(node.x.value, bool)
    ):
        return Atom("number", "-" + _number_slice(node.x, text).lstrip("-"))
    if isinstance(node, Call) and node.func == "date" and len(node.args) == 3:
        parts = []
        for arg in node.args:
            if not isinstance(arg, Lit) or isinstance(arg.value, bool) or not isinstance(arg.value, int):
                return None
            parts.append(int(arg.value))
        return Atom("date", "%04d-%02d-%02d" % (parts[0], parts[1], parts[2]))
    return None


def _number_slice(node: Node, text: str) -> str:
    if not text:
        return ""
    raw = text[node.span.start : node.span.end]
    return "".join(raw.split())


def _write_condition(model: Condition) -> str:
    parts = [_write_row(row) for row in model.rows if row.field]
    if any(part == "" for part in parts):
        return ""
    joiner = " or " if model.join == "or" else " and "
    return joiner.join(parts)


def _write_row(row: Row) -> str:
    field = row.field
    op = row.op
    vals = row.values
    if op == "checked":
        return field
    if op == "unchecked":
        return "not %s" % field
    if op == "blank":
        return "is_blank(%s)" % field
    if op == "not_blank":
        return "not is_blank(%s)" % field
    if op == "contains":
        return "contains(%s, %s)" % (field, _emit(vals[0]))
    if op == "starts":
        return "starts_with(%s, %s)" % (field, _emit(vals[0]))
    if op == "today":
        return "%s == today()" % field
    if op == "between" and len(vals) == 2:
        return "%s <= %s <= %s" % (_emit(vals[0]), field, _emit(vals[1]))
    if op == "one_of" and vals:
        inner = ", ".join(_emit(item) for item in vals)
        return "%s in [%s]" % (field, inner)
    symbol = _SYMBOL.get(op)
    if symbol is None or not vals:
        return ""
    return "%s %s %s" % (field, symbol, _emit(vals[0]))


def _write_value(model: Value) -> str:
    if isinstance(model, IfThen):
        then_text = _write_value(model.then_value)
        test = _write_condition(model.test)
        other = _write_value(model.other)
        if not then_text or not test or not other:
            return ""
        return "%s if %s else %s" % (then_text, test, other)
    if isinstance(model, Simple):
        if not model.atom.text:
            return ""
        return _emit(model.atom)
    parts = []
    if not model.atoms or len(model.ops) != len(model.atoms) - 1:
        return ""
    for index, atom in enumerate(model.atoms):
        if not atom.text:
            return ""
        if index:
            parts.append(model.ops[index - 1])
        parts.append(_emit(atom))
    return " ".join(parts)


def _emit(atom: Atom) -> str:
    if atom.kind == "text":
        return json.dumps(atom.text)
    if atom.kind == "date":
        year, month, day = atom.text.split("-")
        return "date(%d, %d, %d)" % (int(year), int(month), int(day))
    if atom.kind == "yesno":
        return "True" if atom.text == "yes" else "False"
    return atom.text
