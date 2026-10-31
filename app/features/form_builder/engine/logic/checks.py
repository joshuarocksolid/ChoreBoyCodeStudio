"""Validation checks: the JSON boundary and the only native-first decision.

``plan`` decides which checks become Qt properties and which predicates Python
still runs. Commands and the checks expander both call it. They do not decide
what a check means.
"""

from __future__ import annotations

import ast
import datetime
import re
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple, Union

from app.features.form_builder.engine.codegen.logic_hooks import one_line
from app.features.form_builder.engine.diagnostics import CODES, Severity
from app.features.form_builder.engine.logic.codec import JsonObject, JsonValue, parse_json, write_json
from app.features.form_builder.engine.logic.compat import is_name
from app.features.form_builder.engine.logic.formula.check import analyze
from app.features.form_builder.engine.logic.formula.compile import Emitted, compile_formula
from app.features.form_builder.engine.project.window_facts import WindowFacts
from app.features.form_builder.engine.logic.formula.env import FormulaEnv
from app.features.form_builder.engine.logic.formula.runtime import HELPERS
from app.features.form_builder.engine.logic.formula.types import DATE, FType, NUMBER, TEXT
from app.features.form_builder.engine.query.tab_stops import display_name
from app.features.form_builder.engine.ui4.defaults import QtClassTable
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.engine.ui4.values import (
    DateValue,
    DoubleValue,
    NumberValue,
    StringValue,
    Value,
)

_PRESETS = ("email", "phone", "zip")
_ALWAYS_VALUE = frozenset(
    {
        "QSpinBox",
        "QDoubleSpinBox",
        "QDateEdit",
        "QTimeEdit",
        "QDateTimeEdit",
        "QSlider",
        "QDial",
    }
)
_LITERALS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-./ ")
_MASK_BANNED = frozenset("^$[]{}+*?|")
_PLACEHOLDERS = frozenset("AaNnX90D#H")
_CASE_MARKERS = frozenset("><!")
_HELPER_RE = re.compile(r"\b(_cbcs_[A-Za-z0-9_]*)\b")
_HELPER_ORDER = [helper_id for helper_id, _source in HELPERS]
_HELPER_SOURCES = {helper_id: source for helper_id, source in HELPERS}
_IMPORT_NAMES = {
    "Decimal": ("decimal", "Decimal"),
    "ROUND_HALF_UP": ("decimal", "ROUND_HALF_UP"),
    "date": ("datetime", "date"),
    "datetime": ("datetime", "datetime"),
    "time": ("datetime", "time"),
}
_ISO_DATE = re.compile(r"\A\d{4}-\d{2}-\d{2}\Z")


@dataclass(frozen=True)
class Required:
    message: Optional[str]
    extra: Tuple[Tuple[str, object], ...] = ()


@dataclass(frozen=True)
class Bound:
    """A range side. ``number`` is int or float. ``formula`` is source text."""

    number: Optional[Union[int, float]] = None
    formula: Optional[str] = None

    def __post_init__(self) -> None:
        if (self.number is None) == (self.formula is None):
            raise ValueError("a bound is a number or a formula")


@dataclass(frozen=True)
class Range:
    min: Optional[Bound]
    max: Optional[Bound]
    message: Optional[str]
    extra: Tuple[Tuple[str, object], ...] = ()


@dataclass(frozen=True)
class Length:
    min: Optional[int]
    max: Optional[int]
    message: Optional[str]
    extra: Tuple[Tuple[str, object], ...] = ()


@dataclass(frozen=True)
class Preset:
    name: str
    message: Optional[str]
    extra: Tuple[Tuple[str, object], ...] = ()

    def __post_init__(self) -> None:
        if self.name not in _PRESETS:
            raise ValueError("preset name")


@dataclass(frozen=True)
class Pattern:
    pattern: str
    message: Optional[str]
    extra: Tuple[Tuple[str, object], ...] = ()


@dataclass(frozen=True)
class OneOf:
    values: Tuple[Union[str, int, float], ...]
    message: Optional[str]
    extra: Tuple[Tuple[str, object], ...] = ()


@dataclass(frozen=True)
class FormulaCheck:
    formula: str
    message: Optional[str]
    extra: Tuple[Tuple[str, object], ...] = ()


@dataclass(frozen=True)
class Unique:
    message: Optional[str]
    extra: Tuple[Tuple[str, object], ...] = ()


