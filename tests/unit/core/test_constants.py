"""Unit tests for core path/bootstrap constants."""

import pytest

from app.core import constants

pytestmark = pytest.mark.unit


def test_global_state_constant_values() -> None:
    """Global state naming stays stable for downstream path contracts."""
    assert constants.APP_RUN_PATH == "/opt/freecad/AppRun"
    assert constants.GLOBAL_STATE_DIRNAME == ".choreboy_code_studio"
    assert constants.GLOBAL_SETTINGS_FILENAME == "settings.json"
    assert constants.GLOBAL_RECENT_PROJECTS_FILENAME == "recent_projects.json"
    assert constants.GLOBAL_LOGS_DIRNAME == "logs"
    assert constants.GLOBAL_CACHE_DIRNAME == "cache"
    assert constants.GLOBAL_CRASH_REPORTS_DIRNAME == "crash_reports"
    assert constants.GLOBAL_STATE_DB_FILENAME == "state.sqlite3"
    assert constants.APP_LOG_FILENAME == "app.log"


def test_project_structure_constant_values() -> None:
    """Project-local path names must match architecture docs."""
    assert constants.PROJECT_META_DIRNAME == ".cbcs"
    assert constants.PROJECT_MANIFEST_FILENAME == "project.json"
    assert constants.PROJECT_RUNS_DIRNAME == "runs"
    assert constants.PROJECT_CACHE_DIRNAME == "cache"
    assert constants.PROJECT_LOGS_DIRNAME == "logs"


def test_temp_namespace_constant_is_stable() -> None:
    """Temp namespace keeps app temp files grouped together."""
    assert constants.TEMP_NAMESPACE_DIRNAME == "choreboy_code_studio"
