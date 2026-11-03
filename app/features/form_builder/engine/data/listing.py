"""Which widgets a list screen can search or filter with.

The check and the expander both read this map, so a widget that warns at
design time is the same widget the running form refuses to read.
"""

from __future__ import annotations

from typing import Dict, Tuple

# class name -> (getter, strftime-style pattern or "").
# A date getter is turned into ``getter.toString(pattern)`` in generated code.
VALUE_READ: Dict[str, Tuple[str, str]] = {
    "QLineEdit": ("text()", ""),
    "QPlainTextEdit": ("toPlainText()", ""),
    "QTextEdit": ("toPlainText()", ""),
    "QComboBox": ("currentText()", ""),
    "QSpinBox": ("value()", ""),
    "QDoubleSpinBox": ("value()", ""),
    "QCheckBox": ("isChecked()", ""),
    "QDateEdit": ("date()", "yyyy-MM-dd"),
    "QTimeEdit": ("time()", "HH:mm:ss"),
    "QDateTimeEdit": ("dateTime()", "yyyy-MM-dd HH:mm:ss"),
}

FILTER_SIGNAL = {
    "QLineEdit": "textChanged",
    "QPlainTextEdit": "textChanged",
    "QTextEdit": "textChanged",
    "QComboBox": "currentTextChanged",
    "QSpinBox": "valueChanged",
    "QDoubleSpinBox": "valueChanged",
    "QCheckBox": "toggled",
    "QDateEdit": "dateChanged",
    "QTimeEdit": "timeChanged",
    "QDateTimeEdit": "dateTimeChanged",
}
