# pyright: reportAttributeAccessIssue=false
"""formula → builder → formula, for every shape the builder can show."""

from __future__ import annotations

from typing import Tuple

import pytest

from app.features.form_builder.engine.logic.formula.env import FormulaEnv, WidgetFacts
from app.features.form_builder.qtside.formula.builder.model import load_formula, write_formula

pytestmark = [pytest.mark.unit]

_CONDITIONS = (
    "discountCheck",
    "not discountCheck",
    "discountCheck and rushRadio",
    "discountCheck or rushRadio",
    'nameEdit == "Ada"',
    'nameEdit != "Ada"',
    "is_blank(nameEdit)",
    "not is_blank(nameEdit)",
    'contains(nameEdit, "a")',
    'starts_with(nameEdit, "A")',
    'nameEdit == "Ada" and nameEdit != "Bea"',
    'nameEdit == "Ada" or is_blank(nameEdit)',
    "qtySpin == 2",
    "qtySpin != 2",
    "qtySpin < 2",
    "qtySpin <= 2",
    "qtySpin > 2",
    "qtySpin >= 2",
    "1 <= qtySpin <= 10",
    "qtySpin > 2 and qtySpin < 9",
    "whenEdit < date(2024, 3, 1)",
    "whenEdit > date(2024, 3, 1)",
    "whenEdit == today()",
    "is_blank(whenEdit)",
    'statusCombo == "Open"',
    'statusCombo in ["Open", "Paid"]',
    "nameEdit == qtySpin",
)

_VALUES = (
    "qtySpin",
    "10",
    "qtySpin + priceSpin",
    "qtySpin - 1",
    "qtySpin * priceSpin",
    "qtySpin / 2",
    "qtySpin + priceSpin + taxSpin",
    "qtySpin * priceSpin + taxSpin",
    "qtySpin + priceSpin + taxSpin + feeSpin",
    "10 if discountCheck else 0",
    "qtySpin * priceSpin if discountCheck else 0",
    "10 if discountCheck and rushRadio else 1",
    "-2",
)

_OUTSIDE = (
    ("condition", "qtySpin * priceSpin"),
    ("condition", "round(qtySpin)"),
    ("condition", "not (discountCheck and rushRadio)"),
    ("condition", "discountCheck.checked"),
    ("condition", "discountCheck and rushRadio or nameEdit == \"Ada\""),
    ("condition", "qtySpin + priceSpin + taxSpin + feeSpin + minSpin"),
    ("value", "is_blank(nameEdit)"),
    ("value", "round(qtySpin)"),
    ("value", "(qtySpin + priceSpin) * taxSpin"),
    ("value", "qtySpin + priceSpin + taxSpin + feeSpin + minSpin"),
    ("value", "1 if discountCheck else 0 if rushRadio else 2"),
    ("value", "discountCheck.checked"),
    ("value", "qtySpin.value()"),
)


def _env() -> FormulaEnv:
    widgets = {
        "discountCheck": WidgetFacts("QCheckBox", "Discount"),
        "rushRadio": WidgetFacts("QRadioButton", "Rush"),
        "qtySpin": WidgetFacts("QSpinBox", "Qty"),
        "priceSpin": WidgetFacts("QDoubleSpinBox", "Price", decimals=2),
        "taxSpin": WidgetFacts("QSpinBox", "Tax"),
        "feeSpin": WidgetFacts("QSpinBox", "Fee"),
        "minSpin": WidgetFacts("QSpinBox", "Min"),
        "nameEdit": WidgetFacts("QLineEdit", "Name", kind="text"),
        "whenEdit": WidgetFacts("QLineEdit", "When", kind="date"),
        "statusCombo": WidgetFacts("QComboBox", "Status", has_items_data=True),
    }
    return FormulaEnv.for_test(widgets)


@pytest.mark.parametrize("formula", _CONDITIONS)
def test_condition_round_trip(formula: str) -> None:
    model = load_formula(formula, _env(), "condition")
    assert model is not None, formula
    assert write_formula(model) == formula


@pytest.mark.parametrize("formula", _VALUES)
def test_value_round_trip(formula: str) -> None:
    model = load_formula(formula, _env(), "value")
    assert model is not None, formula
    assert write_formula(model) == formula


@pytest.mark.parametrize("kind,formula", _OUTSIDE)
def test_outside_the_builder_does_not_load(kind: str, formula: str) -> None:
    assert load_formula(formula, _env(), kind) is None


def test_empty_text_is_an_empty_builder() -> None:
    env = _env()
    for kind in ("condition", "value"):
        model = load_formula("   ", env, kind)
        assert model is not None
        assert write_formula(model) == ""


def test_builder_readback_uses_menu_words() -> None:
    from app.features.form_builder.qtside.formula.builder.words import speak

    env = _env()
    value = load_formula("qtySpin * priceSpin", env, "value")
    assert value is not None
    assert speak(value, env) == "Qty × Price"
    choice = load_formula("qtySpin * priceSpin if discountCheck else 0", env, "value")
    assert choice is not None
    assert speak(choice, env) == "If Discount is checked, then Qty × Price, otherwise 0"
    both = load_formula("discountCheck and discountCheck", env, "condition")
    assert both is not None
    assert speak(both, env) == "Discount is checked and Discount is checked"


def test_picker_label_uses_the_display_name_and_kind() -> None:
    from app.features.form_builder.qtside.formula.builder.model import picker_label

    assert picker_label(_env(), "qtySpin") == "Qty · Whole number"
