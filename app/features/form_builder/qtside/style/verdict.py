"""The check of a style sheet with Qt's verdict, cached by text (UX-STYLE-004)."""

from __future__ import annotations

from typing import Dict

from app.features.form_builder.engine.style.check import Check, check_sheet
from app.features.form_builder.qtside.style.probe import qt_reads

_CACHE: Dict[str, Check] = {}
_LIMIT = 128


def check_text(text: str) -> Check:
    """Engine check plus Qt's verdict. Empty text is not asked about."""
    found = _CACHE.get(text)
    if found is not None:
        return found
    found = check_sheet(text) if not text.strip() else check_sheet(text, qt_reads(text))
    if len(_CACHE) >= _LIMIT:
        _CACHE.clear()
    _CACHE[text] = found
    return found


def summary_text(text: str) -> str:
    """"None", "1 rule", "{n} rules" or "Can't be read" (UX-STYLE-001)."""
    if not text.strip():
        return "None"
    found = check_text(text)
    if not found.applies:
        return "Can't be read"
    count = found.sheet.rule_count
    if count == 0:
        return "None"
    return "1 rule" if count == 1 else "%d rules" % count