@dataclass(frozen=True)
class Opaque:
    """A ``check`` name this build does not type. Written back in read order."""

    pairs: Tuple[Tuple[str, object], ...]


Check = Union[Required, Range, Length, Preset, Pattern, OneOf, FormulaCheck, Unique, Opaque]


@dataclass(frozen=True)
class CheckRead:
    checks: Tuple[Check, ...]
    error: Optional[Tuple[int, str]]


@dataclass(frozen=True)
class NativeWrite:
    prop: str
    value: Union[NumberValue, DoubleValue, DateValue, StringValue]


@dataclass(frozen=True)
class RuntimeCheck:
    """One generated predicate. ``reads`` is other widget names the formula reads."""

    comment: str
    predicate: str
    message: str
    helpers: Tuple[str, ...]
    reads: Tuple[str, ...]


@dataclass(frozen=True)
class Skipped:
    comment: str
    code: str


@dataclass(frozen=True)
class FieldPlan:
    native: Tuple[NativeWrite, ...]
    runtime: Tuple[Union[RuntimeCheck, Skipped], ...]
    number_check: bool
    validator: bool


def read_checks(text: str) -> CheckRead:
    """``parse_json``, then one Check per object. Never raises."""
    try:
        parsed = parse_json(text)
        if parsed.error is not None:
            return CheckRead((), parsed.error)
        if not isinstance(parsed.value, tuple):
            return CheckRead((), (1, "expected a list"))
        found: List[Check] = []
        for item in parsed.value:
            if not isinstance(item, JsonObject):
                return CheckRead((), (1, "expected an object"))
            found.append(_read_check(item))
        return CheckRead(tuple(found), None)
    except Exception:
        return CheckRead((), (1, "not valid JSON"))


def write_checks(checks: Sequence[Check]) -> Optional[str]:
    """Canonical ``cbcsValidate`` text, or None when the list is empty."""
    if not checks:
        return None
    payload: List[JsonValue] = [_write_check(item) for item in checks]
    return write_json(tuple(payload))


def plan(
    class_name: str,
    checks: Sequence[Check],
    kind: str = "",
    *,
    label: str = "",
    object_name: str = "",
    env: Optional[FormulaEnv] = None,
    decimals: int = 2,
) -> FieldPlan:
    """Native writes plus the predicates Python still runs.

    A QDateEdit range bound that is exactly ``YYYY-MM-DD`` and a real calendar
    day is written as a date. The check schema says a string bound is a formula.
    A pure ISO date is treated as a date literal so native-first has a date to write.
    """
    shown = label or object_name or "Value"
    native: List[NativeWrite] = []
    runtime: List[Union[RuntimeCheck, Skipped]] = []
    family = numeric_family(kind)
    number_check = class_name == "QLineEdit" and bool(family)
    required: List[Required] = []
    rest: List[Check] = []
    for item in checks:
        if isinstance(item, Required):
            required.append(item)
        else:
            rest.append(item)
    for item in required:
        runtime.extend(_required_arm(class_name, item, shown))
    if number_check:
        runtime.append(_number_arm(kind, object_name, decimals))
    for item in rest:
        if isinstance(item, Length):
            native.extend(_length_native(class_name, item))
            runtime.extend(_length_arm(class_name, item, shown))
        elif isinstance(item, Range):
            native.extend(_range_native(class_name, item))
            runtime.extend(
                _range_arm(class_name, kind, item, shown, object_name, env, decimals)
            )
        elif isinstance(item, Pattern):
            mask = mask_of(item.pattern) if class_name == "QLineEdit" else None
            if mask is not None:
                native.append(NativeWrite("inputMask", StringValue(mask)))
            runtime.append(_pattern_arm(item, shown))
        elif isinstance(item, Preset):
            runtime.append(_preset_arm(item, shown))
        elif isinstance(item, OneOf):
            runtime.append(_one_of_arm(item, shown))
        elif isinstance(item, FormulaCheck):
            runtime.append(_formula_arm(item, object_name, env))
        elif isinstance(item, (Unique, Opaque)):
            continue
    return FieldPlan(tuple(native), tuple(runtime), number_check, number_check)


def mask_of(pattern: str) -> Optional[str]:
    """Qt ``inputMask`` for a fixed shape, or None."""
    translated = _translate_pattern(pattern)
    if translated is not None:
        return translated
    if _is_qt_mask(pattern):
        return pattern
    return None


