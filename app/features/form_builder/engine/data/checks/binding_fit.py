"""Fit helpers for a column dropped onto a widget.

FB304 itself is published by ``checks/record.py``. These helpers answer the
drop hint. Integer foreign keys stay spin boxes in this lane, so a reference
is not passed in: a lookup combo is M8.3a.
"""

from __future__ import annotations

from app.features.form_builder.engine.diagnostics import CODES

_CLASS_WORDS = {
    "QSpinBox": "spin box",
    "QDoubleSpinBox": "number box",
    "QLineEdit": "line edit",
    "QPlainTextEdit": "text box",
    "QTextEdit": "text box",
    "QCheckBox": "check box",
    "QRadioButton": "radio button",
    "QDateEdit": "date box",
    "QTimeEdit": "time box",
    "QDateTimeEdit": "date and time box",
    "QComboBox": "combo box",
    "QLabel": "label",
    "QSlider": "slider",
    "QDial": "dial",
}


def register(registry: object) -> None:
    """Present so discovery loads the helpers. The check lives in ``record.py``."""

    del registry


def class_words(class_name: str) -> str:
    """The widget phrase FB304 uses: ``check box``, ``line edit``."""

    found = _CLASS_WORDS.get(class_name)
    if found:
        return found
    text = class_name[1:] if class_name.startswith("Q") else class_name
    return text or "widget"


def compatible(direction: str, class_name: str, kind_name: str = "") -> bool:
    """True when ``class_name`` can show a column of ``direction``.

    ``kind_name`` is the widget's ``cbcsKind``. A line edit shows a date only
    when that kind says ``date``.
    """

    if class_name == "QLabel" or class_name.endswith("Layout"):
        return False
    if direction == "int":
        return class_name in ("QSpinBox", "QDoubleSpinBox", "QComboBox", "QSlider", "QDial")
    if direction == "decimal":
        return class_name in ("QDoubleSpinBox", "QLineEdit")
    if direction == "text":
        return class_name in ("QLineEdit", "QPlainTextEdit", "QTextEdit", "QComboBox")
    if direction == "date":
        if class_name == "QDateEdit":
            return True
        return class_name == "QLineEdit" and kind_name == "date"
    if direction == "bool":
        return class_name in ("QCheckBox", "QRadioButton")
    if direction == "time":
        return class_name == "QTimeEdit"
    if direction == "datetime":
        return class_name == "QDateTimeEdit"
    return class_name == "QLineEdit"


def mismatch_sentence(kind_words: str, class_name: str) -> str:
    """``A date column can't be shown in a check box.``"""

    template = CODES["FB304"].title
    return template.replace("{type words}", kind_words).replace("{class words}", class_words(class_name))
