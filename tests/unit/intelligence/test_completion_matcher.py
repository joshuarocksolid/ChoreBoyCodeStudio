"""Ranking rules for the completion popup (owner-approved v0.4.13 design)."""

from __future__ import annotations

import pytest

from app.intelligence.completion_matcher import filter_and_rank, typed_full_name
from app.intelligence.runtime_members import RuntimeMember, RuntimeMemberListing
from app.intelligence.completion_models import CompletionKind

pytestmark = pytest.mark.unit

QT_LIKE = [
    "__class__",
    "_private_helper",
    "setParent",
    "setText",
    "setToolTip",
    "sizeHint",
    "stackUnder",
    "statusTip",
    "text",
    "toolTip",
]


def _ranked(names: list[str], query: str, **kwargs: object) -> list[str]:
    return [names[row.index] for row in filter_and_rank(names, query, **kwargs)]  # type: ignore[arg-type]


def test_camelcase_query_puts_settext_first() -> None:
    ranked = _ranked(QT_LIKE, "sT")

    assert ranked[0] == "setText"
    assert set(ranked) == {"setText", "setToolTip", "statusTip"}


def test_exact_case_prefix_beats_any_case_and_recent_beats_alphabetical() -> None:
    names = ["Setter", "setA", "setB"]

    assert _ranked(names, "set") == ["setA", "setB", "Setter"]
    assert _ranked(names, "set", recent={"setB": 3}) == ["setB", "setA", "Setter"]


def test_private_names_come_last_and_dunders_need_an_underscore() -> None:
    assert _ranked(["_hidden", "help"], "h")[-1] == "_hidden"
    assert "__class__" not in _ranked(QT_LIKE, "")
    assert "__class__" in _ranked(QT_LIKE, "_")


def test_fuzzy_is_only_a_fallback() -> None:
    assert _ranked(QT_LIKE, "stxt") == ["setText"]
    assert "setText" not in _ranked(QT_LIKE, "statu")


def test_narrowing_from_a_previous_result_matches_a_full_scan() -> None:
    matched: list[int] = []
    filter_and_rank(QT_LIKE, "set", matched_out=matched)

    narrowed = [QT_LIKE[row.index] for row in filter_and_rank(QT_LIKE, "setT", candidates=matched)]

    assert narrowed == _ranked(QT_LIKE, "setT")


def test_member_past_position_500_is_listed_and_filterable() -> None:
    members = [RuntimeMember(name="field{:03d}Value".format(i), kind=CompletionKind.ATTRIBUTE) for i in range(640)]
    members.append(RuntimeMember(name="zzzSortedLast", kind=CompletionKind.ATTRIBUTE))
    listing = RuntimeMemberListing.from_members("record", members)

    names = [item.label for item in listing.visible("")]

    assert len(names) == 641
    assert names.index("zzzSortedLast") > 500
    assert _ranked(names, "zzz") == ["zzzSortedLast"]


@pytest.mark.parametrize(
    ("query", "expected"),
    [("setText", True), ("text", True), ("setTex", False), ("tool", False), ("", False)],
)
def test_typed_full_name(query: str, expected: bool) -> None:
    assert typed_full_name(["setText", "text", "toolTip"], query) is expected
