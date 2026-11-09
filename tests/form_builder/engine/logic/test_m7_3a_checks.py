"""Native-first check planning and the cbcsValidate JSON boundary."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.features.form_builder.engine.codegen.api import generate_form_module
from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.logic.checks import (
    Length,
    Pattern,
    Preset,
    Range,
    Required,
    RuntimeCheck,
    Bound,
    mask_of,
    plan,
    read_checks,
    write_checks,
)
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.ui4.reader import read_ui
from app.features.form_builder.engine.ui4.values import DateValue, DoubleValue, NumberValue, StringValue

pytestmark = pytest.mark.unit


def _predicates(class_name: str, checks: tuple, kind: str = "") -> list:
    field = plan(class_name, checks, kind)
    return [arm.predicate for arm in field.runtime if isinstance(arm, RuntimeCheck)]


def test_native_first_table() -> None:
    length_max = plan("QLineEdit", (Length(None, 8, None),))
    assert [(item.prop, item.value) for item in length_max.native] == [("maxLength", NumberValue(8))]
    assert length_max.runtime == ()
    assert length_max.validator is False

    both = plan("QLineEdit", (Length(2, 8, None),))
    assert [(item.prop, item.value) for item in both.native] == [("maxLength", NumberValue(8))]
    assert len(both.runtime) == 1
    assert isinstance(both.runtime[0], RuntimeCheck)
    assert "len(str(value)) < 2" in both.runtime[0].predicate
    assert "> 8" not in both.runtime[0].predicate
    assert "value is not None" in both.runtime[0].predicate

    spin = plan("QSpinBox", (Range(Bound(number=1), Bound(number=9), None),))
    assert [(item.prop, item.value) for item in spin.native] == [
        ("minimum", NumberValue(1)),
        ("maximum", NumberValue(9)),
    ]
    assert spin.runtime == ()

    double = plan("QDoubleSpinBox", (Range(Bound(number=1.5), Bound(number=2.5), None),))
    assert [(item.prop, item.value) for item in double.native] == [
        ("minimum", DoubleValue(1.5)),
        ("maximum", DoubleValue(2.5)),
    ]
    assert double.runtime == ()

    formula_bound = plan("QSpinBox", (Range(Bound(formula="1 + 1"), None, None),))
    assert formula_bound.native == ()

    assert plan("QSpinBox", (Required(None),)).native == ()
    assert plan("QSpinBox", (Required(None),)).runtime == ()
    assert plan("QDoubleSpinBox", (Required("Need it"),)).runtime == ()

    dated = plan(
        "QDateEdit",
        (Range(Bound(formula="2026-10-31"), Bound(formula="2026-12-01"), None),),
    )
    assert [(item.prop, item.value) for item in dated.native] == [
        ("minimumDate", DateValue(2026, 10, 31)),
        ("maximumDate", DateValue(2026, 12, 1)),
    ]
    assert dated.runtime == ()
    assert plan("QDateEdit", (Range(Bound(formula="2026-02-31"), None, None),)).native == ()
    assert plan("QDateEdit", (Range(Bound(formula="dueEdit + 1"), None, None),)).native == ()

    shaped = plan("QLineEdit", (Pattern(r"^[A-Z]{3}-\d{3}$", None),))
    assert mask_of(r"^[A-Z]{3}-\d{3}$") == ">AAA-999"
    assert [(item.prop, item.value) for item in shaped.native] == [
        ("inputMask", StringValue(">AAA-999")),
    ]
    assert shaped.validator is False
    assert any(
        "_cbcs_matches" in text and repr(r"^[A-Z]{3}-\d{3}$") in text
        for text in _predicates("QLineEdit", (Pattern(r"^[A-Z]{3}-\d{3}$", None),))
    )

    open_ended = plan("QLineEdit", (Pattern(r"^[A-Z]{3}-\d+$", None),))
    assert mask_of(r"^[A-Z]{3}-\d+$") is None
    assert open_ended.native == ()
    assert open_ended.validator is False
    assert any("_cbcs_matches" in text for text in _predicates("QLineEdit", (Pattern(r"^[A-Z]{3}-\d+$", None),)))

    money = plan("QLineEdit", (), "money")
    assert money.validator is True
    assert money.native == ()
    assert any("Enter a number" in arm.message for arm in money.runtime if isinstance(arm, RuntimeCheck))


def test_required_and_email_round_trip_keeps_an_unknown_key() -> None:
    raw = '[{"check": "required", "message": "Need it", "a_note": "keep"}, {"check": "email"}]'
    read = read_checks(raw)
    assert read.error is None
    assert isinstance(read.checks[0], Required)
    assert read.checks[0].message == "Need it"
    assert read.checks[0].extra == (("a_note", "keep"),)
    assert isinstance(read.checks[1], Preset)
    assert read.checks[1].name == "email"
    written = write_checks(read.checks)
    assert written is not None
    assert written.index('"check"') < written.index('"message"') < written.index('"a_note"')
    again = read_checks(written)
    assert again.error is None
    again_first = again.checks[0]
    assert isinstance(again_first, Required)
    assert again_first.extra == (("a_note", "keep"),)
    assert isinstance(again.checks[1], Preset) and again.checks[1].name == "email"
    assert write_checks(()) is None


def test_a_pattern_stays_a_fullmatch_and_not_a_validator(tmp_path: Path) -> None:
    payload = write_checks((Pattern(r"^[A-Z]{3}-\d{3}$", None),))
    assert payload is not None
    text = (
        '<?xml version="1.0" encoding="UTF-8"?>\n<ui version="4.0">\n <class>Code</class>\n'
        ' <widget class="QDialog" name="Code">\n'
        '  <layout class="QVBoxLayout" name="verticalLayout">\n'
        '   <item>\n    <widget class="QLineEdit" name="codeEdit">\n'
        '     <property name="cbcsValidate" stdset="0">\n      <string>%s</string>\n     </property>\n'
        "    </widget>\n   </item>\n  </layout>\n </widget>\n <resources/>\n <connections/>\n</ui>\n"
        % payload
    )
    path = tmp_path / "code.ui"
    path.write_text(text, encoding="utf-8")
    document = read_ui(text, allocator=IdAllocator()).document
    scope = FormScope(
        kind="project",
        ui_path=str(path),
        project_root=str(tmp_path),
        generated_path=str(tmp_path / "ui_code.py"),
        window_path=str(tmp_path / "code_window.py"),
        module_name="ui_code",
    )
    result = generate_form_module(document, scope=scope, source_bytes=text.encode("utf-8"))
    assert result.text is not None, [(item.code, item.message) for item in result.diagnostics]
    ast.parse(result.text, feature_version=(3, 9))
    assert "_cbcs_matches" in result.text
    assert "QRegularExpressionValidator" not in result.text
    assert "QRegularExpression" not in result.text
    assert "inputMask" not in result.text
    assert "setMaxLength" not in result.text
