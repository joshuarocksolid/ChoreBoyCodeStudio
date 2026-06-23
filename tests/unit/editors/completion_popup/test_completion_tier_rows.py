"""Wave 0 scaffold: tier row metadata and prefix-lengthen survival contract.

The parametrized reuse test documents EDIT-R-03 / CC-EDIT-05 behavior expected
after Wave 3 fixes ``CompletionController.reuse_items_for_prefix`` to preserve
tier section headers while the user refines the typed prefix.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.editors.completion_popup.completion_controller import CompletionController  # noqa: E402
from app.editors.completion_popup.completion_item_model import (  # noqa: E402
    CompletionItemModel,
    RowKindRole,
    row_kind_for_item,
)
from app.core.completion_tier import TIER_HEADER_SIDE_EFFECT, is_tier_header_item  # noqa: E402
from app.intelligence.completion_merge_policy import merge_completion_display  # noqa: E402
from app.intelligence.completion_models import (  # noqa: E402
    CompletionEnvelope,
    CompletionItem,
    CompletionKind,
)

pytestmark = pytest.mark.unit


def _item(label: str, *, source: str = "semantic", confidence: str = "exact") -> CompletionItem:
    return CompletionItem(
        label=label,
        insert_text=label,
        kind=CompletionKind.SYMBOL,
        source=source,
        confidence=confidence,
    )


def _tiered_completion_items() -> list[CompletionItem]:
    fast = CompletionEnvelope(
        items=[_item("alpha", source="static_api_index", confidence="approximate")],
        source_phase="fast",
        confidence="approximate",
    )
    semantic = CompletionEnvelope(
        items=[_item("alpha"), _item("alpaca")],
        source_phase="semantic",
        confidence="exact",
    )
    return merge_completion_display(fast=fast, semantic=semantic).items


@pytest.mark.parametrize(
    "row_index,expected_kind",
    [
        (0, "header"),
        (1, "item"),
        (2, "header"),
        (3, "item"),
    ],
)
def test_row_kind_role_marks_tier_headers_and_items(row_index: int, expected_kind: str) -> None:
    model = CompletionItemModel()
    items = _tiered_completion_items()
    model.set_items(items, prefix="")

    assert model.index(row_index, 0).data(RowKindRole) == expected_kind
    assert model.row_kind_at(row_index) == expected_kind
    assert row_kind_for_item(items[row_index]) == expected_kind
    assert is_tier_header_item(items[row_index]) == (expected_kind == "header")


@pytest.mark.parametrize(
    "initial_prefix,lengthened_prefix",
    [
        ("", "a"),
        ("a", "al"),
        ("al", "alp"),
    ],
)
def test_tier_headers_survive_prefix_lengthen(
    qapp,
    initial_prefix: str,
    lengthened_prefix: str,
) -> None:
    controller = CompletionController()
    items = _tiered_completion_items()
    controller.set_items(items, initial_prefix)

    assert controller.reuse_items_for_prefix(lengthened_prefix) is True

    row_kinds = controller.model().row_kinds()
    assert row_kinds.count("header") >= 2
    assert row_kinds[0] == "header"
    assert "item" in row_kinds


def _tier_header(label: str) -> CompletionItem:
    return CompletionItem(
        label=label,
        insert_text="",
        kind=CompletionKind.TEXT,
        source="tier_header",
        confidence="unsupported",
        side_effect_risk=TIER_HEADER_SIDE_EFFECT,
    )


def test_accept_current_on_trailing_header_hides_popup_when_no_selectable_below(qapp) -> None:
    controller = CompletionController()
    items = [_item("alpha"), _tier_header("Semantic")]
    controller.set_items(items, prefix="")
    list_view = controller.popup().list_view()
    list_view.setCurrentIndex(controller.model().index(1, 0))
    assert is_tier_header_item(controller.current_item())

    controller.accept_current()

    assert controller.is_visible() is False