def numeric_family(kind: str) -> str:
    """``whole``, ``number``, ``money``, ``percent``, or ``""``."""
    if kind == "whole":
        return "whole"
    if kind == "money":
        return "money"
    if kind == "percent" or _suffix_number(kind, "percent:"):
        return "percent"
    if kind == "number" or _suffix_number(kind, "number:"):
        return "number"
    return ""


def validator_pattern(kind: str, currency: str = "$") -> str:
    """The only ``QRegularExpressionValidator`` pattern. Empty when ``kind`` is not numeric."""
    family = numeric_family(kind)
    if family == "whole":
        return r"^[0-9,+\-]*$"
    if family == "percent":
        return r"^[0-9.,+\-%]*$"
    if family == "number":
        return r"^[0-9.,+\-]*$"
    if family == "money":
        return "^[0-9.,+\\-()" + _class_body(currency) + "]*$"
    return ""


def formula_env(doc: UiDocument, window: Optional[WindowFacts] = None) -> FormulaEnv:
    """The form's one formula env (M7.2a), so checks see the same kinds and methods as rules."""
    from app.features.form_builder.engine.logic.formula_env import env_for

    return env_for(doc, window, QtClassTable.shared())


def kind_text(node: WidgetNode) -> str:
    value = node.value("cbcsKind")
    if isinstance(value, StringValue):
        return value.text
    return ""


def close_helpers(helper_ids: Sequence[str]) -> Tuple[str, ...]:
    """Helper ids plus every helper they call, in table order."""
    needed = {helper_id for helper_id in helper_ids if helper_id in _HELPER_SOURCES}
    changed = True
    while changed:
        changed = False
        for helper_id in list(needed):
            for found in _HELPER_RE.findall(_HELPER_SOURCES[helper_id]):
                if found in _HELPER_SOURCES and found not in needed:
                    needed.add(found)
                    changed = True
    return tuple(helper_id for helper_id in _HELPER_ORDER if helper_id in needed)


def helper_imports(helper_ids: Sequence[str]) -> Tuple[Tuple[str, str], ...]:
    """``(module, name)`` pairs the closed helpers load."""
    found = []
    seen = set()
    for helper_id in close_helpers(helper_ids):
        for name in _load_names(_HELPER_SOURCES[helper_id]):
            pair = _IMPORT_NAMES.get(name)
            if pair is not None and pair not in seen:
                seen.add(pair)
                found.append(pair)
    return tuple(sorted(found))


def helpers_in(source: str) -> Tuple[str, ...]:
    return tuple(_HELPER_RE.findall(source))


def source_imports(source: str) -> Tuple[Tuple[str, str], ...]:
    """Imports a generated statement block names directly (``Decimal``, ``date``)."""
    found = []
    seen = set()
    for name in _load_names(source):
        pair = _IMPORT_NAMES.get(name)
        if pair is not None and pair not in seen:
            seen.add(pair)
            found.append(pair)
    return tuple(sorted(found))


def _read_check(obj: JsonObject) -> Check:
    name = obj.get("check")
    pairs = obj.pairs
    if not isinstance(name, str):
        return Opaque(pairs)
    message = _message(obj)
    if name == "required":
        return Required(message, _extra(pairs, _used(obj, ("check", "message"))))
    if name == "length":
        return Length(
            _as_int(obj.get("min")),
            _as_int(obj.get("max")),
            message,
            _extra(pairs, _used(obj, ("check", "message", "min", "max"), ints=("min", "max"))),
        )
    if name == "range":
        return Range(
            _bound(obj.get("min")),
            _bound(obj.get("max")),
            message,
            _extra(pairs, _used(obj, ("check", "message", "min", "max"), bounds=("min", "max"))),
        )
    if name in _PRESETS:
        return Preset(name, message, _extra(pairs, _used(obj, ("check", "message"))))
    if name == "pattern":
        pattern = obj.get("pattern")
        if not isinstance(pattern, str):
            return Opaque(pairs)
        return Pattern(pattern, message, _extra(pairs, _used(obj, ("check", "message", "pattern"))))
    if name == "oneOf":
        values = _one_of_values(obj.get("values"))
        if values is None:
            return Opaque(pairs)
        return OneOf(values, message, _extra(pairs, _used(obj, ("check", "message", "values"))))
    if name == "formula":
        formula = obj.get("formula")
        if not isinstance(formula, str):
            return Opaque(pairs)
        return FormulaCheck(formula, message, _extra(pairs, _used(obj, ("check", "message", "formula"))))
    if name == "unique":
        return Unique(message, _extra(pairs, _used(obj, ("check", "message"))))
    return Opaque(pairs)


