"""Completion popup widgets and behavior shared by the editor and Python Console."""

from __future__ import annotations

from app.editors.completion_popup.completion_controller import CompletionController, CompletionHost
from app.editors.completion_popup.completion_docs_panel import CompletionDocsPanel
from app.editors.completion_popup.completion_item_delegate import CompletionItemDelegate
from app.editors.completion_popup.completion_item_model import CompletionItemModel, ItemRole
from app.editors.completion_popup.completion_kind_style import (
    KindGlyphStyle,
    kind_style_for,
    kind_styles_for_tokens,
)
from app.editors.completion_popup.completion_list_view import CompletionListView
from app.editors.completion_popup.completion_popup_container import CompletionPopupContainer
from app.editors.completion_popup.completion_replacement import (
    identifier_span_before,
    resolve_insert_replacement_range,
)

__all__ = [
    "CompletionController",
    "CompletionDocsPanel",
    "CompletionHost",
    "CompletionItemDelegate",
    "CompletionItemModel",
    "CompletionListView",
    "CompletionPopupContainer",
    "ItemRole",
    "KindGlyphStyle",
    "identifier_span_before",
    "kind_style_for",
    "kind_styles_for_tokens",
    "resolve_insert_replacement_range",
]
