"""The form builder manual stays aligned with the shortcut table and the problem codes."""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.check_form_builder_manual_links import link_errors
from tools.form_builder_user_manual import (
    DIAGNOSTICS_PATH,
    KEYBOARD_PATH,
    diagnostics_markdown,
    keyboard_markdown,
    keyboard_pairs,
    visible_codes,
)

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[3]


def _key_rows(text: str) -> list:
    rows = []
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip().replace("\\|", "|") for cell in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        if cells[0] in ("Keys", "Code") or set(cells[0]) <= set("-: "):
            continue
        rows.append((cells[0], cells[1]))
    return rows


def test_keyboard_page_lists_every_registered_shortcut() -> None:
    text = KEYBOARD_PATH.read_text(encoding="utf-8")
    listed = _key_rows(text)
    missing = [pair for pair in keyboard_pairs() if pair not in listed]
    assert missing == []


def test_keyboard_page_matches_the_generator() -> None:
    assert KEYBOARD_PATH.read_text(encoding="utf-8") == keyboard_markdown()


def test_diagnostics_page_lists_every_visible_code() -> None:
    text = DIAGNOSTICS_PATH.read_text(encoding="utf-8")
    missing = [code for code in visible_codes() if "| %s |" % code not in text]
    assert missing == []


def test_diagnostics_page_matches_the_generator() -> None:
    assert DIAGNOSTICS_PATH.read_text(encoding="utf-8") == diagnostics_markdown()


def test_link_check_reports_a_missing_file(tmp_path: Path) -> None:
    page = tmp_path / "page.md"
    page.write_text("See [the other page](missing.md).\n", encoding="utf-8")
    assert link_errors([page]) == ["page.md -> missing.md"]
