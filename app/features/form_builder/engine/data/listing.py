"""Which widgets a list screen can search or filter with.

The check and the expander both read this map, so a widget that warns at
design time is the same widget the running form refuses to read.
"""

from __future__ import annotations

from typing import Dict, Tuple

# class name -> (getter, strftime-style pattern or "").
# A date getter is turned into ``getter.toString(pattern)`` in generated code.
# UX-LIST-001: a blank combo means any row, an empty line edit means any row.
# A checkbox, spin box, or date always has a value, so it is not a filter.
VALUE_READ: Dict[str, Tuple[str, str]] = {
    "QLineEdit": ("text()", ""),
    "QComboBox": ("currentText()", ""),
}

FILTER_SIGNAL = {
    "QLineEdit": "textChanged",
    "QComboBox": "currentTextChanged",
}
