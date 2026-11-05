"""Class glyphs for outline rows. The names are the Insert catalog's."""

from __future__ import annotations

from typing import Dict, Optional, Tuple

_CACHE: Optional[Dict[str, Tuple[str, ...]]] = None


def glyph_for(qt_class: str, name: str = "") -> str:
    """The catalog glyph for this class. A shared class follows the object name."""
    table = _table()
    key = "spacer" if qt_class in ("Spacer", "spacer") else qt_class
    glyphs = table.get(key)
    if not glyphs:
        return "widget"
    chosen = next(iter(glyphs))
    if len(glyphs) == 1:
        return chosen
    lowered = (name or "").lower()
    if "vertical" in lowered:
        for glyph in glyphs:
            if glyph.endswith("_v"):
                return glyph
    elif "horizontal" in lowered:
        for glyph in glyphs:
            if glyph.endswith("_h"):
                return glyph
    return chosen


def _table() -> Dict[str, Tuple[str, ...]]:
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    from app.features.form_builder.qtside.insert.catalog import load_catalog

    found: Dict[str, list] = {}
    catalog = load_catalog()
    for entry in catalog.entries + catalog.windows:
        bucket = found.setdefault(entry.qt_class, [])
        if entry.glyph and entry.glyph not in bucket:
            bucket.append(entry.glyph)
    _CACHE = {key: tuple(value) for key, value in found.items()}
    return _CACHE
