"""Which checks a field can take, and the sentence the engine would show."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Callable, Optional, Sequence, Tuple

from app.features.form_builder.engine.logic.checks import (
    Bound,
    Check,
    FormulaCheck,
    Length,
    OneOf,
    Pattern,
    Preset,
    Range,
    Required,
    RuntimeCheck,
    plan,
)
from app.features.form_builder.engine.logic.formula.types import DATE, FType, NUMBER, TEXT

KindProbe = Callable[[], Check]


@dataclass(frozen=True)
class CheckKind:
    key: str
    menu: str
    words: str
    probe: KindProbe


def _range_probe() -> Check:
    return Range(Bound(number=0), Bound(number=1), None)


def _length_probe() -> Check:
    return Length(1, None, None)


def _email_probe() -> Check:
    return Preset("email", None)


def _phone_probe() -> Check:
    return Preset("phone", None)


def _zip_probe() -> Check:
    return Preset("zip", None)


def _pattern_probe() -> Check:
    return Pattern("A", None)


def _one_of_probe() -> Check:
    return OneOf(("a",), None)


def _formula_probe() -> Check:
    return FormulaCheck("True", "ok")


# Menu order. A kind is offered only when its probe plans to a runtime or native write.
KINDS: Tuple[CheckKind, ...] = (
    CheckKind("required", "Required", "Required", lambda: Required(None)),
    CheckKind("range", "Between\u2026", "Between", _range_probe),
    CheckKind("length", "Length\u2026", "Length", _length_probe),
    CheckKind("email", "Email address", "Email address", _email_probe),
    CheckKind("phone", "Phone number", "Phone number", _phone_probe),
    CheckKind("zip", "US ZIP code", "US ZIP code", _zip_probe),
    CheckKind("pattern", "Pattern\u2026", "Pattern", _pattern_probe),
    CheckKind("one_of", "One of\u2026", "One of", _one_of_probe),
    CheckKind("formula", "Formula\u2026", "Formula", _formula_probe),
)

_BY_KEY = {item.key: item for item in KINDS}


def kind_of(check: Check) -> str:
    """The menu key for a stored check. Empty when this build does not edit it."""
    if isinstance(check, Required):
        return "required"
    if isinstance(check, Range):
        return "range"
    if isinstance(check, Length):
        return "length"
    if isinstance(check, Preset):
        return {"email": "email", "phone": "phone", "zip": "zip"}.get(check.name, "")
    if isinstance(check, Pattern):
        return "pattern"
    if isinstance(check, OneOf):
        return "one_of"
    if isinstance(check, FormulaCheck):
        return "formula"
    return ""


def words_of(check: Check) -> str:
    found = _BY_KEY.get(kind_of(check))
    return found.words if found is not None else ""


def offered_kinds(class_name: str, kind: str = "") -> Tuple[CheckKind, ...]:
    """Kinds whose probe plans to something the engine keeps."""
    found = []
    for item in KINDS:
        try:
            probe = item.probe()
        except Exception:
            continue
        try:
            field = plan(class_name, (probe,), kind)
        except Exception:
            continue
        if field.runtime or field.native:
            found.append(item)
    return tuple(found)


def generated_message(
    class_name: str,
    check: Check,
    kind: str = "",
    *,
    label: str = "",
    object_name: str = "",
) -> str:
    """The sentence ``plan`` would show. Blank when the check has no runtime message."""
    try:
        field = plan(
            class_name,
            (check,),
            kind,
            label=label,
            object_name=object_name,
        )
    except Exception:
        return ""
    for arm in field.runtime:
        if not isinstance(arm, RuntimeCheck) or arm.comment == "Number":
            continue
        try:
            text = ast.literal_eval(arm.message)
        except (SyntaxError, ValueError):
            return ""
        return text if isinstance(text, str) else ""
    return ""


def writes_native(
    class_name: str,
    checks: Sequence[Check],
    kind: str = "",
) -> bool:
    try:
        field = plan(class_name, checks, kind)
    except Exception:
        return False
    return bool(field.native)


def bound_target(class_name: str, kind: str) -> FType:
    """The type a Between formula must have. Same decision as the engine."""
    from app.features.form_builder.engine.logic.checks import numeric_family

    if class_name in ("QSpinBox", "QDoubleSpinBox"):
        return NUMBER
    if class_name == "QDateEdit":
        return DATE
    if numeric_family(kind):
        return NUMBER
    return TEXT
