"""Go to widget: typing narrows by object name and by friendly class words."""

from __future__ import annotations

from app.features.form_builder.integration.go_to_widget import filter_entries

_ENTRIES = [
    ("customer", "", "Widget"),
    ("nameEdit", "", "Line edit"),
    ("okButton", "OK", "Push button"),
    ("cancelButton", "Dismiss", "Push button"),
    ("notes", "", "Text edit"),
]


def test_empty_query_lists_everything_in_form_order() -> None:
    assert [row[0] for row in filter_entries(_ENTRIES, "")] == [row[0] for row in _ENTRIES]


def test_a_class_word_finds_every_widget_of_that_kind() -> None:
    assert [row[0] for row in filter_entries(_ENTRIES, "push button")] == ["okButton", "cancelButton"]


def test_a_name_match_ranks_before_a_class_only_match() -> None:
    names = [row[0] for row in filter_entries(_ENTRIES, "edit")]
    assert names == ["nameEdit", "notes"]
    assert [row[0] for row in filter_entries(_ENTRIES, "no")] == ["notes"]


def test_nothing_matches_gives_an_empty_list() -> None:
    assert filter_entries(_ENTRIES, "zzz") == []


def test_visible_text_matches_after_names_and_before_class_only() -> None:
    entries = [("a", "", "Dismiss kind"), ("b", "Dismiss me", "Label")]
    assert [row[0] for row in filter_entries(entries, "dismiss")] == ["b", "a"]
    assert [row[0] for row in filter_entries(_ENTRIES, "dismiss")] == ["cancelButton"]
