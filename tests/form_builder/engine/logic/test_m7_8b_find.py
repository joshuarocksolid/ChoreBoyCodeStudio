"""Forms logic search reads .ui files. It does not build widgets."""

from __future__ import annotations

import json
from pathlib import Path

from app.editors.search_service import SearchOptions
from app.features.form_builder.engine.logic.checks import Required, write_checks
from app.features.form_builder.engine.logic.events_codec import call_step, write_list
from app.features.form_builder.integration.find_ext.forms_logic import FormsLogic


def _prop(name: str, text: str) -> str:
    return '<property name="%s"><string>%s</string></property>' % (name, text)


def _form(class_name: str, body: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<ui version="4.0"><class>%s</class>'
        '<widget class="QDialog" name="%s">%s</widget></ui>'
    ) % (class_name, class_name, body)


def test_search_finds_a_rule_a_check_and_a_step_across_two_forms(tmp_path: Path) -> None:
    checks = write_checks((Required("Enter a name"),))
    assert checks is not None
    steps = write_list((call_step("ship_order"),))
    alpha = _form(
        "Alpha",
        '<widget class="QLineEdit" name="rateEdit">%s</widget>'
        '<widget class="QLabel" name="customerLabel">'
        '<property name="text"><string>Customer</string></property>'
        '<property name="buddy"><cstring>emailEdit</cstring></property>'
        "</widget>"
        '<widget class="QLineEdit" name="emailEdit">%s</widget>'
        % (_prop("cbcsValue", "seasonRate"), _prop("cbcsValidate", checks)),
    )
    beta = _form(
        "Beta",
        '<widget class="QPushButton" name="shipButton">'
        '<property name="text"><string>Ship</string></property>'
        "%s</widget>" % _prop("cbcsOnClicked", steps),
    )
    (tmp_path / "alpha.ui").write_text(alpha, encoding="utf-8")
    (tmp_path / "beta.ui").write_text(beta, encoding="utf-8")
    hook = FormsLogic()
    options = SearchOptions()

    rules = hook.rows(str(tmp_path), "seasonRate", options)
    assert len(rules) == 1
    assert rules[0].title.startswith("alpha.ui · ")
    assert "Value" in rules[0].title
    assert rules[0].excerpt == "seasonRate"
    assert "Use" not in rules[0].token
    assert json.loads(rules[0].token)["kind"] == "rule"

    checks_found = hook.rows(str(tmp_path), "Customer", options)
    assert any(row.title.startswith("alpha.ui · Customer · Required") for row in checks_found)

    steps_found = hook.rows(str(tmp_path), "ship_order", options)
    assert len(steps_found) == 1
    assert steps_found[0].title.startswith("beta.ui · ")
    assert "ship_order" in steps_found[0].title
    assert json.loads(steps_found[0].token)["kind"] == "step"

    assert hook.rows(str(tmp_path), "season", SearchOptions(whole_word=True)) == ()
    assert hook.rows(str(tmp_path), "seasonRate", SearchOptions(whole_word=True))
