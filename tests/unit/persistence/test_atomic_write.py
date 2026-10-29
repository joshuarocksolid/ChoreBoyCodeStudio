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


def test_atomic_write_text_keeps_crlf_and_mode_of_existing_file(tmp_path: Path) -> None:
    target = tmp_path / "script.sh"
    target.write_bytes(b"one\r\ntwo\r\nthree\r\n")
    target.chmod(0o755)

    atomic_write_text(target, "one\ntwo edited\nthree\n")

    assert target.read_bytes() == b"one\r\ntwo edited\r\nthree\r\n"
    assert target.stat().st_mode & 0o7777 == 0o755


def test_atomic_write_text_mixed_file_uses_dominant_style(tmp_path: Path) -> None:
    target = tmp_path / "mixed.txt"
    target.write_bytes(b"a\r\nb\r\nc\nd\r\n")

    atomic_write_text(target, "a\nb\nc\nd\n")

    assert target.read_bytes() == b"a\r\nb\r\nc\r\nd\r\n"


def test_atomic_write_text_keeps_cr_and_lf_styles(tmp_path: Path) -> None:
    cr_file = tmp_path / "mac.txt"
    cr_file.write_bytes(b"a\rb\r")
    lf_file = tmp_path / "unix.txt"
    lf_file.write_bytes(b"a\nb\n")

    atomic_write_text(cr_file, "a\nb\nc\n")
    atomic_write_text(lf_file, "a\nb\nc\n")

    assert cr_file.read_bytes() == b"a\rb\rc\r"
    assert lf_file.read_bytes() == b"a\nb\nc\n"


def test_atomic_write_text_new_file_gets_default_mode_minus_umask(tmp_path: Path) -> None:
    import os

    old_umask = os.umask(0o022)
    try:
        target = tmp_path / "fresh.txt"
        atomic_write_text(target, "x\n")
    finally:
        os.umask(old_umask)

    assert target.stat().st_mode & 0o7777 == 0o644
    assert target.read_bytes() == b"x\n"
