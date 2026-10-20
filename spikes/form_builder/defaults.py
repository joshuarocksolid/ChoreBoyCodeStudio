"""Properties we do not write when they already match a fresh Qt widget.

stdset="0" properties are kept. They are dynamic values on custom widgets.
"""

from __future__ import annotations

# (class or "*", property name, xml kind, xml text)
_EXACT = {
    ("*", "enabled", "bool", "true"),
    ("*", "visible", "bool", "true"),
    ("QComboBox", "editable", "bool", "false"),
    ("QAbstractButton", "checked", "bool", "false"),
    ("QCheckBox", "checked", "bool", "false"),
    ("QRadioButton", "checked", "bool", "false"),
    ("QPushButton", "checked", "bool", "false"),
    ("QPushButton", "checkable", "bool", "false"),
    ("QGroupBox", "flat", "bool", "false"),
    ("QGroupBox", "checkable", "bool", "false"),
    ("QSpinBox", "minimum", "number", "0"),
    ("QSpinBox", "maximum", "number", "99"),
    ("QSpinBox", "value", "number", "0"),
    ("QSpinBox", "singleStep", "number", "1"),
    ("QDoubleSpinBox", "decimals", "number", "2"),
    ("QLineEdit", "readOnly", "bool", "false"),
    ("QLineEdit", "text", "string", ""),
    ("QLabel", "text", "string", ""),
    ("QPushButton", "text", "string", ""),
}


def is_default_property(class_name: str, prop) -> bool:
    if "stdset" in prop.attrib:
        return False
    if prop.body.children:
        return False
    kind = prop.body.tag
    text = prop.body.text
    if (class_name, prop.name, kind, text) in _EXACT:
        return True
    if ("*", prop.name, kind, text) in _EXACT:
        return True
    if class_name == "QDoubleSpinBox" and prop.name in {"minimum", "value"} and kind == "double":
        try:
            return float(text) == 0.0
        except ValueError:
            return False
    if class_name == "QDoubleSpinBox" and prop.name == "maximum" and kind == "double":
        try:
            return abs(float(text) - 99.99) < 1e-9
        except ValueError:
            return False
    if class_name == "QDoubleSpinBox" and prop.name == "singleStep" and kind == "double":
        try:
            return float(text) == 1.0
        except ValueError:
            return False
    return False
