"""Unit tests for project file operations."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.project.file_operations import copy_path, create_directory, create_file, delete_path, duplicate_path, move_path, rename_path

pytestmark = pytest.mark.unit


def test_create_and_delete_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    xdg_data_home = tmp_path / "xdg_data"
    xdg_data_home.mkdir()
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg_data_home))
    target = tmp_path / "folder" / "new.py"
    create_result = create_file(str(target), content="print('ok')\n")
    assert create_result.success is True
    assert target.exists()

    delete_result = delete_path(str(target))
    assert delete_result.success is True
    assert not target.exists()
    assert delete_result.message == "Path moved to trash."


def test_rename_move_copy_and_duplicate(tmp_path: Path) -> None:
    source = tmp_path / "source.py"
    source.write_text("x=1\n", encoding="utf-8")

    renamed = tmp_path / "renamed.py"
    assert rename_path(str(source), str(renamed)).success is True
    assert renamed.exists()

    moved = tmp_path / "nested" / "moved.py"
    assert move_path(str(renamed), str(moved)).success is True
    assert moved.exists()

    copied = tmp_path / "nested" / "copy.py"
    assert copy_path(str(moved), str(copied)).success is True
    assert copied.exists()

    duplicate_result = duplicate_path(str(copied))
    assert duplicate_result.success is True
    assert Path(str(duplicate_result.destination_path)).exists()


def test_create_directory_conflict_returns_failure(tmp_path: Path) -> None:
    folder = tmp_path / "folder"
    folder.mkdir()
    result = create_directory(str(folder))
    assert result.success is False


def test_delete_path_moves_to_trash_when_enabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Delete operation should prefer user trash path when available."""
    xdg_data_home = tmp_path / "xdg_data"
    xdg_data_home.mkdir()
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg_data_home))
    target = tmp_path / "trash_me.py"
    target.write_text("print('x')\n", encoding="utf-8")

    result = delete_path(str(target), use_trash=True)

    assert result.success is True
    assert target.exists() is False
    assert result.destination_path is not None
    assert Path(result.destination_path).exists()


def test_delete_path_defaults_to_permanent_delete_even_when_home_exists(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Explicit permanent delete remains available for non-trash scenarios."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    target = tmp_path / "permanent_delete.py"
    target.write_text("print('x')\n", encoding="utf-8")

    result = delete_path(str(target), use_trash=False)

    assert result.success is True
    assert result.message == "Path deleted permanently."
    assert target.exists() is False
    assert (fake_home / ".local" / "share" / "Trash" / "files").exists() is False
