"""Which strings get a Translation disclosure, and which go to ``retranslateUi``.

The generator rule lives in ``engine/codegen/emit.py`` (``_translated``). This
module repeats that rule for the inspector without importing the generator.
A disclosure is shown for string, string-list and URL values except names the
spec keeps plain (style sheet, input mask). C strings never get one.
"""

from __future__ import annotations

from app.features.form_builder.engine.ui4.values import StringListValue, StringValue, UrlValue, Value

_PLAIN_NAMES = frozenset({"styleSheet", "inputMask"})


def shows_translation(qt_name: str, element: str) -> bool:
    """True when the row should offer Translation (UX-PED-041, UX-PED-046)."""
    if qt_name in _PLAIN_NAMES:
        return False
    return element in (StringValue.ELEMENT, StringListValue.ELEMENT, UrlValue.ELEMENT)


def in_retranslate(value: Value) -> bool:
    """True when generated code places this value in ``retranslateUi``.

    Same rule as the generator: a string, string list or URL is translated
    unless ``notr`` is true. Every other value is a literal in ``setupUi``.
    """
    if isinstance(value, StringValue):
        return value.notr is not True
    if isinstance(value, StringListValue):
        return value.notr is not True
    if isinstance(value, UrlValue):
        return value.string.notr is not True
    return False
