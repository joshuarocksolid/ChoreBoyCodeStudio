"""Logic storage codec: the seam M6.0b fills (LOGIC_DESIGN section 6; CONTRACTS.md 2.4.3).

Only what other contracts depend on is fixed here.
"""

from __future__ import annotations

from typing import Tuple

#: Highest ``cbcsLogic`` version this build reads and writes.
SUPPORTED_LOGIC_VERSION = 1

#: Write order of logic properties after all standard properties
#: (LOGIC_DESIGN 6.1 table order). ``cbcsOn*`` keys sort after the fixed keys
#: below by signal name; unknown ``cbcs*`` keys sort last by name and are
#: preserved verbatim.
#: ``cbcs*`` keys that are layout data, not logic: set by SetProperty, never
#: add ``cbcsLogic``, not read-only under FB402, category "property".
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
    """True for any dynamic property whose name starts with ``cbcs`` and is not in
    ``CBCS_LAYOUT_KEYS``."""
    ...


def canonical_json(value: object) -> str:
    """LOGIC_DESIGN 6.3: keys in schema order, ``ensure_ascii=False``, integers
    without ``.0``, arrays of objects one object per line, small objects on one
    line, no trailing spaces. Unknown keys are kept after known keys in their
    original order."""
    ...
