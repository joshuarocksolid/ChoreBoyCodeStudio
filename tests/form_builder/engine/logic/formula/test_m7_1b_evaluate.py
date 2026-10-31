"""Design-time evaluation runs the compiled source."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QLineEdit, QSpinBox

from app.features.form_builder.engine.logic.formula import (
    EvalBlank,
    Emitted,
    analyze,
    compile_formula,
    evaluate,
)
from app.features.form_builder.engine.logic.formula.env import SlotKind
from app.features.form_builder.engine.project.window_facts import MethodFacts
from tests.form_builder.engine.logic.formula.test_m7_1b_compile import env_for


def _compile(text: str) -> object:
    env = env_for()
    analysis = analyze(text, env, SlotKind("expr"))
    return compile_formula(analysis, env)


@pytest.mark.unit
def test_evaluate_spin_times_money(qapp: object) -> None:
    del qapp
    qty = QSpinBox()
    qty.setValue(6)
    price = QLineEdit()
    price.setText("$2.00")
    emitted = _compile("qty * moneyEdit")
    reader = SimpleNamespace(qty=qty, moneyEdit=price)
    assert evaluate(emitted, reader, {}) == Decimal("12.00")


@pytest.mark.unit
def test_blank_money_line_is_none(qapp: object) -> None:
    del qapp
    price = QLineEdit()
    price.setText("")
    emitted = _compile("moneyEdit")
    assert evaluate(emitted, SimpleNamespace(moneyEdit=price), {}) is None


@pytest.mark.unit
def test_missing_window_value(qapp: object) -> None:
    del qapp
    env = env_for()
    env = type(env).for_test(
        env.widgets,
        dict(env.methods, tax=MethodFacts("tax", 1, 2)),
        returns=dict(env.returns, tax="int"),
        class_chain=env.class_chain,
    )
    analysis = analyze("window.tax()", env, SlotKind("expr"))
    emitted = compile_formula(analysis, env)
    reader = SimpleNamespace(_form="sentinel")
    missing = evaluate(emitted, reader, {})
    assert isinstance(missing, EvalBlank)
    assert missing.reason == "needs a window value"
    assert reader._form == "sentinel"
    assert evaluate(emitted, reader, {"tax": 7}) == 7


@pytest.mark.unit
def test_empty_builtins_block_bare_len(qapp: object) -> None:
    del qapp
    qty = QSpinBox()
    qty.setValue(3)
    emitted = Emitted(source="len(self.qty.value())", helpers=(), imports=())
    result = evaluate(emitted, SimpleNamespace(qty=qty), {})
    assert isinstance(result, EvalBlank)
    assert "len" in result.reason
