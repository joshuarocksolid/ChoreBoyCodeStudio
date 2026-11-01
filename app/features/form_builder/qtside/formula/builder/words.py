"""Read the builder back in the words already on its menus.

Formula mode keeps ``as_words``. This is only for the builder's status line,
so a non-programmer never sees ``x if c else y``.
"""

from __future__ import annotations

from app.features.form_builder.engine.logic.formula.env import FormulaEnv
from app.features.form_builder.qtside.formula.builder.model import (
    Arithmetic,
    Atom,
    Condition,
    IfThen,
    Model,
    Row,
    Simple,
)

_GLYPH = {"+": "+", "-": "−", "*": "×", "/": "÷"}
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
    "eq": "=",
    "ne": "not =",
    "lt": "<",
    "le": "<=",
    "gt": ">",
    "ge": ">=",
    "between": "between",
}


def speak(model: Model, env: FormulaEnv) -> str:
    """The status line for one builder model. Empty when there is nothing to read."""

    if isinstance(model, Condition):
        return _condition(model, env)
    if isinstance(model, IfThen):
        test = _condition(model.test, env)
        return "If %s, then %s, otherwise %s" % (test, _piece(model.then_value, env), _piece(model.other, env))
    return _piece(model, env)


def _condition(model: Condition, env: FormulaEnv) -> str:
    parts = [_row(row, env) for row in model.rows if row.field]
    if not parts:
        return ""
    joiner = " or " if model.join == "or" else " and "
    return joiner.join(parts)


def _piece(model: object, env: FormulaEnv) -> str:
    if isinstance(model, Simple):
        return _atom(model.atom, env)
    if isinstance(model, Arithmetic):
        text = _atom(model.atoms[0], env)
        for op, atom in zip(model.ops, model.atoms[1:]):
            text = "%s %s %s" % (text, _GLYPH.get(op, op), _atom(atom, env))
        return text
    return ""


def _row(row: Row, env: FormulaEnv) -> str:
    name = _widget(env, row.field)
    family = _family(env, row.field)
    label = (_NUMBER_ROW if family == "number" else _ROW).get(row.op, _ROW.get(row.op, row.op))
    if row.op in ("checked", "unchecked", "blank", "not_blank", "today"):
        return "%s %s" % (name, label)
    if row.op == "between" and len(row.values) >= 2:
        return "%s %s %s and %s" % (name, label, _atom(row.values[0], env), _atom(row.values[1], env))
    if row.op == "one_of":
        listed = ", ".join(_atom(atom, env) for atom in row.values)
        return "%s %s %s" % (name, label, listed)
    if not row.values:
        return "%s %s" % (name, label)
    return "%s %s %s" % (name, label, _atom(row.values[0], env))


def _atom(atom: Atom, env: FormulaEnv) -> str:
    if atom.kind == "field":
        return _widget(env, atom.text)
    return atom.text


def _widget(env: FormulaEnv, name: str) -> str:
    facts = env.widgets.get(name)
    if facts is None or not facts.display:
        return name
    return facts.display


def _family(env: FormulaEnv, name: str) -> str:
    from app.features.form_builder.qtside.formula.builder.model import family_of

    return family_of(env, name)
