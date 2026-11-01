"""UX-M7-003 Mac budgets.

The numbers are the Mac column of the speed table. The form contract is the
M6 reference form plus 100 stored rules and 60 stored checks. The added-cost
row uses the M6.R pairing, warmup dropped, negative differences clipped.
"""

from __future__ import annotations

import pytest

from tests.form_builder.perf.m7_paths import (
    FORMULA,
    MAC_ROWS,
    count_logic,
    paired_added,
    reference_xml,
)

pytestmark = pytest.mark.unit


def test_the_reference_form_stores_100_rules_and_60_checks() -> None:
    assert len(FORMULA) == 200
    rules, checks = count_logic(reference_xml())
    assert rules == 100
    assert checks == 60


def test_mac_budget_rows_match_ux_m7_003() -> None:
    assert tuple((row.key, row.budget_ms) for row in MAC_ROWS) == (
        ("analyze_compile", 2.0),
        ("formula_keystroke", 16.0),
        ("behavior_fill", 16.0),
        ("commit_added", 17.0),
        ("save", 80.0),
        ("cbcs_refresh", 5.0),
        ("preview_reload", 500.0),
    )


def test_commit_added_drops_warmup_and_clips_at_zero() -> None:
    added = paired_added([20.0, 9.0, 4.0], [3.0, 5.0, 6.0])
    assert added == [4.0, 0.0]
