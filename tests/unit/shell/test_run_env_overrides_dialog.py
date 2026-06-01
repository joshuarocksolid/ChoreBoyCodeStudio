"""Unit tests for the environment overrides table editor."""

from __future__ import annotations

import pytest

from app.project.run_configs import parse_env_overrides_text
from app.shell.run_env_overrides_dialog import collect_env_overrides_from_rows, summarize_env_overrides

pytestmark = pytest.mark.unit


def test_summarize_env_overrides_empty() -> None:
    assert summarize_env_overrides({}) == "(none)"


def test_summarize_env_overrides_sorted() -> None:
    assert summarize_env_overrides({"B": "2", "A": "1"}) == "A=1, B=2"


def test_summarize_env_overrides_truncates_long_text() -> None:
    long_value = "x" * 100
    summary = summarize_env_overrides({"KEY": long_value}, max_length=20)
    assert summary.endswith("...")
    assert len(summary) == 20


def test_collect_env_overrides_from_rows() -> None:
    collected = collect_env_overrides_from_rows(
        [
            ("DEBUG", "1"),
            ("LOG_LEVEL", "debug"),
        ]
    )
    assert collected == {"DEBUG": "1", "LOG_LEVEL": "debug"}


def test_collect_env_overrides_from_rows_skips_blank_names() -> None:
    collected = collect_env_overrides_from_rows([("", "ignored"), ("KEEP", "yes")])
    assert collected == {"KEEP": "yes"}


def test_parse_env_overrides_text_supports_paste_format() -> None:
    parsed = parse_env_overrides_text("DEBUG=1, LOG_LEVEL=debug")
    assert parsed == {"DEBUG": "1", "LOG_LEVEL": "debug"}
