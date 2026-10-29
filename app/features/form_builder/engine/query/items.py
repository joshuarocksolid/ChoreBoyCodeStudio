"""Item text as the file stores it: earlier columns, then the typed text."""

from __future__ import annotations

from typing import List, Optional, Tuple

from app.features.form_builder.engine.ui4.opaque import OpaqueElement
from app.features.form_builder.engine.ui4.values import StringValue


def column_texts(node: object) -> Tuple[str, ...]:
    """Every column of an item or header, first column first."""
    spec = node.to_spec() if hasattr(node, "to_spec") else node
    typed = [
        entry.value.text
        for entry in spec.properties  # type: ignore[attr-defined]
        if entry.name == "text" and isinstance(entry.value, StringValue)
    ]
    if len(typed) > 1:
        return tuple(typed)
    earlier: List[str] = []
    for child in spec.children("opaque"):  # type: ignore[attr-defined]
        element = child.field("element")
        if not isinstance(element, OpaqueElement):
            continue
        if element.tag != "property" or dict(element.attrs).get("name") != "text":
            continue
        text = _string_of(element)
        if text is not None:
            earlier.append(text)
    if typed:
        return tuple(earlier + typed)
    if earlier:
        return tuple(earlier)
    return ("",)


def _string_of(element: OpaqueElement) -> Optional[str]:
    for child in element.children:
        if isinstance(child, OpaqueElement) and child.tag == "string":
            return "".join(part for part in child.children if isinstance(part, str))
    return None
