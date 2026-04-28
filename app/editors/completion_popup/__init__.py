"""Custom completion popup widgets shared by the editor and Python Console."""

from __future__ import annotations

from app.editors.completion_popup.completion_controller import CompletionController
from app.editors.completion_popup.completion_docs_panel import CompletionDocsPanel
from app.editors.completion_popup.completion_item_delegate import CompletionItemDelegate
from app.editors.completion_popup.completion_item_model import (
    CompletionItemModel,
    ItemRole,
    KindStyleRole,
    MatchRangesRole,
    compute_match_ranges,
)
from app.editors.completion_popup.completion_kind_style import (
    KindGlyphStyle,
    kind_style_for,
    kind_styles_for_tokens,
)
from app.editors.completion_popup.completion_list_view import CompletionListView
from app.editors.completion_popup.completion_popup_container import CompletionPopupContainer

__all__ = [
    "CompletionController",
    "CompletionDocsPanel",
    "CompletionItemDelegate",
    "CompletionItemModel",
    "CompletionListView",
    "CompletionPopupContainer",
    "ItemRole",
    "KindGlyphStyle",
    "KindStyleRole",
    "MatchRangesRole",
    "compute_match_ranges",
    "kind_style_for",
    "kind_styles_for_tokens",
]
