# pyright: reportAttributeAccessIssue=false
"""M6.R round 2: the persona walkthrough regressions that do not need the shell."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.features.form_builder.engine.codegen.api import generate_form_module
from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.logic.intents.m6 import intents_for, target_candidates
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.ui4.defaults import QtClassTable
from app.features.form_builder.engine.ui4.reader import read_ui
from app.features.form_builder.qtside.inspector.behavior_ext._rows import project_form, project_incoming
from app.features.form_builder.qtside.pickers.flow import (
    Item,
    Page,
    PickContext,
    PickerSource,
    _code_rows,
    _drop_empty,
    _filter,
    _pair_page,
    _step_page,
)
from app.features.form_builder.qtside.pickers.method_page import _show_receive
from tests.form_builder.engine.commands._support import open_log

_FIX = Path(__file__).resolve().parents[1] / "fixtures" / "m6" / "forms"
_SALE = _FIX / "sale.ui"
_DESIGNER = _FIX / "designer_made.ui"


def _ctx(doc: Any, source: PickerSource, target: str = "", infos: tuple = ()) -> PickContext:
    names = tuple(str(getattr(item, "name", item)) for item in infos)
    return PickContext(
        doc, QtClassTable.shared(), source, target, names, "sale_window.py", "SaleWindow", False,
        method_infos=infos,
    )


def test_a_chosen_event_does_not_offer_another_events_step() -> None:
    doc = open_log(_SALE.read_text(encoding="utf-8")).document
    page = _step_page(_ctx(doc, PickerSource("nameEdit", "textChanged")), "textChanged", True, -1, "event")
    assert isinstance(page, Page)
    payloads = [row.payload for row in page.rows if not row.header]
    assert "next-field" not in payloads
    assert page.rows[0].payload != "next-field"


def test_a_drop_on_the_form_offers_a_new_method_and_hides_an_empty_header() -> None:
    doc = open_log(_DESIGNER.read_text(encoding="utf-8")).document
    ctx = _ctx(doc, PickerSource("applyButton", "clicked"), "DesignerMade")
    page = _pair_page(ctx, "clicked", -1, "", "apply", True)
    assert any(row.kind == "new-method" and "apply" in row.text for row in page.rows)
    headers = [row for row in page.rows if row.header]
    for index, header in enumerate(headers):
        nxt = page.rows[page.rows.index(header) + 1]
        assert not nxt.header


def test_nothing_matches_still_offers_a_new_method() -> None:
    rows = (Item("header", "", "EVERYTHING THE FORM CAN DO", header=True),)
    found = _filter(rows, "apply")
    assert found[0].text.startswith("Nothing matches")
    assert found[-1].kind == "new-method"
    assert found[-1].text == "Call a new method named apply\u2026"


def test_your_code_skips_dunder_wide_methods_and_other_events() -> None:
    class _Info:
        def __init__(self, name: str, params: tuple = ()) -> None:
            self.name = name
            self.params = params

    doc = open_log(_SALE.read_text(encoding="utf-8")).document
    infos = (
        _Info("__init__"),
        _Info("two_values", ("first", "second")),
        _Info("on_okButton_clicked"),
        _Info("print_receipt"),
    )
    rows = _code_rows(_ctx(doc, PickerSource("printButton", "clicked"), infos=infos), "clicked")
    names = [row.payload for row in rows if row.kind == "method"]
    assert names == ["print_receipt"]


def test_a_layout_connection_is_kept_and_not_emitted(tmp_path: Path) -> None:
    text = _DESIGNER.read_text(encoding="utf-8")
    read = read_ui(text, allocator=IdAllocator())
    scope = FormScope(
        kind="project",
        ui_path=str(tmp_path / "designer_made.ui"),
        project_root=str(tmp_path),
        generated_path=str(tmp_path / "ui_designer_made.py"),
        window_path=str(tmp_path / "designer_made_window.py"),
        module_name="ui_designer_made",
    )
    result = generate_form_module(read.document, scope=scope, source_bytes=text.encode("utf-8"))
    assert result.text is not None
    assert "invalidate" not in result.text
    words = [row.words for row in project_form(read.document, QtClassTable.shared())]
    assert any("kept" in line and "verticalLayout" in line for line in words)


def test_clear_a_field_does_not_offer_a_label() -> None:
    doc = open_log(_SALE.read_text(encoding="utf-8")).document
    intent = next(item for item in intents_for(doc, QtClassTable.shared(), "clearButton") if item.intent_id == "clear-field")
    names = target_candidates(doc, QtClassTable.shared(), intent, "clearButton")
    assert "nameLabel" not in names
    assert "nameEdit" in names


def test_from_other_widgets_on_the_form_skips_a_childs_method_call() -> None:
    doc = open_log(_DESIGNER.read_text(encoding="utf-8")).document
    rows = project_incoming(doc, QtClassTable.shared(), "DesignerMade")
    assert all("run_search" not in row.words for row in rows)


def test_a_push_button_that_is_not_checkable_does_not_receive_checked() -> None:
    sale = open_log(_SALE.read_text(encoding="utf-8")).document

    class _Source:
        sender = "printButton"

    class _Ctx:
        doc = sale
        source = _Source()

    assert _show_receive(_Ctx(), ("bool",), ("QPushButton",), "clicked") is False


def test_an_empty_section_header_is_dropped() -> None:
    rows = _drop_empty([Item("header", "", "EMPTY", header=True), Item("header", "", "USED", header=True), Item("slot", "close()", "Close")])
    assert [row.text for row in rows] == ["USED", "Close"]


def test_the_same_window_text_is_not_prescanned_twice(tmp_path: Path) -> None:
    from app.features.form_builder.engine.project import window_file as wf

    text = (_FIX / "sale_window.py").read_text(encoding="utf-8")
    calls = []
    real = wf._prescan

    def _count(body: str):
        calls.append(len(body))
        return real(body)

    wf._TEXT_CACHE.clear()
    wf._prescan = _count
    try:
        root = str(tmp_path)
        wf.read_window(root, "sale_window.py", text=text)
        wf.read_window(root, "sale_window.py", text=text, token="4")
        assert len(calls) == 1
        wf.read_window(root, "sale_window.py", text=text + "\n", token="4")
        assert len(calls) == 2
    finally:
        wf._prescan = real


def test_f12_at_column_1_of_a_def_opens_the_form() -> None:
    from app.features.form_builder.integration.keys_ext.code import return_to_form

    source = "class DesignerMadeWindow:\n    def on_okButton_clicked(self):\n        return\n"
    cursor = source.index("\n") + 1
    opened: list = []

    class _Workflow:
        def open_file_at_line(self, path: str, line: int) -> None:
            opened.append(Path(path).name)

    window = type("W", (), {"_editor_tab_workflow": _Workflow(), "_tab_content_registry": None})()
    path = str(_DESIGNER.with_name("designer_made_window.py"))
    assert return_to_form(window, path, source, "", cursor) is True
    assert opened == ["designer_made.ui"]
    opened.clear()
    body = source.index("return")
    assert return_to_form(window, path, source, "return", body) is True
    assert opened == ["designer_made.ui"]
