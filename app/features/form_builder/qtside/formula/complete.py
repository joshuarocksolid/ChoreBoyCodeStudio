"""Completion rows for the formula field (UX-FX-002). Pure: no Qt."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from app.features.form_builder.engine.logic.formula.env import FormulaEnv, WidgetFacts
from app.features.form_builder.engine.logic.formula.kind_words import kind_words as _kind
from app.features.form_builder.engine.logic.formula.library import FUNCTIONS


@dataclass(frozen=True)
class Completion:
    """One row. ``insert`` replaces ``text[start:cursor]``. A display-name match inserts the object name."""

    label: str
    insert: str
    start: int


def completions(text: str, cursor: int, env: FormulaEnv, *, forced: bool = False) -> Tuple[Completion, ...]:
    """Widgets, then functions, then ``window.`` methods when the token starts with ``window.``."""
    start, token = _token(text, cursor)
    if token.startswith("window."):
        return _methods(env, token[len("window.") :], start + len("window."))
    if not forced and len(token) < 2:
        return ()
    rows = []
    for name, facts in env.widgets.items():
        display = facts.display or name
        if token and not _prefix(token, name) and not _prefix(token, display):
            continue
        kind = _kind(env, facts)
        if display == name:
            label = "%s  %s" % (name, kind)
        else:
            label = "%s  %s  %s" % (name, display, kind)
        rows.append(Completion(label, name, start))
    folded = token.casefold()
    for name, spec in FUNCTIONS.items():
        if folded and not name.casefold().startswith(folded):
            continue
        rows.append(Completion("%s  %s" % (name, spec.doc), name, start))
    return tuple(rows)


def _methods(env: FormulaEnv, prefix: str, start: int) -> Tuple[Completion, ...]:
    rows = []
    for name in env.methods:
        if prefix and not _prefix(prefix, name):
            continue
        rows.append(Completion("window.%s" % name, name, start))
    return tuple(rows)


def _token(text: str, cursor: int) -> Tuple[int, str]:
    if cursor < 0:
        cursor = 0
    if cursor > len(text):
        cursor = len(text)
    start = cursor
    while start > 0 and (text[start - 1].isalnum() or text[start - 1] in "_."):
        start -= 1
    return start, text[start:cursor]


def _prefix(prefix: str, value: str) -> bool:
    return value.casefold().startswith(prefix.casefold())
