"""Behavior of the shared formula helpers."""

from __future__ import annotations

import ast
from decimal import Decimal
from datetime import date

import pytest

from app.features.form_builder.engine.logic.formula import helper_sources, helper_table, live_helpers


class _Text(object):
    def __init__(self, text: str) -> None:
        self._text = text

    def text(self) -> str:
        return self._text


@pytest.mark.unit
def test_live_helpers_are_the_table() -> None:
    ids = [helper_id for helper_id, _source in helper_table()]
    assert len(ids) == len(set(ids))
    first = live_helpers()
    second = live_helpers()
    assert first is not second
    assert list(first) == ids
    assert first["_cbcs_add"] is second["_cbcs_add"]
    first["extra"] = 1
    assert "extra" not in live_helpers()
    assert "Decimal" not in first
    assert "__builtins__" not in first
    for helper_id, source in helper_table():
        assert source.startswith("def %s(" % helper_id)
        assert source.endswith("\n")
        ast.parse(source)


@pytest.mark.unit
def test_helper_sources_follow_table_order() -> None:
    text = helper_sources(["_cbcs_div", "missing", "_cbcs_is_blank"])
    assert text.index("def _cbcs_is_blank") < text.index("def _cbcs_div")
    assert "\n\n" in text
    assert "missing" not in text
    assert helper_sources(["nope"]) == ""


@pytest.mark.unit
def test_arithmetic_blank_and_rounding() -> None:
    live = live_helpers()
    assert live["_cbcs_div"](7, 0) is None
    assert live["_cbcs_div"](7, 2) == Decimal("3.5")
    assert live["_cbcs_div"](1, None) is None
    assert live["_cbcs_add"](1, None) is None
    assert live["_cbcs_sub"](None, 1) is None
    assert live["_cbcs_mul"](4, None) is None
    assert live["_cbcs_neg"](None) is None
    assert live["_cbcs_add"](2, 3) == 5
    assert live["_cbcs_round"](Decimal("2.5")) == Decimal("3")
    assert live["_cbcs_round"](Decimal("-2.5")) == Decimal("-3")
    assert live["_cbcs_number"]("$1,234.50") == Decimal("1234.50")
    assert live["_cbcs_number"]("1234.5") == Decimal("1234.5")
    assert live["_cbcs_whole"](Decimal("-1.9")) == -1
    assert live["_cbcs_money"](None) == ""
    assert live["_cbcs_money"](Decimal("1234.5")) == "$1,234.50"
    assert live["_cbcs_money"](Decimal("-12")) == "-$12.00"


@pytest.mark.unit
def test_blank_compare_and_aggregates() -> None:
    live = live_helpers()
    assert live["_cbcs_is_blank"](None) is True
    assert live["_cbcs_is_blank"]("  ") is True
    assert live["_cbcs_is_blank"](0) is False
    assert live["_cbcs_is_blank"](False) is False
    assert live["_cbcs_lt"](None, 1) is False
    assert live["_cbcs_eq"](None, None) is True
    assert live["_cbcs_eq"](None, "") is True
    assert live["_cbcs_eq"](None, "  ") is True
    assert live["_cbcs_ne"](None, None) is False
    assert live["_cbcs_concat"](None, "a") == "a"
    assert live["_cbcs_concat"]("hello", " world") == "hello world"
    assert live["_cbcs_sum"](None, "", "  ") == 0
    assert live["_cbcs_avg"](None, " ") is None
    assert live["_cbcs_min"](None, "") is None
    assert live["_cbcs_min"](None, 3, None) == 3
    assert live["_cbcs_text"](Decimal("1.50")) == "1.50"
    assert live["_cbcs_text"](date(2026, 10, 20), "date:long") == "October 20, 2026"