def _write_check(item: Check) -> JsonObject:
    if isinstance(item, Opaque):
        return JsonObject(tuple(item.pairs))
    pairs: List[Tuple[str, JsonValue]] = []
    if isinstance(item, Required):
        pairs.append(("check", "required"))
    elif isinstance(item, Length):
        pairs.append(("check", "length"))
        if item.min is not None:
            pairs.append(("min", item.min))
        if item.max is not None:
            pairs.append(("max", item.max))
    elif isinstance(item, Range):
        pairs.append(("check", "range"))
        if item.min is not None:
            pairs.append(("min", _bound_json(item.min)))
        if item.max is not None:
            pairs.append(("max", _bound_json(item.max)))
    elif isinstance(item, Preset):
        pairs.append(("check", item.name))
    elif isinstance(item, Pattern):
        pairs.append(("check", "pattern"))
        pairs.append(("pattern", item.pattern))
    elif isinstance(item, OneOf):
        pairs.append(("check", "oneOf"))
        pairs.append(("values", tuple(item.values)))
    elif isinstance(item, FormulaCheck):
        pairs.append(("check", "formula"))
        pairs.append(("formula", item.formula))
    elif isinstance(item, Unique):
        pairs.append(("check", "unique"))
    if item.message is not None:
        pairs.append(("message", item.message))
    for key, value in item.extra:
        pairs.append((key, value))  # type: ignore[arg-type]
    return JsonObject(tuple(pairs))


def _required_arm(class_name: str, item: Required, label: str) -> Tuple[RuntimeCheck, ...]:
    if class_name in _ALWAYS_VALUE:
        return ()
    return (
        RuntimeCheck(
            "Required",
            "value is None",
            repr(_sentence(item.message, "%s is required" % label)),
            (),
            (),
        ),
    )


def _number_arm(kind: str, object_name: str, decimals: int) -> RuntimeCheck:
    reader, helpers = _kind_reader(kind, object_name, decimals)
    return RuntimeCheck(
        "Number",
        "value is not None and %s is None" % reader,
        repr("Enter a number"),
        helpers,
        (),
    )


def _length_native(class_name: str, item: Length) -> Tuple[NativeWrite, ...]:
    if class_name == "QLineEdit" and item.max is not None:
        return (NativeWrite("maxLength", NumberValue(item.max)),)
    return ()


def _length_arm(class_name: str, item: Length, label: str) -> Tuple[RuntimeCheck, ...]:
    native_max = class_name == "QLineEdit" and item.max is not None
    low = item.min if item.min is not None and item.min > 0 else None
    high = None if native_max else item.max
    if low is None and high is None:
        return ()
    checks = []
    if low is not None:
        checks.append("len(str(value)) < %d" % low)
    if high is not None:
        checks.append("len(str(value)) > %d" % high)
    return (
        RuntimeCheck(
            "Length",
            "value is not None and (%s)" % " or ".join(checks),
            repr(_sentence(item.message, _length_message(label, item.min, item.max))),
            (),
            (),
        ),
    )


def _range_native(class_name: str, item: Range) -> Tuple[NativeWrite, ...]:
    found: List[NativeWrite] = []
    for side, prop in (("min", _min_prop(class_name)), ("max", _max_prop(class_name))):
        if prop is None:
            continue
        bound = item.min if side == "min" else item.max
        value = _native_bound(class_name, bound)
        if value is not None:
            found.append(NativeWrite(prop, value))
    return tuple(found)


