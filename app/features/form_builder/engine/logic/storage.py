"""Logic property keys the command log and change events share (CONTRACTS.md section 15.1).

``SetLogic`` writes canonical text from ``engine.logic.codec``. This module is
the one place that decides which ``cbcs*`` names are logic, how they rank when
CBCS inserts a new entry, and what kind of text each one holds.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.features.form_builder.engine.ui4.values import StringListValue, StringValue, Value

SUPPORTED_LOGIC_VERSION = 1

CBCS_LAYOUT_KEYS: Tuple[str, ...] = ("cbcsSplitterSizes",)

#: The prefix of every step-list property: ``cbcsOn`` + the signal name, first letter upper-cased.
SIGNAL_PREFIX = "cbcsOn"

#: The rank slot that every ``cbcsOn<Signal>`` name shares in ``LOGIC_PROPERTY_ORDER``.
SIGNAL_RANK_NAME = "cbcsOn*"

#: Properties whose text is a formula (LOGIC_DESIGN 6.1). Rename rewrites NAME tokens.
FORMULA_KEYS: Tuple[str, ...] = (
    "cbcsEnabledWhen",
    "cbcsVisibleWhen",
    "cbcsReadOnlyWhen",
    "cbcsValue",
    "cbcsDefault",
)

#: Properties whose text is one object name.
LABEL_KEYS: Tuple[str, ...] = ("cbcsErrorLabel", "cbcsErrorSummary")

#: Properties whose text is JSON with an array (checks) or an object at the top, besides ``cbcsOn*``.
JSON_KEYS: Tuple[str, ...] = ("cbcsValidate", "cbcsData", "cbcsLookup", "cbcsRows")

#: Top-level shape each of ``JSON_KEYS`` must have.
JSON_TOP_SHAPE: Dict[str, str] = {
    "cbcsValidate": "array",
    "cbcsData": "object",
    "cbcsLookup": "object",
    "cbcsRows": "object",
}

_ORDER: Tuple[str, ...] = (
    "cbcsSplitterSizes",
    "cbcsLogic",
    "cbcsEnabledWhen",
    "cbcsVisibleWhen",
    "cbcsReadOnlyWhen",
    "cbcsValue",
    "cbcsDefault",
    "cbcsKind",
    "cbcsFormat",
    "cbcsValidate",
    "cbcsErrorLabel",
    "cbcsErrorSummary",
    SIGNAL_RANK_NAME,
    "cbcsData",
    "cbcsBind",
    "cbcsBindMode",
    "cbcsLookup",
    "cbcsRows",
    "cbcsChoice",
)


def _is_ascii_upper(char: str) -> bool:
    return "A" <= char <= "Z"


def _is_ascii_lower(char: str) -> bool:
    return "a" <= char <= "z"


def is_signal_property(name: str) -> bool:
    """True for ``cbcsOn`` followed by an upper-case ASCII letter (form events included)."""
    return len(name) > len(SIGNAL_PREFIX) and name.startswith(SIGNAL_PREFIX) and _is_ascii_upper(name[len(SIGNAL_PREFIX)])


def signal_property(signal_name: str) -> str:
    """``clicked`` -> ``cbcsOnClicked``. Exact inverse of ``signal_of_property`` for names
    that start with a lower-case ASCII letter."""
    if not signal_name:
        return SIGNAL_PREFIX
    first = signal_name[0]
    if _is_ascii_lower(first):
        first = first.upper()
    return SIGNAL_PREFIX + first + signal_name[1:]


def signal_of_property(key: str) -> Optional[str]:
    """``cbcsOnClicked`` -> ``clicked``; None when ``key`` is not a ``cbcsOn<Signal>`` name."""
    if not is_signal_property(key):
        return None
    rest = key[len(SIGNAL_PREFIX):]
    return rest[0].lower() + rest[1:]


class _LogicOrder(tuple):  # type: ignore[type-arg]
    """``LOGIC_PROPERTY_ORDER``. Any ``cbcsOn<Signal>`` name counts as a member and
    ranks at the ``cbcsOn*`` slot, so ``property_rank`` (``ui4/defaults.py``) sorts the
    step lists of one owner among themselves by name without a change there."""

    __slots__ = ()

    def __contains__(self, item: object) -> bool:
        if isinstance(item, str) and is_signal_property(item):
            return True
        return tuple.__contains__(self, item)

    def index(self, value: Any, *args: Any) -> int:  # type: ignore[override]
        if isinstance(value, str) and is_signal_property(value):
            value = SIGNAL_RANK_NAME
        return tuple.index(self, value, *args)


LOGIC_PROPERTY_ORDER: Tuple[str, ...] = _LogicOrder(_ORDER)


def is_logic_key(name: str) -> bool:
    """A dynamic property starting with ``cbcs``, except layout keys such as splitter sizes."""
    return name.startswith("cbcs") and name not in CBCS_LAYOUT_KEYS


def is_user_logic_key(name: str) -> bool:
    """A logic key other than the root ``cbcsLogic`` version marker."""
    return is_logic_key(name) and name != "cbcsLogic"


def text_kind(key: str) -> str:
    """How the text of ``key`` is read: ``steps``, ``json``, ``formula``, ``label`` or ``plain``."""
    if is_signal_property(key):
        return "steps"
    if key in JSON_KEYS:
        return "json"
    if key in FORMULA_KEYS:
        return "formula"
    if key in LABEL_KEYS:
        return "label"
    return "plain"


def splitter_sizes(value: Value) -> Tuple[int, ...]:
    """The pane sizes a ``cbcsSplitterSizes`` value stores. A bad number reads as 0."""
    raw = ""
    if isinstance(value, StringValue):
        raw = value.text
    elif isinstance(value, StringListValue):
        raw = ",".join(value.items)
    found: List[int] = []
    for piece in raw.split(","):
        piece = piece.strip()
        if not piece:
            continue
        try:
            found.append(int(piece))
        except ValueError:
            found.append(0)
    return tuple(found)


def splitter_sizes_value(sizes: Sequence[int]) -> StringValue:
    return StringValue(",".join(str(int(size)) for size in sizes))


def logic_version_text(version: int = SUPPORTED_LOGIC_VERSION) -> str:
    """Canonical ``cbcsLogic`` payload. One object, no spaces, stable key order."""
    return '{"version":%d}' % version
