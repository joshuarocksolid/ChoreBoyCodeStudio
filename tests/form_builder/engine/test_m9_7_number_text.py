"""Value writes show a Decimal as plain digits."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

import pytest

from app.features.form_builder.engine.codegen.expanders.defaults import write_value
from app.features.form_builder.engine.logic.formula.env import WidgetFacts
from app.features.form_builder.engine.logic.formula.runtime import live_helpers

pytestmark = pytest.mark.unit


class _Edit(object):
    def __init__(self) -> None:
        self._text = ""

    def setText(self, text: str) -> None:
        self._text = text

    def text(self) -> str:
        return self._text


class _Host(object):
    def __init__(self, edit: _Edit) -> None:
        self.amountEdit = edit


def _shown(fmt: str, expr: str) -> str:
    lines, helpers, _imports = write_value(
        "amountEdit",
        WidgetFacts("QLineEdit"),
        ("amountEdit",),
        fmt,
        expr,
    )
    live = live_helpers()
    namespace = {"Decimal": Decimal, "ROUND_HALF_UP": ROUND_HALF_UP}
    for name in helpers:
        namespace[name] = live[name]
    edit = _Edit()
    namespace["self"] = _Host(edit)
    exec("\n".join(lines), namespace)  # noqa: S102
    return edit.text()


def test_a_value_rule_shows_two_hundred_not_scientific_notation() -> None:
    assert _shown("", "Decimal('2E+2')") == "200"


def test_number_two_shows_one_third_as_two_places() -> None:
    shown = _shown("number:2", "Decimal(1) / Decimal(3)")
    assert shown == "0.33"
    assert "33333333333333333333333333" not in shown
