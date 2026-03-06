"""Unit tests for core path/bootstrap constants."""

import pytest

from app.core import constants

pytestmark = pytest.mark.unit


def test_global_state_constant_values() -> None:
    """Global state naming stays stable for downstream path contracts."""
    assert constants.APP_RUN_PATH == "/opt/freecad/AppRun"
    assert constants.GLOBAL_STATE_DIRNAME == "choreboy_code_studio_state"
    assert constants.GLOBAL_SETTINGS_FILENAME == "settings.json"
    assert constants.GLOBAL_RECENT_PROJECTS_FILENAME == "recent_projects.json"
    assert constants.GLOBAL_LOGS_DIRNAME == "logs"
    assert constants.GLOBAL_CACHE_DIRNAME == "cache"
    assert constants.GLOBAL_CRASH_REPORTS_DIRNAME == "crash_reports"
    assert constants.GLOBAL_STATE_DB_FILENAME == "state.sqlite3"
    assert constants.APP_LOG_FILENAME == "app.log"
    assert constants.APP_LOGGER_NAMESPACE == "choreboy_code_studio"
    assert constants.APP_LOG_FORMAT == "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    assert constants.APP_LOG_DATE_FORMAT == "%Y-%m-%d %H:%M:%S"


def test_project_structure_constant_values() -> None:
    """Project-local path names must match architecture docs."""
    assert constants.PROJECT_META_DIRNAME == "cbcs"
    assert constants.PROJECT_MANIFEST_FILENAME == "project.json"
    assert constants.PROJECT_SETTINGS_FILENAME == "settings.json"
    assert constants.PROJECT_RUNS_DIRNAME == "runs"
    assert constants.PROJECT_CACHE_DIRNAME == "cache"
    assert constants.PROJECT_SETTINGS_OVERRIDABLE_ROOT_KEYS == (
        constants.UI_EDITOR_SETTINGS_KEY,
        constants.UI_INTELLIGENCE_SETTINGS_KEY,
        constants.UI_LINTER_SETTINGS_KEY,
        constants.UI_FILE_EXCLUDES_SETTINGS_KEY,
        constants.UI_OUTPUT_SETTINGS_KEY,
    )
    assert constants.RUN_MANIFEST_FILENAME_PREFIX == "run_manifest_"
    assert constants.RUN_ID_TIMESTAMP_FORMAT == "%Y%m%d_%H%M%S"
    assert constants.RUN_MANIFEST_VERSION == 1
    assert constants.RUN_EXIT_SUCCESS == 0
    assert constants.RUN_EXIT_USER_CODE_ERROR == 1
    assert constants.RUN_EXIT_BOOTSTRAP_ERROR == 2
    assert constants.RUN_EXIT_INVALID_MANIFEST == 3
    assert constants.RUN_EXIT_TERMINATED_BY_USER == 130


def test_temp_namespace_constant_is_stable() -> None:
    """Temp namespace keeps app temp files grouped together."""
    assert constants.TEMP_NAMESPACE_DIRNAME == "choreboy_code_studio"