def _range_arm(
    class_name: str,
    kind: str,
    item: Range,
    label: str,
    object_name: str,
    env: Optional[FormulaEnv],
    decimals: int,
) -> Tuple[Union[RuntimeCheck, Skipped], ...]:
    sides: List[str] = []
    helpers: List[str] = []
    reads: List[str] = []
    compare = _compare_value(class_name, kind, object_name, decimals)
    helpers.extend(compare[1])
    for side, bound, native in (
        ("min", item.min, _native_bound(class_name, item.min) is not None),
        ("max", item.max, _native_bound(class_name, item.max) is not None),
    ):
        if bound is None or native:
            continue
        expr = _bound_expression(class_name, kind, bound, object_name, env)
        if isinstance(expr, Skipped):
            return (expr,)
        op = "_cbcs_lt" if side == "min" else "_cbcs_gt"
        sides.append("%s(%s, %s)" % (op, compare[0], expr.source))
        helpers.extend(expr.helpers)
        reads.extend(expr.reads)
    if not sides:
        return ()
    return (
        RuntimeCheck(
            "Range",
            "value is not None and (%s)" % " or ".join(sides),
            repr(_sentence(item.message, _range_message(label, item.min, item.max))),
            tuple(helpers) + ("_cbcs_lt", "_cbcs_gt"),
            tuple(reads),
        ),
    )


def _pattern_arm(item: Pattern, label: str) -> RuntimeCheck:
    return RuntimeCheck(
        "Pattern",
        "value is not None and not _cbcs_matches(value, %s)" % repr(item.pattern),
        repr(_sentence(item.message, "%s is not in the right format" % label)),
        ("_cbcs_matches",),
        (),
    )


def _preset_arm(item: Preset, label: str) -> RuntimeCheck:
    helper = {"email": "_cbcs_is_email", "phone": "_cbcs_is_phone", "zip": "_cbcs_is_zip"}[item.name]
    defaults = {
        "email": "Enter an email address like name@example.com",
        "phone": "Enter a phone number",
        "zip": "Enter a ZIP code like 12345",
    }
    return RuntimeCheck(
        item.name,
        "value is not None and not %s(value)" % helper,
        repr(_sentence(item.message, defaults[item.name])),
        (helper,),
        (),
    )


def _one_of_arm(item: OneOf, label: str) -> RuntimeCheck:
    shown = ", ".join(str(value) for value in item.values)
    return RuntimeCheck(
        "One of",
        "value is not None and value not in %s" % repr(tuple(item.values)),
        repr(_sentence(item.message, "%s must be one of %s" % (label, shown))),
        (),
        (),
    )


def _formula_arm(item: FormulaCheck, object_name: str, env: Optional[FormulaEnv]) -> Union[RuntimeCheck, Skipped]:
    if env is None:
        return _skipped(object_name, "formula", "message")
    analysis = analyze(item.formula, env, _slot_check())
    problem = _error_problem(analysis)
    if problem is not None:
        return _skipped(object_name, problem.message, problem.code)
    if item.message is None:
        return _skipped(object_name, "formula", "message")
    if getattr(analysis, "tree", None) is None:
        return _skipped(object_name, "formula", "FB108")
    try:
        emitted = compile_formula(analysis, env)
    except Exception:
        return _skipped(object_name, "formula", "FB108")
    reads = tuple(sorted(name for name in analysis.reads if name != object_name and is_name(name)))
    return RuntimeCheck(
        "Formula",
        "not (%s)" % emitted.source,
        repr(item.message),
        tuple(emitted.helpers),
        reads,
    )


def _bound_expression(
    class_name: str,
    kind: str,
    bound: Bound,
    object_name: str,
    env: Optional[FormulaEnv],
) -> Union["_BoundExpr", Skipped]:
    if bound.number is not None:
        return _BoundExpr(repr(bound.number), (), ())
    text = bound.formula or ""
    if env is None:
        return _skipped(object_name, "range", "message")
    from app.features.form_builder.engine.logic.formula.env import SlotKind

    analysis = analyze(text, env, SlotKind.range_bound(_bound_target(class_name, kind)))
    problem = _error_problem(analysis)
    if problem is not None:
        return _skipped(object_name, problem.message, problem.code)
    if getattr(analysis, "tree", None) is None:
        return _skipped(object_name, "range", "FB108")
    try:
        emitted = compile_formula(analysis, env)
    except Exception:
        return _skipped(object_name, "range", "FB108")
    reads = tuple(sorted(name for name in analysis.reads if name != object_name and is_name(name)))
    return _BoundExpr(emitted.source, tuple(emitted.helpers), reads)


@dataclass(frozen=True)
class _BoundExpr:
    source: str
    helpers: Tuple[str, ...]
    reads: Tuple[str, ...]


