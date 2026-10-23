"""Map kept XML spans onto editor gutter notes."""

from __future__ import annotations

from typing import Tuple

from app.editors.code_editor_chrome_mixin import LineNote
from app.features.form_builder.engine.ui4.kept import kept_spans

KEPT_AS_IS = "Kept as is"


def line_notes_for_xml(text: str) -> Tuple[LineNote, ...]:
    return tuple(
        LineNote(span.first_line, span.last_line, KEPT_AS_IS, span.reasons)
        for span in kept_spans(text)
    )
