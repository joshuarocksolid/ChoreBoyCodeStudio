"""Unit tests for bulk file tree operations (delete, duplicate, paste)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.project.file_operations import copy_path, delete_path, duplicate_path, move_path

pytestmark = pytest.mark.unit


def test_bulk_delete_removes_all_targets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str((tmp_path / "xdg_data").resolve()))
    files = []
    for name in ("a.py", "b.py", "c.txt"):
        f = tmp_path / name
        f.write_text(f"# {name}\n", encoding="utf-8")
        files.append(f)

    for f in files:
        result = delete_path(str(f))
        assert result.success is True

    for f in files:
        assert not f.exists()


def test_bulk_delete_reports_missing_target(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str((tmp_path / "xdg_data").resolve()))
    existing = tmp_path / "real.py"
    existing.write_text("x = 1\n", encoding="utf-8")
    missing = tmp_path / "ghost.py"

    result_ok = delete_path(str(existing))
    result_fail = delete_path(str(missing))

    assert result_ok.success is True
    assert result_fail.success is False


def test_bulk_duplicate_creates_copies_for_all(tmp_path: Path) -> None:
    originals = []
    for name in ("one.py", "two.py"):
        f = tmp_path / name
        f.write_text(f"# {name}\n", encoding="utf-8")
        originals.append(f)

    destinations = []
    for f in originals:
        result = duplicate_path(str(f))
        assert result.success is True
        assert result.destination_path is not None
        dest = Path(result.destination_path)
        assert dest.exists()
        destinations.append(dest)

    for orig in originals:
        assert orig.exists(), "originals should remain after duplication"

    assert len(destinations) == 2
    assert destinations[0].name == "one.py.copy"
    assert destinations[1].name == "two.py.copy"


def test_bulk_delete_directories_and_files_mixed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str((tmp_path / "xdg_data").resolve()))
    file_a = tmp_path / "file.txt"
    file_a.write_text("content\n", encoding="utf-8")
    dir_b = tmp_path / "subdir"
    dir_b.mkdir()
    (dir_b / "nested.py").write_text("y = 2\n", encoding="utf-8")

    assert delete_path(str(file_a)).success is True
    assert delete_path(str(dir_b)).success is True

    assert not file_a.exists()
    assert not dir_b.exists()


def test_multi_paste_copy_places_all_sources(tmp_path: Path) -> None:
    """Simulates pasting multiple clipboard items into a destination directory."""
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()

    sources = []
    for name in ("alpha.py", "beta.py", "gamma.py"):
        f = src_dir / name
        f.write_text(f"# {name}\n", encoding="utf-8")
        sources.append(f)

    for source in sources:
        destination = dest_dir / source.name
        result = copy_path(str(source), str(destination))
        assert result.success is True

    for source in sources:
        assert source.exists(), "copy should not remove sources"
        assert (dest_dir / source.name).exists()


def test_multi_paste_cut_moves_all_sources(tmp_path: Path) -> None:
    """Simulates cut-paste of multiple clipboard items."""
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()

    sources = []
    for name in ("x.py", "y.py"):
        f = src_dir / name
        f.write_text(f"# {name}\n", encoding="utf-8")
        sources.append(f)

    for source in sources:
        destination = dest_dir / source.name
        result = move_path(str(source), str(destination))
        assert result.success is True

    for source in sources:
        assert not source.exists(), "move should remove sources"
        assert (dest_dir / source.name).exists()


def test_multi_paste_reports_conflict_without_blocking_others(tmp_path: Path) -> None:
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()

    good = src_dir / "good.py"
    good.write_text("ok\n", encoding="utf-8")
    conflict = src_dir / "conflict.py"
    conflict.write_text("dup\n", encoding="utf-8")
    (dest_dir / "conflict.py").write_text("existing\n", encoding="utf-8")

    result_good = copy_path(str(good), str(dest_dir / "good.py"))
    result_conflict = copy_path(str(conflict), str(dest_dir / "conflict.py"))

    assert result_good.success is True
    assert result_conflict.success is False
    assert (dest_dir / "good.py").exists()
