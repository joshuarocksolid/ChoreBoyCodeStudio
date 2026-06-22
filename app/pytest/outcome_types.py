"""Shared pytest outcome and node-kind vocabulary."""

from __future__ import annotations

from typing import Final, Literal

TestOutcome = Literal["passed", "failed", "skipped", "error", "not_run"]
TestNodeKind = Literal["file", "class", "function"]

SUMMARY_OUTCOME_PREFIXES: Final[tuple[tuple[str, TestOutcome], ...]] = (
    ("PASSED ", "passed"),
    ("FAILED ", "failed"),
    ("SKIPPED ", "skipped"),
    ("ERROR ", "error"),
)

VERBOSE_OUTCOME_SUFFIXES: Final[tuple[tuple[str, TestOutcome], ...]] = (
    (" PASSED", "passed"),
    (" FAILED", "failed"),
    (" SKIPPED", "skipped"),
    (" ERROR", "error"),
)
