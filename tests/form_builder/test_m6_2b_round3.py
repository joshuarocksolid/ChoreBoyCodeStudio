# pyright: reportAttributeAccessIssue=false
"""Regressions from the M6.2b gate probes: memos, create-method, a failed save."""

from __future__ import annotations

import gc
from pathlib import Path

import pytest

from app.features.form_builder.engine.commands.catalog_ext.events import SetEventSteps
from app.features.form_builder.engine.commands.catalog_ext.form_fields import SetFormField
from app.features.form_builder.engine.commands.catalog_ext.methods import MethodUndoMark
from app.features.form_builder.engine.logic.events_codec import call_step
from app.features.form_builder.integration.handlers import MethodRequest
from app.features.form_builder.integration.handlers_code import SERVICE
from tests.form_builder.test_m6_2b_gesture import FIXTURE, _open, _request

pytestmark = [pytest.mark.unit]


def test_a_discarded_redo_does_not_toast_on_a_later_undo(tmp_path: Path) -> None:
    text = (FIXTURE / "sale_window.py").read_text(encoding="utf-8")
    surface, window, port = _open(tmp_path / "one", text)
    other, other_window, other_port = _open(tmp_path / "two", text)
    other_before = other_port.tabs[str(other_window)]
    hits = 0
    for index in range(40):
        assert SERVICE.make_method(surface, _request()).ok
        assert surface.session.log.undo()
        SERVICE.book.last_notice = ""
        surface.session.log.execute(SetFormField("comment", "c%d" % index, "Change comment"))
        gc.collect()
        before = port.tabs[str(window)]
        surface.session.log.undo()
        if SERVICE.book.last_notice or port.tabs[str(window)] != before:
            hits += 1
        SERVICE.book.last_notice = ""
    assert hits == 0
    assert other_port.tabs[str(other_window)] == other_before


def test_the_fourth_and_fifth_create_method_each_undo_in_one_step(tmp_path: Path) -> None:
    text = (FIXTURE / "sale_window.py").read_text(encoding="utf-8")
    surface, window, port = _open(tmp_path, text, dirty=True)
    names = ["m_a", "m_b", "m_c", "m_d", "m_e"]
    for name in names:
        so_far = tuple(call_step(item) for item in names[: names.index(name) + 1])
        surface.session.log.execute(SetEventSteps("printButton", "clicked", so_far, caption="Call"))
    befores = []
    for name in names:
        befores.append(port.tabs[str(window)])
        outcome = SERVICE.make_method(
            surface,
            MethodRequest("Create method", (MethodUndoMark(name),), name, "", "printButton", "clicked"),
        )
        assert outcome.ok, outcome.reason
        assert "def %s(self):" % name in port.tabs[str(window)]
    for before in reversed(befores):
        assert surface.session.log.undo()
        assert port.tabs[str(window)] == before


def test_a_parse_error_refusal_shows_its_sentence(tmp_path: Path) -> None:
    text = (FIXTURE / "sale_window.py").read_text(encoding="utf-8") + "\n("
    surface, _window, _port = _open(tmp_path, text, dirty=True)
    outcome = SERVICE.make_method(surface, _request())
    assert outcome.ok is False
    assert "Fix the error on line" in outcome.reason
    assert any("Fix the error on line" in line for line in surface.lines)


@pytest.mark.parametrize(
    "reason",
    ["the copy on disk changed", "the file can't be written"],
)
def test_a_failed_save_refuses_and_restores_a_clean_tab(tmp_path: Path, reason: str) -> None:
    text = (FIXTURE / "sale_window.py").read_text(encoding="utf-8")
    surface, window, port = _open(tmp_path, text)
    port.fail_reason = reason
    before = port.tabs[str(window)]
    steps = len(surface.session.log.entries())
    outcome = SERVICE.make_method(surface, _request())
    assert outcome.ok is False
    assert outcome.reason == "Code Studio couldn't change %s: %s" % (window.name, reason)
    assert port.tabs[str(window)] == before
    assert str(window) not in port.dirty
    assert len(surface.session.log.entries()) == steps
    assert any(reason in line for line in surface.lines)


def test_the_method_page_skips_dunder_methods() -> None:
    from app.features.form_builder.qtside.pickers.method_page import _fitting

    class _Info:
        def __init__(self, name: str) -> None:
            self.name = name
            self.params = ()

    class _Ctx:
        method_infos = (_Info("__init__"), _Info("print_receipt"))

    kept = _fitting(_Ctx(), 0)
    assert [item.name for item in kept] == ["print_receipt"]
