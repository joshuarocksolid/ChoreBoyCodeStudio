"""Runtime-parity checks for runtime explanation probes under AppRun."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.bootstrap.capability_probe import (
    APP_RUN_PRESENCE_CHECK_ID,
    FREECAD_IMPORT_CHECK_ID,
    GLOBAL_LOGS_WRITABLE_CHECK_ID,
    PYSIDE2_IMPORT_CHECK_ID,
    STATE_ROOT_WRITABLE_CHECK_ID,
    TEMP_ROOT_WRITABLE_CHECK_ID,
    run_startup_capability_probe,
)
from app.bootstrap.runtime_module_probe import probe_runtime_modules, save_runtime_modules_cache
from app.core import constants
from app.intelligence.runtime_import_probe import clear_runtime_import_probe_cache, probe_runtime_module_importability

pytestmark = pytest.mark.runtime_parity


def _require_apprun() -> str:
    app_run = Path(constants.APP_RUN_PATH)
    if not app_run.exists():
        pytest.skip(f"AppRun not available at {app_run}; skipping runtime explanation parity tests.")
    if not os.access(str(app_run), os.X_OK):
        pytest.skip(f"AppRun exists but is not executable at {app_run}; skipping runtime explanation parity tests.")
    return str(app_run.resolve())


def test_startup_capability_probe_matches_apprun_runtime_expectations(tmp_path: Path) -> None:
    runtime_executable = _require_apprun()
    state_root = (tmp_path / "state_root").resolve()
    temp_root = (tmp_path / "temp_root").resolve()
    report = run_startup_capability_probe(
        state_root=str(state_root),
        temp_root=str(temp_root),
        app_run_path=runtime_executable,
    )
    checks_by_id = {check.check_id: check for check in report.checks}

    assert checks_by_id[APP_RUN_PRESENCE_CHECK_ID].is_available is True
    assert checks_by_id[PYSIDE2_IMPORT_CHECK_ID].is_available is True
    assert checks_by_id[FREECAD_IMPORT_CHECK_ID].is_available is True
    assert checks_by_id[STATE_ROOT_WRITABLE_CHECK_ID].is_available is True
    assert checks_by_id[GLOBAL_LOGS_WRITABLE_CHECK_ID].is_available is True
    assert checks_by_id[TEMP_ROOT_WRITABLE_CHECK_ID].is_available is True


def test_runtime_module_probe_and_cache_use_visible_paths(tmp_path: Path) -> None:
    runtime_executable = _require_apprun()
    state_root = (tmp_path / "state_root").resolve()

    result = probe_runtime_modules(runtime_executable)
    assert result.success is True, result.error_message
    assert "json" in result.modules

    cache_path = save_runtime_modules_cache(result, state_root=str(state_root))
    relative_parts = cache_path.relative_to(state_root).parts

    assert cache_path.name == "runtime_modules.json"
    assert not any(part.startswith(".") for part in relative_parts)


def test_runtime_import_probe_reports_real_import_success_and_failure() -> None:
    runtime_executable = _require_apprun()
    clear_runtime_import_probe_cache()

    available_result = probe_runtime_module_importability("json", runtime_path=runtime_executable)
    missing_result = probe_runtime_module_importability(
        "totally_missing_runtime_probe_module",
        runtime_path=runtime_executable,
    )

    assert available_result.is_importable is True
    assert available_result.runtime_path == runtime_executable
    assert missing_result.is_importable is False
    assert missing_result.failure_reason == "import_error"
    assert missing_result.module_name == "totally_missing_runtime_probe_module"
