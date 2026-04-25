"""Integration coverage for semantic engines respecting visible project paths."""
from __future__ import annotations

from pathlib import Path
import shutil

import pytest

from app.intelligence.refactor_runtime import initialize_refactor_runtime
from app.intelligence.semantic_facade import SemanticFacade

pytestmark = pytest.mark.integration

FIXTURES_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "semantic"


def _copy_fixture(tmp_path: Path, fixture_name: str) -> Path:
    source = FIXTURES_ROOT / fixture_name
    target = tmp_path / fixture_name
    shutil.copytree(source, target)
    return target


def _collect_hidden_dirs(root: Path) -> set[str]:
    return {path.name for path in root.rglob("*") if path.is_dir() and path.name.startswith(".")}


def test_rope_rename_creates_no_dot_prefixed_project_metadata(tmp_path: Path) -> None:
    status = initialize_refactor_runtime()
    if not status.is_available:
        pytest.skip(status.message)

    project_root = _copy_fixture(tmp_path, "imported_project")
    state_root = (tmp_path / "state").resolve()
    state_root.mkdir(parents=True, exist_ok=True)
    facade = SemanticFacade(
        cache_db_path=str(state_root / "symbols.sqlite3"),
        state_root=str(state_root),
    )
    lib_path = (project_root / "lib.py").resolve()
    source = lib_path.read_text(encoding="utf-8")

    plan = facade.plan_rename(
        project_root=str(project_root.resolve()),
        current_file_path=str(lib_path),
        source_text=source,
        cursor_position=source.index("helper") + 2,
        new_symbol="build_summary",
    )

    assert plan is not None
    hidden_dirs = _collect_hidden_dirs(project_root)
    assert hidden_dirs == set()
