"""Unit tests for completion row help teaser helpers."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.editors.completion_popup.completion_item_delegate import (  # noqa: E402
    _inline_help_teaser,
    _row_secondary_text,
)
from app.intelligence.completion_models import CompletionItem, CompletionKind  # noqa: E402

pytestmark = pytest.mark.unit


def test_inline_help_teaser_prefers_first_documentation_line() -> None:
    item = CompletionItem(
        label="paint",
        insert_text="paint",
        kind=CompletionKind.METHOD,
        documentation="Draw the widget.\n\nMore detail.",
        signature="(self)",
        detail="method",
    )
    assert _inline_help_teaser(item) == "Draw the widget."


def test_row_secondary_falls_back_to_signature_without_docs() -> None:
    item = CompletionItem(
        label="resize",
        insert_text="resize",
        kind=CompletionKind.METHOD,
        signature="(self, w, h)",
    )
    assert _inline_help_teaser(item) == ""
    assert _row_secondary_text(item) == "(self, w, h)"
