# pyright: reportAttributeAccessIssue=false
"""UX-CAT-007 search: the lead result for each table row, ranking and the quick list."""

from __future__ import annotations

import pytest

from app.features.form_builder.qtside.insert.catalog import load_catalog
from app.features.form_builder.qtside.insert.rows import browse_rows, quick_rows, search_rows
from app.features.form_builder.qtside.insert.catalog.search import search

_TABLE = (
    ("textbox", "Line edit"),
    ("text box", "Line edit"),
    ("textfield", "Line edit"),
    ("input", "Line edit"),
    ("entry", "Line edit"),
    ("field", "Line edit"),
    ("textarea", "Plain text edit"),
    ("memo", "Plain text edit"),
    ("multiline", "Plain text edit"),
    ("notes", "Plain text edit"),
    ("paragraph", "Plain text edit"),
    ("dropdown", "Combo box"),
    ("drop down", "Combo box"),
    ("select", "Combo box"),
    ("picklist", "Combo box"),
    ("choice", "Combo box"),
    ("combo", "Combo box"),
    ("checkbox", "Check box"),
    ("tick", "Check box"),
    ("tickbox", "Check box"),
    ("toggle", "Check box"),
    ("yes no", "Check box"),
    ("radio", "Radio button"),
    ("option", "Radio button"),
    ("button", "Push button"),
    ("btn", "Push button"),
    ("command", "Push button"),
    ("ok cancel", "Button box"),
    ("dialog buttons", "Button box"),
    ("buttons", "Button box"),
    ("number", "Spin box"),
    ("integer", "Spin box"),
    ("whole number", "Spin box"),
    ("counter", "Spin box"),
    ("numeric", "Spin box"),
    ("decimal", "Double spin box"),
    ("float", "Double spin box"),
    ("money", "Double spin box"),
    ("currency", "Double spin box"),
    ("price", "Double spin box"),
    ("amount", "Double spin box"),
    ("date", "Date edit"),
    ("datepicker", "Date edit"),
    ("day", "Date edit"),
    ("time", "Time edit"),
    ("clock", "Time edit"),
    ("datetime", "Date and time edit"),
    ("timestamp", "Date and time edit"),
    ("calendar", "Calendar"),
    ("month", "Calendar"),
    ("slider", "Horizontal slider"),
    ("range", "Horizontal slider"),
    ("track bar", "Horizontal slider"),
    ("knob", "Dial"),
    ("progress", "Progress bar"),
    ("loading", "Progress bar"),
    ("percent", "Progress bar"),
    ("table", "Table widget"),
    ("spreadsheet", "Table widget"),
    ("cells", "Table widget"),
    ("grid", "Grid layout"),
    ("list", "List widget"),
    ("listbox", "List widget"),
    ("tree", "Tree widget"),
    ("hierarchy", "Tree widget"),
    ("folders", "Tree widget"),
    ("tabs", "Tab widget"),
    ("notebook", "Tab widget"),
    ("pages", "Tab widget"),
    ("wizard", "Wizard"),
    ("steps", "Wizard"),
    ("assistant", "Wizard"),
    ("panel", "Group box"),
    ("group", "Group box"),
    ("fieldset", "Group box"),
    ("container", "Group box"),
    ("box", "Group box"),
    ("scroll", "Scroll area"),
    ("label", "Label"),
    ("caption", "Label"),
    ("static text", "Label"),
    ("title", "Label"),
    ("image", "Label"),
    ("picture", "Label"),
    ("photo", "Label"),
    ("logo", "Label"),
    ("icon", "Label"),
    ("separator", "Horizontal line"),
    ("divider", "Horizontal line"),
    ("rule", "Horizontal line"),
    ("line", "Horizontal line"),
    ("space", "Horizontal spacer"),
    ("gap", "Horizontal spacer"),
    ("stretch", "Horizontal spacer"),
    ("spring", "Horizontal spacer"),
    ("spacer", "Horizontal spacer"),
    ("shortcut", "Key sequence edit"),
    ("hotkey", "Key sequence edit"),
    ("html", "Text browser"),
    ("browser", "Text browser"),
    ("link", "Text browser"),
    ("help text", "Text browser"),
    ("lcd", "LCD number"),
    ("digits", "LCD number"),
    ("display", "LCD number"),
    ("font", "Font combo box"),
    ("split", "Horizontal splitter"),
    ("splitter", "Horizontal splitter"),
    ("resizable panes", "Horizontal splitter"),
    ("dock", "Dock widget"),
    ("side panel", "Dock widget"),
    ("mdi", "MDI area"),
    ("windows", "MDI area"),
    ("quantity", "Quantity spin box"),
    ("unit", "Quantity spin box"),
    ("length", "Quantity spin box"),
    # The five extra pairs listed in UX-CAT-007.
    ("lin", "Line edit"),
    ("QComboBox", "Combo box"),
    ("push", "Push button"),
    ("tab", "Tab widget"),
    ("date", "Date edit"),
)