def _slot_check() -> object:
    from app.features.form_builder.engine.logic.formula.env import SlotKind

    return SlotKind.check()


def _error_problem(analysis: object) -> Optional[object]:
    for problem in getattr(analysis, "problems", ()) or ():
        spec = CODES.get(getattr(problem, "code", ""))
        if spec is None or spec.severity == Severity.ERROR:
            return problem
    return None


def _skipped(widget: str, words: str, code: str) -> Skipped:
    name = widget or "check"
    return Skipped(one_line("# %s: %s skipped (%s: see Problems)" % (name, words, code)), code)


def _sentence(stored: Optional[str], default: str) -> str:
    if stored is not None:
        return stored
    return default


def _length_message(label: str, low: Optional[int], high: Optional[int]) -> str:
    if low is not None and high is not None:
        return "%s must be %s to %s characters" % (label, low, high)
    if low is not None:
        return "%s must be at least %s characters" % (label, low)
    return "%s must be at most %s characters" % (label, high)


def _range_message(label: str, low: Optional[Bound], high: Optional[Bound]) -> str:
    if low is not None and high is not None:
        return "%s must be between %s and %s" % (label, _bound_words(low), _bound_words(high))
    if low is not None:
        return "%s must be at least %s" % (label, _bound_words(low))
    if high is not None:
        return "%s must be at most %s" % (label, _bound_words(high))
    return "%s is out of range" % label


def _bound_words(bound: Bound) -> str:
    if bound.number is not None:
        return str(bound.number)
    return bound.formula or ""


def _kind_reader(kind: str, object_name: str, decimals: int) -> Tuple[str, Tuple[str, ...]]:
    target = "self.%s" % object_name if object_name else "value"
    family = numeric_family(kind)
    if not object_name:
        return "_cbcs_number(value)", ("_cbcs_number",)
    if family == "whole":
        return "_cbcs_read_whole(%s)" % target, ("_cbcs_read_whole",)
    if family == "money":
        return "_cbcs_read_money(%s)" % target, ("_cbcs_read_money",)
    if family == "percent":
        return "_cbcs_read_percent(%s)" % target, ("_cbcs_read_percent",)
    places = _places(kind, decimals)
    return "_cbcs_read_number(%s, %d)" % (target, places), ("_cbcs_read_number",)


def _compare_value(class_name: str, kind: str, object_name: str, decimals: int) -> Tuple[str, Tuple[str, ...]]:
    if class_name == "QLineEdit" and numeric_family(kind):
        return _kind_reader(kind, object_name, decimals)
    return "value", ()


def _places(kind: str, decimals: int) -> int:
    if _suffix_number(kind, "number:"):
        return int(kind.split(":", 1)[1])
    return decimals


def _suffix_number(kind: str, prefix: str) -> bool:
    if not kind.startswith(prefix):
        return False
    rest = kind[len(prefix) :]
    return bool(rest) and rest.isdigit()


def _min_prop(class_name: str) -> Optional[str]:
    if class_name in ("QSpinBox", "QDoubleSpinBox"):
        return "minimum"
    if class_name == "QDateEdit":
        return "minimumDate"
    return None


def _max_prop(class_name: str) -> Optional[str]:
    if class_name in ("QSpinBox", "QDoubleSpinBox"):
        return "maximum"
    if class_name == "QDateEdit":
        return "maximumDate"
    return None


def _native_bound(class_name: str, bound: Optional[Bound]) -> Optional[Value]:
    if bound is None:
        return None
    if class_name == "QSpinBox" and isinstance(bound.number, int):
        return NumberValue(bound.number)
    if class_name == "QSpinBox" and isinstance(bound.number, float) and bound.number.is_integer():
        return NumberValue(int(bound.number))
    if class_name == "QDoubleSpinBox" and isinstance(bound.number, (int, float)) and not isinstance(bound.number, bool):
        return DoubleValue(float(bound.number))
    if class_name == "QDateEdit" and bound.formula is not None:
        return _iso_date(bound.formula)
    return None


def _iso_date(text: str) -> Optional[DateValue]:
    if _ISO_DATE.match(text) is None:
        return None
    year = int(text[0:4])
    month = int(text[5:7])
    day = int(text[8:10])
    try:
        datetime.date(year, month, day)
    except ValueError:
        return None
    return DateValue(year, month, day)


