"""`not (x)` is Python's not with brackets, not Excel's NOT(x)."""

from __future__ import annotations

import pytest

from app.features.form_builder.engine.logic.formula import analyze
from tests.form_builder.engine.logic.formula.support import ENV, SLOTS

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "text",
    ["not (discountCheck and discountCheck)", "not(discountCheck)", "not (qtySpin > 1)"],
)
def test_lowercase_not_with_brackets_is_clean(text: str) -> None:
    got = analyze(text, ENV, SLOTS["cond"])
    assert got.problems == ()
    assert got.fixes == ()


def test_excel_not_still_gets_the_fix() -> None:
    got = analyze("NOT(discountCheck)", ENV, SLOTS["cond"])
    assert [fix.replacement for fix in got.fixes] == ["not discountCheck"]
