"""Change signals a rule or a check connects to (CONTRACTS section 18.2). Qt-free.

``class_name`` wins, then each base in order, so the caller passes bases
nearest first. A class the table does not name has no signal: the core skips
that connect instead of guessing.
"""

from __future__ import annotations

from typing import Optional, Sequence

CHANGE_SIGNALS = {
    "QLineEdit": "textChanged",
    "QPlainTextEdit": "textChanged",
    "QTextEdit": "textChanged",
    "QSpinBox": "valueChanged",
    "QDoubleSpinBox": "valueChanged",
    "QSlider": "valueChanged",
    "QDial": "valueChanged",
    "QCheckBox": "toggled",
    "QRadioButton": "toggled",
    "QComboBox": "currentIndexChanged",
    "QDateEdit": "dateChanged",
    "QTimeEdit": "timeChanged",
    "QDateTimeEdit": "dateTimeChanged",
}


def change_signal(class_name: str, bases: Sequence[str]) -> Optional[str]:
    """``class_name`` first, then ``bases``, first hit. Nearest base."""
    found = CHANGE_SIGNALS.get(class_name)
    if found is not None:
        return found
    for name in bases:
        found = CHANGE_SIGNALS.get(name)
        if found is not None:
            return found
    return None
