"""M6.0b: FB401 to FB403 from the stored logic, and read-only logic in the session."""

from __future__ import annotations

import pytest

from app.features.form_builder.engine.diagnostic_codes import discover
from app.features.form_builder.engine.diagnostic_codes.fb4xx_logic import event_words, logic_diagnostics
from app.features.form_builder.engine.diagnostics import CODES, Severity
from tests.support.form_builder.m6_logic_fixtures import CHECKS, CLEAR_STEPS, prop_xml, form
from tests.form_builder.engine.commands._support import open_log
from tests.form_builder.qtside.support import open_session


def _codes(text: str):
    return [(item.code, item.location.object_name, item.location.property) for item in logic_diagnostics(open_log(text).document)]


def test_the_logic_codes_are_declared_with_the_agreed_severities() -> None:
    discover()
    assert CODES["FB401"].severity is Severity.ERROR
    assert CODES["FB402"].severity is Severity.WARNING
    assert CODES["FB403"].severity is Severity.ERROR
    assert CODES["FB405"].severity is Severity.ERROR
    assert not any(CODES[code].blocks_visual_open for code in ("FB401", "FB402", "FB403", "FB405"))


def test_a_clean_form_has_no_logic_diagnostics() -> None:
    assert _codes(form()) == []
    assert _codes(form(marker="")) == []
    assert _codes(form(marker='{"version":1}').replace(prop_xml("cbcsOnClicked", CLEAR_STEPS), "")) == []


def test_unreadable_lists_and_unknown_verbs_are_reported_on_their_property() -> None:
    broken = form().replace(prop_xml("cbcsOnClicked", CLEAR_STEPS), prop_xml("cbcsOnClicked", '[{"do": "slot"}]'))
    assert _codes(broken) == [("FB401", "clearButton", "cbcsOnClicked")]
    items = logic_diagnostics(open_log(broken).document)
    assert items[0].message == "cbcsOnClicked on clearButton can't be read (line 1). It is kept as it is and does nothing."
    bad_checks = form().replace(prop_xml("cbcsValidate", CHECKS), prop_xml("cbcsValidate", '{"check": "required"}'))
    assert _codes(bad_checks) == [("FB401", "nameEdit", "cbcsValidate")]
    future = form().replace(prop_xml("cbcsOnClicked", CLEAR_STEPS), prop_xml("cbcsOnClicked", '[{"do": "hyperjump"}]'))
    found = logic_diagnostics(open_log(future).document)
    assert [(item.code, item.location.property) for item in found] == [("FB403", "cbcsOnClicked")]
    assert found[0].message == (
        "clearButton clicked has a step Code Studio can't edit (hyperjump). "
        "The event does nothing until it's edited in a newer version."
    )


def test_a_newer_or_unreadable_marker_is_one_warning_for_the_form() -> None:
    newer = logic_diagnostics(open_log(form(marker='{"version":5}')).document)
    assert [item.code for item in newer] == ["FB402"]
    assert "(version 5)" in newer[0].message and newer[0].severity is Severity.WARNING
    unreadable = logic_diagnostics(open_log(form(marker="soon")).document)
    assert [item.code for item in unreadable] == ["FB401", "FB402"]
    # newer logic is not interpreted: shapes and verbs this build doesn't know add no rows
    future = form(marker='{"version":5}').replace(
        prop_xml("cbcsOnClicked", CLEAR_STEPS), prop_xml("cbcsOnClicked", '{"v2": [{"do": "hyperjump"}]}')
    )
    assert [item.code for item in logic_diagnostics(open_log(future).document)] == ["FB402"]


def test_event_words() -> None:
    assert event_words("currentIndexChanged") == "current index changed"
    assert event_words("clicked") == "clicked"


def test_session_reports_read_only_logic_for_newer_and_unreadable_markers() -> None:
    assert open_session(form(), "/tmp/a.ui").logic_read_only() is False
    assert open_session(form(marker="2"), "/tmp/a.ui").logic_read_only() is True
    assert open_session(form(marker="{}"), "/tmp/a.ui").logic_read_only() is True


def test_a_number_marker_from_qt_designer_is_read() -> None:
    number = form(marker="").replace(
        "  <layout class=",
        '  <property name="cbcsLogic" stdset="0">\n   <number>3</number>\n  </property>\n  <layout class=',
        1,
    )
    assert open_session(number, "/tmp/a.ui").logic_read_only() is True
    assert [item.code for item in logic_diagnostics(open_log(number).document)] == ["FB402"]
    assert open_session(number.replace("<number>3", "<number>1"), "/tmp/a.ui").logic_read_only() is False


@pytest.mark.xfail(
    strict=True,
    reason="Owner of engine/session.py (wiring lane): FormSession.open publishes only 'reader' and 'connections'; "
    "logic_diagnostics (M6.0b) is not published yet, so FB401 to FB403 never reach Problems.",
)
def test_session_open_publishes_logic_diagnostics() -> None:
    session = open_session(form(marker="2"), "/tmp/a.ui")
    assert "FB402" in [item.code for item in session.diagnostics.all()]
