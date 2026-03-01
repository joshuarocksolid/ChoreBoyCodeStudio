"""Unit tests for quick-open ranking helpers."""

import pytest

from app.editors.quick_open import QuickOpenCandidate, rank_candidates

pytestmark = pytest.mark.unit


def test_rank_candidates_prioritizes_filename_prefix_matches() -> None:
    """Candidates with filename prefix matches should rank first."""
    candidates = [
        QuickOpenCandidate(relative_path="app/main_window.py", absolute_path="/tmp/app/main_window.py"),
        QuickOpenCandidate(relative_path="docs/main_notes.md", absolute_path="/tmp/docs/main_notes.md"),
        QuickOpenCandidate(relative_path="app/helpers.py", absolute_path="/tmp/app/helpers.py"),
    ]

    ranked = rank_candidates(candidates, "main")
    assert [candidate.relative_path for candidate in ranked[:2]] == [
        "app/main_window.py",
        "docs/main_notes.md",
    ]


def test_rank_candidates_returns_all_when_query_blank() -> None:
    """Blank query should preserve original order up to limit."""
    candidates = [
        QuickOpenCandidate(relative_path="a.py", absolute_path="/tmp/a.py"),
        QuickOpenCandidate(relative_path="b.py", absolute_path="/tmp/b.py"),
    ]
    ranked = rank_candidates(candidates, "")
    assert ranked == candidates
