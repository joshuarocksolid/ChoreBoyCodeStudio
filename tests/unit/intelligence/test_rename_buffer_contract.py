"""Regression tests for rename buffer-to-disk consistency (CC-17)."""

from __future__ import annotations

from pathlib import Path
import shutil

import pytest

from app.intelligence.semantic_facade import SemanticFacade

pytestmark = pytest.mark.unit

FIXTURES_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "semantic"


def _copy_fixture(tmp_path: Path, fixture_name: str) -> Path:
    source = FIXTURES_ROOT / fixture_name
    target = tmp_path / fixture_name
    shutil.copytree(source, target)
    return target


def _build_facade(tmp_path: Path) -> SemanticFacade:
    state_root = (tmp_path / "state").resolve()
    state_root.mkdir(parents=True, exist_ok=True)
    cache_db_path = state_root / "symbols.sqlite3"
    return SemanticFacade(cache_db_path=str(cache_db_path), state_root=str(state_root))


def test_plan_rename_fails_closed_when_buffer_differs_from_disk(tmp_path: Path) -> None:
    project_root = _copy_fixture(tmp_path, "imported_project")
    facade = _build_facade(tmp_path)
    lib_path = (project_root / "lib.py").resolve()
    disk_source = lib_path.read_text(encoding="utf-8")
    unsaved_source = f"{disk_source}\n# unsaved edit\n"

    with pytest.raises(ValueError, match="Save file before renaming"):
        facade.plan_rename(
            project_root=str(project_root.resolve()),
            current_file_path=str(lib_path),
            source_text=unsaved_source,
            cursor_position=unsaved_source.index("helper") + 2,
            new_symbol="build_summary",
        )

    assert lib_path.read_text(encoding="utf-8") == disk_source
