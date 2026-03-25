"""Runtime-parity tests for bundled workflow plugin host behavior."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core import constants
from app.plugins.runtime_manager import PluginRuntimeManager

pytestmark = pytest.mark.runtime_parity


def _require_apprun() -> None:
    app_run = Path(constants.APP_RUN_PATH)
    if not app_run.exists():
        pytest.skip(f"AppRun not available at {app_run}; skipping plugin runtime parity tests.")


def test_bundled_workflow_plugins_run_through_host_without_hidden_paths(tmp_path: Path) -> None:
    _require_apprun()
    state_root = (tmp_path / "state_root").resolve()
    project_root = (tmp_path / "project_root").resolve()
    state_root.mkdir(parents=True, exist_ok=True)
    project_root.mkdir(parents=True, exist_ok=True)
    (project_root / "test_sample.py").write_text(
        "def test_sample():\n    assert 1 + 1 == 2\n",
        encoding="utf-8",
    )

    manager = PluginRuntimeManager(state_root=str(state_root))
    try:
        format_result = manager.invoke_workflow_query(
            "cbcs.python_tools:formatter",
            {
                "source_text": "value={'alpha':1}\n",
                "file_path": str((project_root / "demo.py").resolve()),
                "project_root": str(project_root),
            },
        )
        assert format_result["status"] in {"formatted", "unchanged"}

        job = manager.start_workflow_job(
            "cbcs.pytest:pytest",
            {"project_root": str(project_root)},
        )
        job_result = manager.wait_for_workflow_job(job, timeout_seconds=30.0)
        assert job_result["return_code"] == 0
    finally:
        manager.stop()

    assert not any(child.name.startswith(".") for child in state_root.iterdir())
    assert not any(child.name.startswith(".") for child in project_root.iterdir())
