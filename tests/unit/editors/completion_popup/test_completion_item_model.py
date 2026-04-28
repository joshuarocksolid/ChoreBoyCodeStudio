"""Unit tests for the completion item model and its match-range helper."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtGui import QPalette  # noqa: E402

from app.editors.completion_popup.completion_item_model import (  # noqa: E402
    CompletionItemModel,
    ItemRole,
    KindStyleRole,
    MatchRangesRole,
    compute_match_ranges,
)
from app.intelligence.completion_models import CompletionItem, CompletionKind  # noqa: E402
from app.shell.theme_tokens import tokens_from_palette  # noqa: E402

pytestmark = pytest.mark.unit


def _item(label: str, kind: CompletionKind = CompletionKind.SYMBOL) -> CompletionItem:
    return CompletionItem(label=label, insert_text=label, kind=kind)


@pytest.mark.parametrize(
    "label,prefix,expected",
    [
        ("alpha_local", "", []),
        ("", "alp", []),
        ("alpha_local", "alp", [(0, 3)]),
        ("alpha_local", "ALP", [(0, 3)]),
        ("AlphaLocal", "alp", [(0, 3)]),
        ("alpha_local", "alpha_local", [(0, 11)]),
        ("alpha_local", "lcl", [(1, 1), (8, 1), (10, 1)]),
        ("alpha_local", "xyz", []),
        ("aaa", "aa", [(0, 2)]),
        ("foo_bar_baz", "fbb", [(0, 1), (4, 1), (8, 1)]),
        ("foo_bar", "fooo", []),
    ],
)
def test_compute_match_ranges(label: str, prefix: str, expected: list[tuple[int, int]]) -> None:
    assert compute_match_ranges(label, prefix) == expected


def test_compute_match_ranges_collapses_adjacent_chars() -> None:
    # When the subsequence path matches consecutive characters, the returned
    # ranges should merge so the painter draws a single bold run instead of
    # multiple 1-character runs back-to-back.
    assert compute_match_ranges("abcdef", "abc") == [(0, 3)]
    assert compute_match_ranges("xabcy", "abc") == [(1, 3)]


def test_set_items_populates_rows_and_roles() -> None:
    model = CompletionItemModel()
    item = _item("alpha_local", CompletionKind.FUNCTION)
    model.set_items([item], prefix="alp")

    assert model.rowCount() == 1
    index = model.index(0, 0)
    assert index.data(ItemRole) is item
    assert index.data(MatchRangesRole) == [(0, 3)]
    assert model.prefix() == "alp"


def test_set_items_clears_previous_state() -> None:
    model = CompletionItemModel()
    model.set_items([_item("first")], prefix="f")
    model.set_items([], prefix="")
    assert model.rowCount() == 0


def test_clear_resets_rows() -> None:
    model = CompletionItemModel()
    model.set_items([_item("alpha"), _item("beta")], prefix="")
    assert model.rowCount() == 2
    model.clear()
    assert model.rowCount() == 0


def test_kind_style_role_returns_none_without_tokens() -> None:
    model = CompletionItemModel()
    model.set_items([_item("alpha")], prefix="")
    assert model.index(0, 0).data(KindStyleRole) is None


def test_kind_style_role_resolves_after_theme_applied() -> None:
    model = CompletionItemModel()
    model.set_items([_item("alpha", CompletionKind.CLASS)], prefix="")
    tokens = tokens_from_palette(QPalette(), force_mode="dark")
    model.set_theme_tokens(tokens)
    style = model.index(0, 0).data(KindStyleRole)
    assert style is not None
    assert style.label == "class"
    assert style.glyph
    assert style.accent_color
