"""Runtime-parity tests for semantic engine boot and filesystem behavior."""
from __future__ import annotations

from pathlib import Path
import shutil

import pytest

from app.core import constants
from app.intelligence.jedi_runtime import initialize_jedi_runtime
from app.intelligence.refactor_runtime import initialize_refactor_runtime
from app.intelligence.refactor_engine import RopeRefactorEngine
from app.intelligence.semantic_facade import SemanticFacade

pytestmark = pytest.mark.runtime_parity

FIXTURES_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "semantic"


def _require_apprun() -> None:
    app_run = Path(constants.APP_RUN_PATH)
    if not app_run.exists():
        pytest.skip(f"AppRun not available at {app_run}; skipping semantic runtime parity tests.")


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


def _collect_hidden_dirs(root: Path) -> set[str]:
    """Return names of hidden (dot-prefixed) directories under root."""
    hidden: set[str] = set()
    for path in root.rglob("*"):
        if path.is_dir() and path.name.startswith("."):
            hidden.add(path.name)
    return hidden


def test_semantic_runtimes_use_visible_cache_paths_and_no_hidden_project_dirs(tmp_path: Path) -> None:
    _require_apprun()
    state_root = (tmp_path / "state_root").resolve()
    state_root.mkdir(parents=True, exist_ok=True)
    project_root = (tmp_path / "project_root").resolve()
    project_root.mkdir(parents=True, exist_ok=True)
    target_file = project_root / "main.py"
    target_file.write_text("def helper():\n    return 1\nhelper()\n", encoding="utf-8")

    jedi_status = initialize_jedi_runtime(state_root=str(state_root))
    rope_status = initialize_refactor_runtime()
    engine = RopeRefactorEngine()
    plan = engine.plan_rename(
        project_root=str(project_root),
        current_file_path=str(target_file),
        cursor_position=4,
        new_symbol="renamed_helper",
    )

    assert jedi_status.is_available is True
    assert rope_status.is_available is True
    assert ".jedi" not in {path.name for path in project_root.iterdir()}
    assert ".ropeproject" not in {path.name for path in project_root.iterdir()}
    assert "jedi" in Path(jedi_status.cache_directory).parts
    assert not Path(jedi_status.cache_directory).name.startswith(".")
    assert plan is not None


def test_jedi_completion_works_under_apprun_with_cross_file_imports(tmp_path: Path) -> None:
    """Jedi resolves completions for imported module members in AppRun environment."""
    _require_apprun()
    project_root = _copy_fixture(tmp_path, "imported_project")
    facade = _build_facade(tmp_path)
    source = "from lib import helper\nhelper."

    items = facade.complete(
        project_root=str(project_root.resolve()),
        current_file_path=str((project_root / "consumer.py").resolve()),
        source_text=source,
        cursor_position=len(source),
        trigger_is_manual=True,
        min_prefix_chars=0,
        max_results=20,
    )

    assert len(items) > 0
    hidden_dirs = _collect_hidden_dirs(project_root)
    assert not hidden_dirs, f"Hidden directories created in project: {hidden_dirs}"


def test_rope_rename_plan_under_apprun_with_multi_file_project(tmp_path: Path) -> None:
    """Rope produces a multi-file rename plan under AppRun without hidden dirs."""
    _require_apprun()
    project_root = _copy_fixture(tmp_path, "imported_project")
    facade = _build_facade(tmp_path)
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
    assert len(plan.preview_patches) > 0
    hidden_dirs = _collect_hidden_dirs(project_root)
    assert not hidden_dirs, f"Hidden directories created in project: {hidden_dirs}"


def test_semantic_facade_handles_deep_import_chains_under_apprun(tmp_path: Path) -> None:
    """Deep import chain through re-export resolves correctly in AppRun."""
    _require_apprun()
    project_root = _copy_fixture(tmp_path, "deep_import_project")
    facade = _build_facade(tmp_path)
    main_path = (project_root / "main.py").resolve()
    source = main_path.read_text(encoding="utf-8")

    result = facade.lookup_definition(
        project_root=str(project_root.resolve()),
        current_file_path=str(main_path),
        source_text=source,
        cursor_position=source.index("deep_function(42)") + 2,
    )

    assert result.found is True
    target_path = str((project_root / "pkg" / "sub" / "inner.py").resolve())
    assert result.locations[0].file_path == target_path
    hidden_dirs = _collect_hidden_dirs(project_root)
    assert not hidden_dirs, f"Hidden directories created in project: {hidden_dirs}"
