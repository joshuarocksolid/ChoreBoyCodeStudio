"""Seeded command sequences (CONTRACTS.md section 13)."""

from __future__ import annotations

import pytest

from tests.support.form_builder.gen import run_many


def test_generated_sequences_hold_the_invariants() -> None:
    summary = run_many(20, 30)
    assert "failed 0" in summary


@pytest.mark.perf
@pytest.mark.timeout(280)
def test_gate_run_holds_the_invariants() -> None:
    summary = run_many(5000, 50)
    print(summary)
    assert "failed 0" in summary
