"""Pure-logic tests for the diff parser used by the polished dialogs.

Per ``.cursor/rules/testing_when_to_write.mdc``, only the non-trivial
classification branches in ``compute_diff_hunks`` and the boundary
buckets of ``_format_relative`` are covered here.  Visual layout,
gutter painting, and stylesheet output are intentionally not tested.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.shell.diff_view import (
    LINE_KIND_ADD,
    LINE_KIND_CONTEXT,
    LINE_KIND_REMOVE,
    compute_diff_hunks,
)
from app.shell.local_history_dialog import _format_relative

pytestmark = pytest.mark.unit


def _kinds(hunks):
    return [line.kind for hunk in hunks for line in hunk.lines]


def test_compute_diff_hunks_returns_empty_for_identical_inputs() -> None:
    hunks, stats, raw = compute_diff_hunks(
        "alpha\nbeta\n",
        "alpha\nbeta\n",
        from_label="left",
        to_label="right",
    )

    assert hunks == []
    assert stats.added == 0
    assert stats.removed == 0
    assert stats.is_empty is True
    assert raw == ""


def test_compute_diff_hunks_classifies_pure_addition() -> None:
    hunks, stats, raw = compute_diff_hunks(
        "alpha\n",
        "alpha\nbeta\n",
        from_label="disk",
        to_label="draft",
    )

    assert stats.added == 1
    assert stats.removed == 0
    assert stats.is_empty is False
    assert "+beta" in raw
    assert LINE_KIND_ADD in _kinds(hunks)
    assert LINE_KIND_REMOVE not in _kinds(hunks)


def test_compute_diff_hunks_classifies_pure_removal() -> None:
    hunks, stats, _ = compute_diff_hunks(
        "alpha\nbeta\n",
        "alpha\n",
        from_label="disk",
        to_label="draft",
    )

    assert stats.added == 0
    assert stats.removed == 1
    assert LINE_KIND_REMOVE in _kinds(hunks)


def test_compute_diff_hunks_classifies_mixed_hunk_with_context() -> None:
    before = "one\ntwo\nthree\nfour\n"
    after = "one\nTWO\nthree\nfour\nfive\n"
    hunks, stats, _ = compute_diff_hunks(
        before, after, from_label="a", to_label="b"
    )

    assert stats.added == 2
    assert stats.removed == 1
    kinds = _kinds(hunks)
    assert LINE_KIND_ADD in kinds
    assert LINE_KIND_REMOVE in kinds
    assert LINE_KIND_CONTEXT in kinds


def test_compute_diff_hunks_handles_trailing_newline_difference() -> None:
    """Adding a trailing newline should produce no diff under splitlines semantics."""
    hunks, stats, raw = compute_diff_hunks(
        "alpha", "alpha\n", from_label="a", to_label="b"
    )

    assert hunks == []
    assert stats.is_empty is True
    assert raw == ""


@pytest.mark.parametrize(
    "delta, expected_substring",
    [
        (timedelta(seconds=5), "just now"),
        (timedelta(minutes=3), "min ago"),
        (timedelta(hours=2), "hr ago"),
    ],
)
def test_format_relative_recent_buckets(delta: timedelta, expected_substring: str) -> None:
    when = datetime.now(timezone.utc).astimezone() - delta
    label = _format_relative(when.isoformat())
    assert expected_substring in label


def test_format_relative_today_uses_clock_label() -> None:
    today = datetime.now(timezone.utc).astimezone().replace(hour=3, minute=15, second=0, microsecond=0)
    label = _format_relative(today.isoformat())
    if (datetime.now(timezone.utc).astimezone() - today).total_seconds() < 12 * 3600:
        assert "hr ago" in label or "min ago" in label or "just now" in label
    else:
        assert "today at" in label


def test_format_relative_returns_empty_for_unparsable_input() -> None:
    assert _format_relative("not-a-timestamp") == ""
    assert _format_relative("") == ""
    assert _format_relative(None) == ""
