"""Pure helpers for editor overlay/highlighting policy decisions."""

from __future__ import annotations

from app.core import constants


def is_large_document(*, document_size: int, reduced_threshold_chars: int) -> bool:
    """Return whether a document should be treated as large."""
    return document_size > reduced_threshold_chars


def effective_highlighting_mode(
    *,
    adaptive_mode: str,
    document_size: int,
    reduced_threshold_chars: int,
    lexical_only_threshold_chars: int,
) -> str:
    """Resolve runtime highlighting mode from policy + document size."""
    if adaptive_mode == constants.HIGHLIGHTING_MODE_LEXICAL_ONLY:
        return constants.HIGHLIGHTING_MODE_LEXICAL_ONLY
    if document_size >= lexical_only_threshold_chars:
        return constants.HIGHLIGHTING_MODE_LEXICAL_ONLY
    if (
        adaptive_mode == constants.HIGHLIGHTING_MODE_REDUCED
        or document_size >= reduced_threshold_chars
    ):
        return constants.HIGHLIGHTING_MODE_REDUCED
    return constants.HIGHLIGHTING_MODE_NORMAL


def visible_document_window(
    *,
    top_position: int,
    bottom_position: int,
    max_position: int,
    margin: int,
) -> tuple[int, int]:
    """Compute a bounded visible-character window with margins applied."""
    start = max(0, min(top_position, bottom_position) - margin)
    end = min(max_position, max(top_position, bottom_position) + margin)
    return (start, max(start + 1, end))
