"""Pure helpers for editor overlay/highlighting policy decisions.

Re-exported from :mod:`app.core.highlighting_policy` for backward compatibility.
"""

from __future__ import annotations

from app.core.highlighting_policy import (
    effective_highlighting_mode,
    is_large_document,
    visible_document_window,
)

__all__ = [
    "effective_highlighting_mode",
    "is_large_document",
    "visible_document_window",
]
