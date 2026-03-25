"""Runtime-parity tests for semantic engine boot and filesystem behavior."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.core import constants
from app.intelligence.jedi_runtime import initialize_jedi_runtime
from app.intelligence.refactor_runtime import initialize_refactor_runtime
from app.intelligence.refactor_engine import RopeRefactorEngine

pytestmark = pytest.mark.runtime_parity


def _require_apprun() -> None:
    app_run = Path(constants.APP_RUN_PATH)
    if not app_run.exists():
        pytest.skip(f"AppRun not available at {app_run}; skipping semantic runtime parity tests.")


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
