"""Unit tests for quick-open ranking helpers."""

import pytest

from app.editors.quick_open import QuickOpenCandidate, rank_candidates

pytestmark = pytest.mark.unit


def test_rank_candidates_prioritizes_filename_prefix_matches() -> None:
    candidates = [
        QuickOpenCandidate(relative_path="app/main_window.py", absolute_path="/tmp/app/main_window.py"),
        QuickOpenCandidate(relative_path="docs/main_notes.md", absolute_path="/tmp/docs/main_notes.md"),
        QuickOpenCandidate(relative_path="app/helpers.py", absolute_path="/tmp/app/helpers.py"),
    ]

    ranked = rank_candidates(candidates, "main")
    paths = [r.candidate.relative_path for r in ranked[:2]]
    assert "app/main_window.py" in paths
    assert "docs/main_notes.md" in paths


def test_rank_candidates_returns_all_when_query_blank() -> None:
    candidates = [
        QuickOpenCandidate(relative_path="a.py", absolute_path="/tmp/a.py"),
        QuickOpenCandidate(relative_path="b.py", absolute_path="/tmp/b.py"),
    ]
    ranked = rank_candidates(candidates, "")
    assert [r.candidate.relative_path for r in ranked] == ["a.py", "b.py"]


def test_fuzzy_match_non_contiguous() -> None:
    candidates = [
        QuickOpenCandidate(relative_path="app/editors/quick_open_dialog.py", absolute_path="/tmp/qod.py"),
        QuickOpenCandidate(relative_path="app/helpers.py", absolute_path="/tmp/helpers.py"),
    ]
    ranked = rank_candidates(candidates, "qod")
    assert len(ranked) == 1
    assert ranked[0].candidate.relative_path == "app/editors/quick_open_dialog.py"
    assert len(ranked[0].match_positions) == 3


def test_open_files_prioritized_when_query_empty() -> None:
    candidates = [
        QuickOpenCandidate(relative_path="a.py", absolute_path="/tmp/a.py", is_open=False),
        QuickOpenCandidate(relative_path="b.py", absolute_path="/tmp/b.py", is_open=True),
        QuickOpenCandidate(relative_path="c.py", absolute_path="/tmp/c.py", is_open=False),
    ]
    ranked = rank_candidates(candidates, "")
    assert ranked[0].candidate.relative_path == "b.py"
