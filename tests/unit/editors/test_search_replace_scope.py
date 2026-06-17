"""Replace-scope tests for project search (CC-EDIT-14 / EDIT-R-04).

TN-EDIT-SEARCH-3: ``replace_in_files`` must replace only the capped match list
that the sidebar shows, not every occurrence in the file via ``pattern.sub``.

This test fails until EDIT-R-23 scopes replace to ``SearchMatch`` spans.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.editors.search_panel import find_in_files, replace_in_files

pytestmark = pytest.mark.unit

SIDEBAR_DISPLAY_CAP = 3
NEEDLE = "needle"
REPLACEMENT = "haystack"
TOTAL_MATCHES = 10


def _project_with_ten_needle_lines(tmp_path: Path) -> tuple[Path, Path]:
    project_root = tmp_path / "project"
    project_root.mkdir()
    source_file = project_root / "matches.py"
    lines = [f"{NEEDLE} line {index}" for index in range(1, TOTAL_MATCHES + 1)]
    source_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return project_root, source_file


def test_replace_in_files_honors_capped_match_list(tmp_path: Path) -> None:
    """Replace-all must edit only the capped matches shown in the sidebar."""
    project_root, source_file = _project_with_ten_needle_lines(tmp_path)

    capped_matches = find_in_files(project_root, NEEDLE, max_results=SIDEBAR_DISPLAY_CAP)
    assert len(capped_matches) == SIDEBAR_DISPLAY_CAP

    count = replace_in_files(capped_matches, REPLACEMENT, NEEDLE)
    content = source_file.read_text(encoding="utf-8")

    assert count == SIDEBAR_DISPLAY_CAP
    assert content.count(REPLACEMENT) == SIDEBAR_DISPLAY_CAP
    assert content.count(NEEDLE) == TOTAL_MATCHES - SIDEBAR_DISPLAY_CAP