@pytest.mark.unit
def test_predicates_dates_and_months() -> None:
    live = live_helpers()
    assert live["_cbcs_matches"]("abc", "(") is False
    assert live["_cbcs_matches"]("abc", "a" * 201) is False
    assert live["_cbcs_matches"]("abc", "abc") is True
    assert live["_cbcs_is_email"]("a@b.co") is True
    assert live["_cbcs_is_email"]("not-an-email") is False
    assert live["_cbcs_is_email"]("") is False
    assert live["_cbcs_is_phone"]("555-123-4567") is True
    assert live["_cbcs_is_phone"]("+1 (555) 123-4567") is True
    assert live["_cbcs_is_phone"]("123") is False
    assert live["_cbcs_is_zip"]("12345") is True
    assert live["_cbcs_is_zip"]("12345-6789") is True
    assert live["_cbcs_is_zip"]("1234") is False
    assert live["_cbcs_date"](2020, 2, 31) is None
    monday = date(2020, 6, 1)
    assert monday.weekday() == 0
    assert live["_cbcs_weekday"](monday) == 1
    assert live["_cbcs_add_months"](date(2021, 1, 31), 1) == date(2021, 2, 28)
    assert live["_cbcs_add_months"](date(2020, 1, 31), 1) == date(2020, 2, 29)
    widget = _Text("$1,234.50")
    assert live["_cbcs_read_money"](widget) == Decimal("1234.50")
    assert live["_cbcs_read_money"](_Text("(1.00)")) == Decimal("-1.00")
    assert live["_cbcs_read_money"](_Text("-$1.00")) == Decimal("-1.00")
    assert live["_cbcs_read_money"](_Text("  ")) is None


_OPERATORS_AND_READS = frozenset(
    {
        "_cbcs_add",
        "_cbcs_sub",
        "_cbcs_mul",
        "_cbcs_div",
        "_cbcs_neg",
        "_cbcs_not",
        "_cbcs_and",
        "_cbcs_or",
        "_cbcs_bool",
        "_cbcs_concat",
        "_cbcs_is_blank",
        "_cbcs_lt",
        "_cbcs_le",
        "_cbcs_gt",
        "_cbcs_ge",
        "_cbcs_eq",
        "_cbcs_ne",
        "_cbcs_in",
        "_cbcs_not_in",
        "_cbcs_date_diff",
        "_cbcs_add_days",
        "_cbcs_dec",
        "_cbcs_read_spin",
        "_cbcs_read_double",
        "_cbcs_read_check",
        "_cbcs_read_radio",
        "_cbcs_read_dateedit",
        "_cbcs_read_timeedit",
        "_cbcs_read_datetime",
        "_cbcs_read_list",
        "_cbcs_read_plain",
        "_cbcs_read_line",
        "_cbcs_read_shown",
        "_cbcs_read_enabled",
        "_cbcs_read_visible",
        "_cbcs_read_checked",
        "_cbcs_read_count",
        "_cbcs_read_money",
        "_cbcs_read_percent",
        "_cbcs_read_whole",
        "_cbcs_read_number",
        "_cbcs_read_date",
        "_cbcs_read_time",
        "_cbcs_read_label_money",
        "_cbcs_read_label_percent",
        "_cbcs_read_label_whole",
        "_cbcs_read_label_number",
        "_cbcs_read_label_date",
        "_cbcs_read_label_time",
        "_cbcs_read_plain_money",
        "_cbcs_read_plain_percent",
        "_cbcs_read_plain_whole",
        "_cbcs_read_plain_number",
        "_cbcs_read_plain_date",
        "_cbcs_read_plain_time",
    }
)


def _reachable() -> set:
    import re

    from app.features.form_builder.engine.logic.formula.library import FUNCTIONS

    sources = {helper_id: source for helper_id, source in helper_table()}
    roots = {spec.helper_id for spec in FUNCTIONS.values()} | set(_OPERATORS_AND_READS)
    needed = set(roots)
    changed = True
    pattern = re.compile(r"\b(_cbcs_[A-Za-z0-9_]*)\b")
    while changed:
        changed = False
        for helper_id in list(needed):
            text = sources.get(helper_id, "")
            for found in pattern.findall(text):
                if found in sources and found not in needed:
                    needed.add(found)
                    changed = True
    return needed


@pytest.mark.unit
def test_every_library_helper_is_in_the_runtime_table() -> None:
    from app.features.form_builder.engine.logic.formula.library import FUNCTIONS

    table = {helper_id for helper_id, _source in helper_table()}
    missing = sorted(spec.helper_id for spec in FUNCTIONS.values() if spec.helper_id not in table)
    assert missing == []


@pytest.mark.unit
def test_every_helper_is_reachable_from_a_function_operator_or_read() -> None:
    table = {helper_id for helper_id, _source in helper_table()}
    assert sorted(table - _reachable()) == []
