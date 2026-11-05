"""Blank and/or must skip the right side. LOGIC section 4.2 is Python's and/or."""

from __future__ import annotations

from typing import Any, List

import pytest

from app.features.form_builder.engine.diagnostics import CODES, Severity
from app.features.form_builder.engine.logic.formula import analyze, compile_formula, evaluate
from app.features.form_builder.engine.logic.formula.env import DataFacts, FormulaEnv, SlotKind
from app.features.form_builder.engine.logic.formula.runtime import helper_sources
from app.features.form_builder.engine.logic.formula.types import YESNO
from app.features.form_builder.engine.project.window_facts import MethodFacts


class _SawBlank(Exception):
    pass


class _Window:
    def __init__(self, ok_result: bool = True, raise_on_blank: bool = True) -> None:
        self.ok_calls: List[object] = []
        self.late_calls = 0
        self.ok_result = ok_result
        self.raise_on_blank = raise_on_blank

    def ok(self, value: object) -> bool:
        self.ok_calls.append(value)
        if self.raise_on_blank and (value is None or (isinstance(value, str) and value.strip() == "")):
            raise _SawBlank(value)
        return self.ok_result

    def late(self) -> bool:
        self.late_calls += 1
        return True


class _Form:
    def __init__(self, value: object, ok_result: bool = True, raise_on_blank: bool = True) -> None:
        self._cbcs_record = {"x": value}
        self._form = _Window(ok_result, raise_on_blank)


def _env() -> FormulaEnv:
    return FormulaEnv.for_test(
        {},
        {
            "ok": MethodFacts("ok", 1, 2, params=("value",), required=1),
            "late": MethodFacts("late", 1, 2),
        },
        data=DataFacts(record={"x": YESNO, "y": YESNO}, record_known=True),
        returns={"ok": "bool", "late": "bool"},
    )


def _run(text: str, form: _Form) -> object:
    env = _env()
    analysis = analyze(text, env, SlotKind.condition())
    errors = [
        (item.code, item.message)
        for item in analysis.problems
        if CODES[item.code].severity == Severity.ERROR
    ]
    assert errors == []
    emitted = compile_formula(analysis, env)
    namespace = {"__builtins__": __builtins__}  # type: dict
    exec(helper_sources(emitted.helpers), namespace)  # noqa: S102
    exec("def run(self):\n    return %s\n" % emitted.source, namespace)  # noqa: S102
    return namespace["run"](form)


@pytest.mark.unit
@pytest.mark.parametrize("blank", [None, "", "   "])
def test_blank_record_does_not_call_ok(blank: object) -> None:
    form = _Form(blank)
    assert _run("record.x and window.ok(record.x)", form) is False
    assert form._form.ok_calls == []


@pytest.mark.unit
def test_truthy_record_calls_ok() -> None:
    form = _Form(True)
    assert _run("record.x and window.ok(record.x)", form) is True
    assert form._form.ok_calls == [True]


@pytest.mark.unit
def test_third_and_operand_waits_for_the_earlier_ones() -> None:
    blank = _Form(None)
    assert _run("record.x and window.ok(record.x) and window.late()", blank) is False
    assert blank._form.ok_calls == []
    assert blank._form.late_calls == 0

    stopped = _Form(True, ok_result=False)
    assert _run("record.x and window.ok(record.x) and window.late()", stopped) is False
    assert stopped._form.ok_calls == [True]
    assert stopped._form.late_calls == 0

    reached = _Form(True)
    assert _run("record.x and window.ok(record.x) and window.late()", reached) is True
    assert reached._form.late_calls == 1


@pytest.mark.unit
def test_truthy_or_does_not_call_ok() -> None:
    form = _Form(True)
    assert _run("record.x or window.ok(record.x)", form) is True
    assert form._form.ok_calls == []


@pytest.mark.unit
def test_blank_or_does_call_ok() -> None:
    form = _Form(None, raise_on_blank=False)
    assert _run("record.x or window.ok(record.x)", form) is True
    assert form._form.ok_calls == [None]


@pytest.mark.unit
def test_design_time_eval_short_circuits_a_blank_record() -> None:
    env = _env()
    analysis = analyze("record.x and record.y", env, SlotKind.condition())
    emitted = compile_formula(analysis, env)
    reader = type("Reader", (), {})()
    reader._cbcs_record = {"x": None, "y": True}  # type: ignore[attr-defined]
    assert evaluate(emitted, reader, {}) is False
    reader._cbcs_record = {"x": True, "y": True}  # type: ignore[attr-defined]
    assert evaluate(emitted, reader, {}) is True
