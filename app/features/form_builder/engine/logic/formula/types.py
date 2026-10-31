"""Formula types, widget values, and arithmetic results (CONTRACTS.md 17.4).

The tables are the design. A new widget class or coercion is a row, not a branch
in the checker. WHOLE and MONEY sit under NUMBER for comparisons.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Dict, Mapping, Optional, Tuple


class FKind(Enum):
    """One design-time type, or a wrapper (choice, column) around another."""

    TEXT = "text"
    WHOLE = "whole"
    NUMBER = "number"
    MONEY = "money"
    YESNO = "yesno"
    DATE = "date"
    TIME = "time"
    DATETIME = "datetime"
    PAGE = "page"
    ANY = "any"
    BLANK = "blank"
    CHOICE = "choice"
    COLUMN = "column"


@dataclass(frozen=True)
class FType:
    """A formula type. ``item`` is set only for choice(T) and column(T)."""

    kind: FKind
    item: Optional["FType"] = None

    def __post_init__(self) -> None:
        wrapped = self.kind in (FKind.CHOICE, FKind.COLUMN)
        if wrapped and self.item is None:
            raise ValueError("%s needs an inner type" % self.kind.value)
        if not wrapped and self.item is not None:
            raise ValueError("%s does not take an inner type" % self.kind.value)


def choice(inner: FType) -> FType:
    return FType(FKind.CHOICE, inner)


def column(inner: FType) -> FType:
    return FType(FKind.COLUMN, inner)


TEXT = FType(FKind.TEXT)
WHOLE = FType(FKind.WHOLE)
NUMBER = FType(FKind.NUMBER)
MONEY = FType(FKind.MONEY)
YESNO = FType(FKind.YESNO)
DATE = FType(FKind.DATE)
TIME = FType(FKind.TIME)
DATETIME = FType(FKind.DATETIME)
PAGE = FType(FKind.PAGE)
ANY = FType(FKind.ANY)
BLANK = FType(FKind.BLANK)

_PHRASE = {
    FKind.TEXT: "text",
    FKind.WHOLE: "a whole number",
    FKind.NUMBER: "a number",
    FKind.MONEY: "money",
    FKind.YESNO: "a yes or no",
    FKind.DATE: "a date",
    FKind.TIME: "a time",
    FKind.DATETIME: "a date and time",
    FKind.PAGE: "a page",
    FKind.ANY: "a window value",
    FKind.BLANK: "blank",
    FKind.CHOICE: "a choice",
    FKind.COLUMN: "a column",
}


def type_phrase(value: FType) -> str:
    """The words FB102 puts in the sentence. Never says null or None."""
    return _PHRASE[value.kind]


def unwrap(value: FType) -> FType:
    """choice(T) is T for arithmetic and comparison. column(T) stays a column."""
    if value.kind == FKind.CHOICE and value.item is not None:
        return value.item
    return value


def is_numeric(value: FType) -> bool:
    return unwrap(value).kind in (FKind.WHOLE, FKind.NUMBER, FKind.MONEY)


def numeric_family(value: FType) -> bool:
    return is_numeric(value) or unwrap(value).kind == FKind.BLANK


_KIND_NAMES = {
    "text": TEXT,
    "whole": WHOLE,
    "number": NUMBER,
    "money": MONEY,
    "percent": NUMBER,
    "date": DATE,
    "time": TIME,
}


def type_from_kind(kind: str) -> Optional[FType]:
    """Map a cbcsKind token to a type. ``number:N`` (N in 0..6) is a number.

    Unknown kinds return None so the caller can warn and read text.
    """
    text = kind.strip()
    if text in _KIND_NAMES:
        return _KIND_NAMES[text]
    if text.startswith("number:"):
        places = text[len("number:") :]
        if places.isdigit() and 0 <= int(places) <= 6:
            return NUMBER
    return None


@dataclass(frozen=True)
class ValueSpec:
    """One row of LOGIC_DESIGN section 4.3. Strings are the table, not prose."""

    type_rule: str
    read: str
    blank_rule: str
    write: str


# Keyed by Qt class. A subclass resolves to the nearest name in this map.
VALUE_TABLE: Mapping[str, ValueSpec] = {
    "QLineEdit": ValueSpec(
        "kind",
        "text().strip(), parsed by kind",
        "empty after stripping, or unparsable",
        "setText(formatted)",
    ),
    "QPlainTextEdit": ValueSpec(
        "kind",
        "toPlainText().strip()",
        "empty",
        "setPlainText",
    ),
    "QTextEdit": ValueSpec(
        "text",
        "toPlainText().strip()",
        "empty",
        "setPlainText",
    ),
    "QLabel": ValueSpec(
        "kind",
        "text()",
        "empty",
        "setText(formatted)",
    ),
    "QSpinBox": ValueSpec(
        "whole",
        "value()",
        "special value at the minimum when allow blank is set",
        "setValue",
    ),
    "QSlider": ValueSpec("whole", "value()", "never", "setValue"),
    "QDial": ValueSpec("whole", "value()", "never", "setValue"),
    "QProgressBar": ValueSpec("whole", "value()", "never", "setValue"),
    "QDoubleSpinBox": ValueSpec(
        "number_or_money",
        "Decimal of value(), rounded to decimals()",
        "special value at the minimum when allow blank is set",
        "setValue(float(x))",
    ),
    "QCheckBox": ValueSpec(
        "yesno",
        "isChecked()",
        "tri-state and partially checked",
        "setChecked",
    ),
    "QRadioButton": ValueSpec("yesno", "isChecked()", "never", "setChecked"),
    "QButtonGroup": ValueSpec(
        "text",
        "the checked button's cbcsChoice, or its object name",
        "none checked",
        "check the matching button",
    ),
    "QComboBox": ValueSpec(
        "choice_or_text",
        "currentData() when items have data, else currentText()",
        "index -1, a blank first item, or empty text",
        "select by data, or by text",
    ),
    "QDateEdit": ValueSpec(
        "date",
        "date().toPython()",
        "special value at minimumDate when allow blank is set",
        "setDate",
    ),
    "QTimeEdit": ValueSpec(
        "time",
        "time().toPython()",
        "special value at the minimum when allow blank is set",
        "setTime",
    ),
    "QDateTimeEdit": ValueSpec(
        "datetime",
        "dateTime().toPython()",
        "special value at the minimum when allow blank is set",
        "setDateTime",
    ),
    "QTabWidget": ValueSpec("page", "currentWidget()", "never", "setCurrentWidget"),
    "QStackedWidget": ValueSpec("page", "currentWidget()", "never", "setCurrentWidget"),
    "QListWidget": ValueSpec(
        "text",
        "currentItem().text()",
        "no current item",
        "select the matching item",
    ),
    "QTableView": ValueSpec(
        "none",
        "no main value; use attributes",
        "not applicable",
        "not applicable",
    ),
}

_KIND_CLASSES = frozenset({"QLineEdit", "QLabel", "QPlainTextEdit"})
_RULE_TYPE = {
    "text": TEXT,
    "whole": WHOLE,
    "date": DATE,
    "time": TIME,
    "datetime": DATETIME,
    "page": PAGE,
    "yesno": YESNO,
}


def lookup_spec(
    class_name: str,
    chain: Tuple[str, ...],
) -> Tuple[Optional[str], Optional[ValueSpec]]:
    """Return ``(matched class, spec)`` for the nearest listed base, or neither."""
    names = (class_name,) + tuple(name for name in chain if name != class_name)
    for name in names:
        spec = VALUE_TABLE.get(name)
        if spec is not None:
            return name, spec
    return None, None


def main_type(
    spec: ValueSpec,
    matched_class: str,
    *,
    kind: str,
    prefix: str,
    decimals: int,
    has_items_data: bool,
) -> Tuple[Optional[FType], bool]:
    """Return ``(type, unknown_kind)``. None means the widget has no main value."""
    rule = spec.type_rule
    if rule == "none":
        return None, False
    if rule == "kind":
        if matched_class not in _KIND_CLASSES:
            return TEXT, False
        token = kind.strip() or "text"
        found = type_from_kind(token)
        if found is None:
            return TEXT, True
        return found, False
    if rule == "number_or_money":
        if prefix == "$" and decimals == 2:
            return MONEY, False
        return NUMBER, False
    if rule == "choice_or_text":
        if has_items_data:
            return choice(TEXT), False
        return TEXT, False
    return _RULE_TYPE[rule], False


# Arithmetic results. Missing pairs are FB102. BLANK is applied before lookup:
# a blank side keeps the other side's type (text plus blank is text).
def _fill_arith() -> Dict[Tuple[str, FKind, FKind], FKind]:
    table: Dict[Tuple[str, FKind, FKind], FKind] = {}
    numeric = (FKind.WHOLE, FKind.NUMBER, FKind.MONEY)
    for op in ("+", "-", "*"):
        for left in numeric:
            for right in numeric:
                if left == FKind.MONEY or right == FKind.MONEY:
                    result = FKind.MONEY
                elif left == FKind.WHOLE and right == FKind.WHOLE:
                    result = FKind.WHOLE
                else:
                    result = FKind.NUMBER
                table[(op, left, right)] = result
    for left in numeric:
        for right in numeric:
            if left == FKind.MONEY or right == FKind.MONEY:
                table[("/", left, right)] = FKind.MONEY
            else:
                table[("/", left, right)] = FKind.NUMBER
    table[("+", FKind.TEXT, FKind.TEXT)] = FKind.TEXT
    table[("+", FKind.DATE, FKind.WHOLE)] = FKind.DATE
    table[("+", FKind.WHOLE, FKind.DATE)] = FKind.DATE
    table[("-", FKind.DATE, FKind.WHOLE)] = FKind.DATE
    table[("-", FKind.DATE, FKind.DATE)] = FKind.WHOLE
    return table


ARITH: Mapping[Tuple[str, FKind, FKind], FKind] = _fill_arith()

_ORDER = (FKind.WHOLE, FKind.NUMBER, FKind.MONEY, FKind.TEXT, FKind.DATE, FKind.TIME, FKind.DATETIME, FKind.YESNO, FKind.PAGE)


def same_or_numeric(left: FType, right: FType) -> bool:
    """True when two types may be compared with ``==`` or ordered."""
    a = unwrap(left)
    b = unwrap(right)
    if a.kind == FKind.BLANK or b.kind == FKind.BLANK:
        return True
    if a.kind == FKind.ANY or b.kind == FKind.ANY:
        return True
    if is_numeric(a) and is_numeric(b):
        return True
    return a.kind == b.kind and a.kind in _ORDER


def assignable(src: FType, target: FType) -> bool:
    """True when a value slot can store ``src`` in a widget of type ``target``.

    Whole fits a number. A number fits money (it rounds). Anything else going
    to text needs ``text()``, so that pair is not assignable.
    """
    a = unwrap(src)
    b = unwrap(target)
    if a.kind == FKind.BLANK or a.kind == FKind.ANY or b.kind == FKind.ANY:
        return True
    if a.kind == b.kind:
        return True
    if b.kind == FKind.NUMBER and a.kind in (FKind.WHOLE, FKind.MONEY):
        return True
    if b.kind == FKind.MONEY and a.kind in (FKind.WHOLE, FKind.NUMBER):
        return True
    if b.kind == FKind.WHOLE and a.kind == FKind.WHOLE:
        return True
    return False


def widen_numeric(types: Tuple[FType, ...]) -> FType:
    """The smallest numeric type that holds every argument."""
    kinds = [unwrap(item).kind for item in types]
    if any(kind == FKind.MONEY for kind in kinds):
        return MONEY
    if any(kind == FKind.NUMBER for kind in kinds):
        return NUMBER
    if any(kind == FKind.ANY for kind in kinds):
        return ANY
    return WHOLE


def decimal_from_literal(token: str) -> Decimal:
    """Build a non-integer from its source text, underscores removed."""
    return Decimal(token.replace("_", ""))


def whole_from_literal(token: str) -> int:
    return int(token.replace("_", ""))
