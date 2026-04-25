"""Unit tests for the project file inventory SSOT."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.project.file_inventory import (
    iter_project_entries,
    iter_python_files,
    iter_text_file_paths,
    walk_project,
)

pytestmark = pytest.mark.unit


def _seed_python_tree(root: Path) -> None:
    (root / "cbcs").mkdir()
    (root / "cbcs" / "project.json").write_text("{}\n", encoding="utf-8")
    (root / "vendor").mkdir()
    (root / "vendor" / "thirdparty.py").write_text("X = 1\n", encoding="utf-8")
    (root / "src").mkdir()
    (root / "src" / "app.py").write_text("Y = 2\n", encoding="utf-8")
    (root / "src" / "helper.py").write_text("Z = 3\n", encoding="utf-8")
    (root / "src" / "data.json").write_text("{}", encoding="utf-8")
    (root / "build").mkdir()
    (root / "build" / "out.py").write_text("W = 4\n", encoding="utf-8")
    (root / "main.py").write_text("Q = 5\n", encoding="utf-8")


def test_iter_python_files_skips_cbcs_and_returns_sorted_paths(tmp_path: Path) -> None:
    _seed_python_tree(tmp_path)

    relative = sorted(p.relative_to(tmp_path).as_posix() for p in iter_python_files(tmp_path))

    assert "cbcs/project.json" not in relative
    assert relative == [
        "build/out.py",
        "main.py",
        "src/app.py",
        "src/helper.py",
        "vendor/thirdparty.py",
    ]


def test_iter_python_files_extra_top_level_skips_prunes_only_top_level(tmp_path: Path) -> None:
    _seed_python_tree(tmp_path)
    (tmp_path / "src" / "vendor").mkdir()
    (tmp_path / "src" / "vendor" / "nested.py").write_text("# nested\n", encoding="utf-8")

    relative = sorted(
        p.relative_to(tmp_path).as_posix()
        for p in iter_python_files(tmp_path, extra_top_level_skips=("vendor",))
    )

    assert "vendor/thirdparty.py" not in relative
    assert "src/vendor/nested.py" in relative


def test_iter_python_files_applies_name_pattern_excludes(tmp_path: Path) -> None:
    _seed_python_tree(tmp_path)

    relative = sorted(
        p.relative_to(tmp_path).as_posix()
        for p in iter_python_files(tmp_path, exclude_patterns=("build",))
    )

    assert "build/out.py" not in relative
    assert "main.py" in relative


def test_iter_python_files_relative_path_pattern_mode_respects_slashes(tmp_path: Path) -> None:
    _seed_python_tree(tmp_path)

    relative = sorted(
        p.relative_to(tmp_path).as_posix()
        for p in iter_python_files(
            tmp_path,
            exclude_patterns=("src/helper.py",),
            pattern_mode="relative_path",
        )
    )

    assert "src/helper.py" not in relative
    assert "src/app.py" in relative


def test_walk_project_yields_relative_dir_and_allows_caller_pruning(tmp_path: Path) -> None:
    _seed_python_tree(tmp_path)

    visited: list[str] = []
    for current_path, relative_dir, dir_names, file_names in walk_project(tmp_path):
        visited.append(relative_dir)
        if relative_dir == "":
            dir_names[:] = [name for name in dir_names if name != "build"]
        del current_path, file_names

    assert "" in visited
    assert "build" not in visited
    assert "src" in visited


def test_iter_text_file_paths_uses_relative_path_excludes(tmp_path: Path) -> None:
    _seed_python_tree(tmp_path)

    listed = sorted(rel for _absolute, rel in iter_text_file_paths(tmp_path))

    assert "cbcs/project.json" not in listed
    assert "src/data.json" in listed
    assert "main.py" in listed


def test_iter_text_file_paths_supports_glob_patterns_with_slashes(tmp_path: Path) -> None:
    _seed_python_tree(tmp_path)
    (tmp_path / "src" / "generated").mkdir()
    (tmp_path / "src" / "generated" / "code.py").write_text("# gen\n", encoding="utf-8")

    listed = sorted(
        rel
        for _absolute, rel in iter_text_file_paths(
            tmp_path,
            exclude_patterns=("src/generated/*",),
        )
    )

    assert "src/generated/code.py" not in listed
    assert "src/app.py" in listed


def test_iter_project_entries_includes_directories_and_files_sorted(tmp_path: Path) -> None:
    _seed_python_tree(tmp_path)

    entries = list(iter_project_entries(tmp_path))
    relative = [entry.relative_path for entry in entries]

    assert "src" in relative
    assert "src/app.py" in relative
    assert any(entry.is_directory for entry in entries if entry.relative_path == "src")
    assert any(not entry.is_directory for entry in entries if entry.relative_path == "src/app.py")


def test_iter_project_entries_includes_cbcs_meta_dir_for_full_tree(tmp_path: Path) -> None:
    _seed_python_tree(tmp_path)

    entries = list(iter_project_entries(tmp_path))
    relative = {entry.relative_path for entry in entries}

    assert "cbcs" in relative
    assert "cbcs/project.json" in relative


def test_iter_python_files_default_does_not_follow_symlinked_directories(tmp_path: Path) -> None:
    _seed_python_tree(tmp_path)
    target = tmp_path.parent / "outside_target"
    target.mkdir(exist_ok=True)
    (target / "outside.py").write_text("# outside\n", encoding="utf-8")
    link = tmp_path / "src" / "linked"
    try:
        link.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation unsupported in this environment")

    relative = sorted(p.relative_to(tmp_path).as_posix() for p in iter_python_files(tmp_path))

    assert all(not rel.startswith("src/linked") for rel in relative)
