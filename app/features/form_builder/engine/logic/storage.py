"""Logic property keys the command log and change events share.

The full codec arrives with M6.0b. ``SetLogic`` writes canonical text it is given.
This module is the one place that decides which ``cbcs*`` names are logic.
"""

from __future__ import annotations

from typing import List, Sequence, Tuple

from app.features.form_builder.engine.ui4.values import StringListValue, StringValue, Value

SUPPORTED_LOGIC_VERSION = 1

CBCS_LAYOUT_KEYS: Tuple[str, ...] = ("cbcsSplitterSizes",)

LOGIC_PROPERTY_ORDER: Tuple[str, ...] = (
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
    "cbcsData",
    "cbcsBind",
    "cbcsBindMode",
    "cbcsLookup",
    "cbcsRows",
    "cbcsChoice",
)


def is_logic_key(name: str) -> bool:
    """A dynamic property starting with ``cbcs``, except layout keys such as splitter sizes."""
    return name.startswith("cbcs") and name not in CBCS_LAYOUT_KEYS


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


def is_user_logic_key(name: str) -> bool:
    """A logic key other than the root ``cbcsLogic`` version marker."""
    return is_logic_key(name) and name != "cbcsLogic"


def logic_version_text(version: int = SUPPORTED_LOGIC_VERSION) -> str:
    """Canonical ``cbcsLogic`` payload. One object, no spaces, stable key order."""
    return '{"version":%d}' % version