def _bound_target(class_name: str, kind: str) -> FType:
    if class_name in ("QSpinBox", "QDoubleSpinBox"):
        return NUMBER
    if class_name == "QDateEdit":
        return DATE
    if numeric_family(kind):
        return NUMBER
    return TEXT


def _translate_pattern(pattern: str) -> Optional[str]:
    if len(pattern) < 2 or pattern[0] != "^" or pattern[-1] != "$":
        return None
    body = pattern[1:-1]
    if not body or any(ch in body for ch in "+*?|()"):
        return None
    pieces: List[str] = []
    index = 0
    while index < len(body):
        piece = _take_piece(body, index)
        if piece is None:
            return None
        pieces.append(piece[0])
        index = piece[1]
    mask = "".join(pieces)
    if not 1 <= len(mask) <= 32:
        return None
    return mask


def _take_piece(body: str, index: int) -> Optional[Tuple[str, int]]:
    for prefix, marker, fill in (("[A-Z]{", ">", "A"), ("[a-z]{", "<", "a"), ("\\d{", "", "9")):
        if body.startswith(prefix, index):
            counted = _brace_count(body, index + len(prefix))
            if counted is None:
                return None
            count, end = counted
            return marker + (fill * count), end
    if body[index] in _LITERALS:
        return body[index], index + 1
    return None


def _brace_count(body: str, index: int) -> Optional[Tuple[int, int]]:
    end = index
    while end < len(body) and body[end].isdigit():
        end += 1
    if end == index or end >= len(body) or body[end] != "}":
        return None
    count = int(body[index:end])
    if count < 1 or count > 32:
        return None
    return count, end + 1


def _is_qt_mask(pattern: str) -> bool:
    if not pattern or len(pattern) > 32 or ";" in pattern:
        return False
    placeholders = 0
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if char == "\\":
            if index + 1 >= len(pattern):
                return False
            index += 2
            continue
        if char in _MASK_BANNED or ord(char) < 32:
            return False
        if char in _CASE_MARKERS:
            index += 1
            continue
        if char in _PLACEHOLDERS:
            placeholders += 1
        index += 1
    return placeholders >= 1


def _class_body(extra: str) -> str:
    chars: List[str] = []
    seen = set()
    for char in extra:
        if char in seen or char in "0123456789.,+-()":
            continue
        seen.add(char)
        if char == "\\":
            chars.append("\\\\")
        elif char == "]":
            chars.append("\\]")
        elif char == "^":
            chars.append("\\^")
        elif char == "-":
            chars.append("\\-")
        else:
            chars.append(char)
    return "".join(chars)


def _message(obj: JsonObject) -> Optional[str]:
    value = obj.get("message")
    if isinstance(value, str):
        return value
    return None


def _used(obj: JsonObject, keys: Tuple[str, ...], *, ints: Tuple[str, ...] = (), bounds: Tuple[str, ...] = ()) -> set:
    used = set()
    for key in keys:
        if not obj.has(key):
            continue
        value = obj.get(key)
        if key == "message" and not isinstance(value, str):
            continue
        if key in ints and _as_int(value) is None:
            continue
        if key in bounds and _bound(value) is None:
            continue
        if key == "pattern" and not isinstance(value, str):
            continue
        if key == "formula" and not isinstance(value, str):
            continue
        if key == "values" and _one_of_values(value) is None:
            continue
        used.add(key)
    return used


def _extra(pairs: Tuple[Tuple[str, JsonValue], ...], used: set) -> Tuple[Tuple[str, object], ...]:
    return tuple((key, value) for key, value in pairs if key not in used)


def _as_int(value: object) -> Optional[int]:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _bound(value: object) -> Optional[Bound]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return Bound(number=value)
    if isinstance(value, float):
        return Bound(number=value)
    if isinstance(value, str):
        return Bound(formula=value)
    return None


def _bound_json(bound: Bound) -> JsonValue:
    if bound.number is not None:
        return bound.number
    return bound.formula or ""


def _one_of_values(value: object) -> Optional[Tuple[Union[str, int, float], ...]]:
    if not isinstance(value, tuple):
        return None
    found: List[Union[str, int, float]] = []
    for item in value:
        if isinstance(item, bool):
            return None
        if isinstance(item, (str, int, float)):
            found.append(item)
        else:
            return None
    return tuple(found)


def _load_names(source: str) -> set:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    return {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
