"""Function signatures and result types (CONTRACTS.md section 17.9).

M7.1b writes the bodies under ``helper_id``. A wrong argument type is FB102 and
a wrong count is FB112. The checker reads this table. It does not call the helpers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional, Tuple

from app.features.form_builder.engine.logic.formula.types import (
    FType,
    NUMBER,
    TEXT,
    WHOLE,
    YESNO,
    DATE,
    DATETIME,
    unwrap,
    widen_numeric,
)


@dataclass(frozen=True)
class FunctionSpec:
    """One library function. ``params`` are type tags, not live values.

    Tags are ``any``, ``text``, ``number``, ``whole``, and ``date``. ``column``
    means a single column argument is legal (aggregates, and ``min`` / ``max``).
    ``pattern_arg`` is the index that must be a literal pattern (``matches``).
    """

    params: Tuple[str, ...]
    required: int
    varargs: bool
    result_rule: str
    helper_id: str
    doc: str
    max_args: Optional[int] = None
    column: bool = False
    pattern_arg: Optional[int] = None


def _spec(
    name: str,
    params: Tuple[str, ...],
    result_rule: str,
    doc: str,
    *,
    required: Optional[int] = None,
    varargs: bool = False,
    max_args: Optional[int] = None,
    column: bool = False,
    pattern_arg: Optional[int] = None,
) -> FunctionSpec:
    return FunctionSpec(
        params=params,
        required=len(params) if required is None else required,
        varargs=varargs,
        result_rule=result_rule,
        helper_id="_cbcs_" + name,
        doc=doc,
        max_args=max_args,
        column=column,
        pattern_arg=pattern_arg,
    )


FUNCTIONS: Mapping[str, FunctionSpec] = {
    "is_blank": _spec("is_blank", ("any",), "yesno", "True when the value is blank."),
    "if_blank": _spec("if_blank", ("any", "any"), "if_blank", "The fallback when the value is blank."),
    "round": _spec(
        "round",
        ("number", "whole"),
        "number",
        "Round half up.",
        required=1,
        max_args=2,
    ),
    "abs": _spec("abs", ("number",), "number", "Absolute value."),
    "min": _spec(
        "min",
        ("number",),
        "widen",
        "The smaller value, or the smallest in a column.",
        required=2,
        varargs=True,
        column=True,
    ),
    "max": _spec(
        "max",
        ("number",),
        "widen",
        "The larger value, or the largest in a column.",
        required=2,
        varargs=True,
        column=True,
    ),
    "sum": _spec("sum", ("number",), "number", "Sum of a column, skipping blanks.", column=True),
    "avg": _spec("avg", ("number",), "number", "Average of a column, skipping blanks.", column=True),
    "count": _spec("count", ("any",), "whole", "How many rows or values, skipping blanks.", column=True),
    "number": _spec("number", ("text",), "number", "Read a number from text."),
    "whole": _spec("whole", ("number",), "whole", "Drop the fraction, toward zero."),
    "text": _spec(
        "text",
        ("any", "text"),
        "text",
        "Show a value as text.",
        required=1,
        max_args=2,
    ),
    "len": _spec("len", ("text",), "whole", "How many characters."),
    "upper": _spec("upper", ("text",), "text", "Upper case."),
    "lower": _spec("lower", ("text",), "text", "Lower case."),
    "trim": _spec("trim", ("text",), "text", "Strip surrounding spaces."),
    "proper": _spec("proper", ("text",), "text", "Title case."),
    "left": _spec("left", ("text", "whole"), "text", "The first n characters."),
    "right": _spec("right", ("text", "whole"), "text", "The last n characters."),
    "contains": _spec("contains", ("text", "text"), "yesno", "True when the text contains the part."),
    "starts_with": _spec("starts_with", ("text", "text"), "yesno", "True when the text starts with the part."),
    "ends_with": _spec("ends_with", ("text", "text"), "yesno", "True when the text ends with the part."),
    "replace": _spec("replace", ("text", "text", "text"), "text", "Replace one piece of text with another."),
    "matches": _spec(
        "matches",
        ("text", "text"),
        "yesno",
        "True when the text matches the pattern.",
        pattern_arg=1,
    ),
    "is_email": _spec("is_email", ("text",), "yesno", "True when the text looks like an email address."),
    "is_phone": _spec("is_phone", ("text",), "yesno", "True when the text looks like a phone number."),
    "is_zip": _spec("is_zip", ("text",), "yesno", "True when the text looks like a US ZIP."),
    "today": _spec("today", (), "date", "Today's date."),
    "now": _spec("now", (), "datetime", "The current date and time."),
    "date": _spec("date", ("whole", "whole", "whole"), "date", "A date from a year, month, and day."),
    "year": _spec("year", ("date",), "whole", "The year."),
    "month": _spec("month", ("date",), "whole", "The month."),
    "day": _spec("day", ("date",), "whole", "The day."),
    "weekday": _spec("weekday", ("date",), "whole", "Monday is 1."),
    "add_days": _spec("add_days", ("date", "whole"), "date", "Shift a date by a number of days."),
    "add_months": _spec("add_months", ("date", "whole"), "date", "Shift a date by a number of months."),
    "days_between": _spec("days_between", ("date", "date"), "whole", "How many days from the first date to the second."),
}


def result_type(spec: FunctionSpec, args: Tuple[FType, ...]) -> FType:
    """The type the call returns, from the argument types."""
    rule = spec.result_rule
    if rule == "yesno":
        return YESNO
    if rule == "number":
        return NUMBER
    if rule == "whole":
        return WHOLE
    if rule == "text":
        return TEXT
    if rule == "date":
        return DATE
    if rule == "datetime":
        return DATETIME
    if rule == "widen":
        if not args:
            return NUMBER
        return widen_numeric(args)
    if rule == "if_blank":
        if len(args) < 2:
            return args[0] if args else TEXT
        return _if_blank_type(args[0], args[1])
    return TEXT


def _if_blank_type(value: FType, fallback: FType) -> FType:
    left = unwrap(value)
    right = unwrap(fallback)
    if left.kind == right.kind:
        return left
    pair = (left, right)
    if all(item.kind.value in ("whole", "number", "money", "blank", "any") for item in pair):
        return widen_numeric(pair)
    return right


def accepts_tag(tag: str, value: FType) -> bool:
    """True when an argument of ``value`` may be passed for ``tag``."""
    kind = unwrap(value).kind.value
    if kind in ("blank", "any"):
        return True
    if tag == "any":
        return True
    if tag == "text":
        return kind == "text"
    if tag == "number":
        return kind in ("whole", "number", "money")
    if tag == "whole":
        return kind == "whole"
    if tag == "date":
        return kind == "date"
    if tag == "yesno":
        return kind == "yesno"
    return False
