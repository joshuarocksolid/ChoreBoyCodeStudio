"""Unit tests for atomic text-file writes."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.persistence.atomic_write import atomic_write_text

pytestmark = pytest.mark.unit


def test_atomic_write_text_writes_file_and_leaves_no_temp_files(tmp_path: Path) -> None:
    target = tmp_path / "notes.txt"

    written_path = atomic_write_text(target, "updated\n")

    assert written_path == target.resolve()
    assert target.read_text(encoding="utf-8") == "updated\n"
    assert list(tmp_path.glob("notes.txt.*.tmp")) == []


def test_atomic_write_text_preserves_original_content_when_replace_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "notes.txt"
    target.write_text("original\n", encoding="utf-8")

    def raise_replace(_src: str, _dst: str) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr("app.persistence.atomic_write.os.replace", raise_replace)

    with pytest.raises(OSError, match="simulated replace failure"):
        atomic_write_text(target, "updated\n")

    assert target.read_text(encoding="utf-8") == "original\n"
    assert list(tmp_path.glob("notes.txt.*.tmp")) == []
