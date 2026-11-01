"""The builder status line and Read as text use one speaker."""

from __future__ import annotations

import pytest

from app.features.form_builder.engine.logic.formula.speak import speak_text
from app.features.form_builder.qtside.formula.builder.model import load_formula
from app.features.form_builder.qtside.formula.builder.words import speak
from tests.form_builder.qtside.test_m7_5_roundtrip import _CONDITIONS, _OUTSIDE, _VALUES, _env

pytestmark = [pytest.mark.unit]


@pytest.mark.parametrize("formula", _CONDITIONS)
def test_a_builder_condition_speaks_once(formula: str) -> None:
    env = _env()
    model = load_formula(formula, env, "condition")
    assert model is not None
    heard = speak(model, env)
    assert heard == speak_text(formula, env, "condition")
    assert heard
    assert "`" not in heard


@pytest.mark.parametrize("formula", _VALUES)
def test_a_builder_value_speaks_once(formula: str) -> None:
    env = _env()
    model = load_formula(formula, env, "value")
    assert model is not None
    heard = speak(model, env)
    assert heard == speak_text(formula, env, "value")
    assert heard
    assert "`" not in heard


def test_a_number_comparison_uses_the_builder_symbol() -> None:
    env = _env()
    assert speak_text("qtySpin > 2", env, "condition") == "Qty > 2"


@pytest.mark.parametrize("kind, formula", _OUTSIDE)
def test_a_formula_the_builder_refuses_is_not_spoken(kind: str, formula: str) -> None:
    assert speak_text(formula, _env(), kind) == ""