def _lead(query: str) -> str:
    catalog = load_catalog()
    hits = search(catalog.entries, catalog.windows, query)
    return hits[0].entry.friendly if hits else ""


def _params():  # type: ignore[no-untyped-def]
    found = []
    seen = set()
    for query, expected in _TABLE:
        if (query, expected) in seen:
            continue
        seen.add((query, expected))
        found.append(pytest.param(query, expected, id="%s->%s" % (query, expected)))
    return found


@pytest.mark.parametrize(("query", "expected"), _params())
def test_the_lead_result_for_each_table_query(query: str, expected: str) -> None:
    assert _lead(query) == expected


@pytest.mark.parity("R3-133")
def test_the_filter_results_are_one_flat_list() -> None:
    """R3-133: the filter shows one flat result list, each match once, with the category or synonym beside it."""
    catalog = load_catalog()
    rows = search_rows(search(catalog.entries, catalog.windows, "dropdown"), "dropdown")
    names = [row.key for row in rows]
    assert len(names) == len(set(names))
    assert rows[0].title == "Combo box"
    assert rows[0].via == "dropdown"
    assert rows[0].search


def test_each_entry_appears_once() -> None:
    catalog = load_catalog()
    hits = search(catalog.entries, catalog.windows, "e")
    keys = [hit.entry.key for hit in hits]
    assert len(keys) == len(set(keys))


def test_an_empty_query_lists_everything_in_category_order() -> None:
    catalog = load_catalog()
    hits = search(catalog.entries, catalog.windows, "")
    assert [hit.entry.key for hit in hits] == [entry.key for entry in catalog.entries]


def test_a_leading_capital_q_and_spaces_are_ignored() -> None:
    assert _lead("Q Line Edit") == "Line edit"
    assert _lead("line-edit") == "Line edit"


def test_window_kinds_follow_the_widget_results() -> None:
    catalog = load_catalog()
    hits = search(catalog.entries, catalog.windows, "wizard")
    windows = [hit for hit in hits if hit.window]
    assert [hit.entry.friendly for hit in windows] == ["Wizard · new form"]
    assert hits.index(windows[0]) == len(hits) - 1


@pytest.mark.parity("R3-112")
def test_the_dialog_search_row_opens_a_dialog_form() -> None:
    catalog = load_catalog()
    rows = search_rows(search(catalog.entries, catalog.windows, "dialog"), "dialog")
    windows = [row for row in rows if row.window]
    assert [row.title for row in windows] == ["Dialog · new form"]
    assert windows[0].key == "window:dialog"


@pytest.mark.parity("R3-111")
def test_the_main_window_search_row_opens_a_main_window_form() -> None:
    catalog = load_catalog()
    rows = search_rows(search(catalog.entries, catalog.windows, "main window"), "main window")
    windows = [row for row in rows if row.window]
    assert windows and windows[0].key == "window:main"


def test_the_quick_list_starts_with_recent_entries() -> None:
    catalog = load_catalog()
    rows = quick_rows(catalog.entries, ["QComboBox", "QTabWidget"], "")
    assert rows[0].title == "Recently used"
    assert [row.key for row in rows[1:3]] == ["QComboBox", "QTabWidget"]


def test_the_quick_list_with_a_query_is_the_same_search_without_windows() -> None:
    catalog = load_catalog()
    rows = quick_rows(catalog.entries, [], "tabs")
    assert rows[0].key == "QTabWidget"
    assert not any(row.window for row in rows)


def test_browse_rows_fold_the_freecad_category_by_default() -> None:
    catalog = load_catalog()
    rows = browse_rows(catalog.entries, (), {})
    freecad = [row for row in rows if row.kind == "header" and row.category == "FreeCAD"]
    assert freecad and freecad[0].expanded is False
    assert not any(row.kind == "entry" and row.category == "FreeCAD" for row in rows)
    opened = browse_rows(catalog.entries, (), {"FreeCAD": True})
    assert any(row.kind == "entry" and row.category == "FreeCAD" for row in opened)
