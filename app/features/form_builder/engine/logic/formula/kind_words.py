"""Kind words and the builder family. Qt-free so the engine can speak formulas.

``qtside.formula.complete`` re-exports ``kind_words`` as ``_kind``.
"""

from __future__ import annotations

from app.features.form_builder.engine.logic.formula.env import FormulaEnv, WidgetFacts
from app.features.form_builder.engine.logic.formula.types import FKind, lookup_spec, main_type

_KIND_WORDS = {
    "text": "Text",
    "whole": "Whole number",
    "money": "Money",
    "percent": "Percent",
    "date": "Date",
    "time": "Time",
}

_TYPE_WORDS = {
    FKind.TEXT: "Text",
    FKind.WHOLE: "Whole number",
    FKind.NUMBER: "Number",
    FKind.MONEY: "Money",
    FKind.YESNO: "Yes or no",
    FKind.DATE: "Date",
    FKind.TIME: "Time",
    FKind.DATETIME: "Date and time",
    FKind.PAGE: "Page",
    FKind.CHOICE: "Choice",
    FKind.COLUMN: "Column",
}

_FAMILY = {
    "Yes or no": "yesno",
    "Whole number": "number",
    "Number": "number",
    "Money": "number",
    "Percent": "number",
    "Text": "text",
    "Date": "date",
    "Time": "time",
    "Date and time": "datetime",
}


def kind_words(env: FormulaEnv, facts: WidgetFacts) -> str:
    """The Kind a person sees ("Whole number", "Yes or no")."""
    code = (facts.kind or "").strip()
    if code in _KIND_WORDS:
        return _KIND_WORDS[code]
    if code.startswith("number:"):
        return "Number"
    chain = env.class_chain(facts.class_name)
    matched, spec = lookup_spec(facts.class_name, chain)
    if spec is None or matched is None:
        return facts.class_name
    found, _unknown = main_type(
        spec,
        matched,
        kind=facts.kind,
        prefix=facts.prefix,
        decimals=facts.decimals,
        has_items_data=facts.has_items_data,
    )
    if found is None:
        return facts.class_name
    return _TYPE_WORDS.get(found.kind, facts.class_name)


def family_of(env: FormulaEnv, name: str) -> str:
    """yesno, number, text, date, or "" when the widget has no builder family."""
    facts = env.widgets.get(name)
    if facts is None:
        return ""
    return _FAMILY.get(kind_words(env, facts), "")
