"""A multi-file write keeps modes and does not leave a temp behind."""

from __future__ import annotations

import errno
import os
from pathlib import Path

import pytest

from app.persistence.file_unit import commit_files, restore_file

pytestmark = pytest.mark.unit


def _names(directory: Path) -> list[str]:
    return sorted(path.name for path in directory.iterdir())


def test_a_failed_write_removes_the_temp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    directory = tmp_path / "w"
    directory.mkdir()
    first = directory / "a.txt"
    second = directory / "b.txt"
    first.write_bytes(b"A0")
    second.write_bytes(b"B0")
    calls = {"count": 0}
    real = os.write

    def fail_second(fd: int, data: bytes) -> int:
        calls["count"] += 1
        if calls["count"] == 2:
            raise OSError(errno.ENOSPC, "full")
        return real(fd, data)

    monkeypatch.setattr(os, "write", fail_second)
    sentence = commit_files([(str(first), b"A1", b"A0"), (str(second), b"B1", b"B0")])
    assert sentence
    assert first.read_bytes() == b"A0"
    assert second.read_bytes() == b"B0"
    assert _names(directory) == ["a.txt", "b.txt"]


def test_restore_keeps_the_mode_and_a_failed_replace_leaves_no_temp(tmp_path: Path) -> None:
    directory = tmp_path / "m"
    directory.mkdir()
    path = directory / "a.sh"
    path.write_bytes(b"x")
    os.chmod(path, 0o755)
    assert restore_file(str(path), b"y") == ""
    assert path.read_bytes() == b"y"
    assert path.stat().st_mode & 0o777 == 0o755

    def fail(_source: str, _dest: str) -> None:
        raise OSError(errno.EIO, "io")

    assert restore_file(str(path), b"z", fail)
    assert path.read_bytes() == b"y"
    assert _names(directory) == ["a.sh"]


@pytest.mark.parametrize("mask,mode", [(0o022, 0o644), (0o002, 0o664)])
def test_a_new_file_gets_the_umask_mode(tmp_path: Path, mask: int, mode: int) -> None:
    previous = os.umask(mask)
    try:
        path = tmp_path / "new.py"
        assert commit_files([(str(path), b"z\n", None)]) == ""
        assert path.stat().st_mode & 0o777 == mode
    finally:
        os.umask(previous)


def test_a_failed_replace_removes_every_temp(tmp_path: Path) -> None:
    directory = tmp_path / "rf"
    directory.mkdir()
    first = directory / "a.txt"
    second = directory / "b.txt"
    first.write_bytes(b"A0")
    second.write_bytes(b"B0")
    calls = {"count": 0}
    real = os.replace

    def fail_later(source: str, dest: str) -> None:
        calls["count"] += 1
        if calls["count"] in (2, 3):
            raise OSError(errno.EIO, "io")
        real(source, dest)

    sentence = commit_files(
        [(str(first), b"A1", b"A0"), (str(second), b"B1", b"B0")],
        replace=fail_later,
    )
    assert "Couldn't restore" in sentence
    assert _names(directory) == ["a.txt", "b.txt"]
