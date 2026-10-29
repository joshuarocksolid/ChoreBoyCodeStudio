"""Go to widget: typing narrows by object name and by friendly class words."""

from __future__ import annotations

from app.features.form_builder.integration.go_to_widget import filter_entries

_ENTRIES = [
    ("customer", "Widget"),
    ("nameEdit", "Line edit"),
    ("okButton", "Push button"),
    ("cancelButton", "Push button"),
    ("notes", "Text edit"),
]


def test_empty_query_lists_everything_in_form_order() -> None:
    assert [name for name, _ in filter_entries(_ENTRIES, "")] == [name for name, _ in _ENTRIES]


def test_a_class_word_finds_every_widget_of_that_kind() -> None:
    assert [name for name, _ in filter_entries(_ENTRIES, "push button")] == ["okButton", "cancelButton"]


def test_a_name_match_ranks_before_a_class_only_match() -> None:
    names = [name for name, _ in filter_entries(_ENTRIES, "edit")]
    assert names == ["nameEdit", "notes"]
    assert [name for name, _ in filter_entries(_ENTRIES, "no")] == ["notes"]


def test_nothing_matches_gives_an_empty_list() -> None:
    assert filter_entries(_ENTRIES, "zzz") == []
