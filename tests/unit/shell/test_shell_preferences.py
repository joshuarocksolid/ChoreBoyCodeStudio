"""Unit tests for shell preferences bundle loading."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.core import constants
from app.shell.settings_models import SETTINGS_SCOPE_PROJECT
from app.shell.shell_preferences import load_shell_preferences_bundle

pytestmark = pytest.mark.unit


def test_load_shell_preferences_bundle_reads_global_and_project_once() -> None:
    settings_service = MagicMock()
    settings_service.load_global.return_value = {
        constants.UI_EDITOR_SETTINGS_KEY: {constants.UI_EDITOR_TAB_WIDTH_KEY: 4},
        constants.UI_THEME_SETTINGS_KEY: {
            constants.UI_THEME_MODE_KEY: constants.UI_THEME_MODE_DARK,
        },
    }
    settings_service.load_project.return_value = {
        "schema_version": 1,
        constants.UI_EDITOR_SETTINGS_KEY: {constants.UI_EDITOR_TAB_WIDTH_KEY: 2},
    }

    bundle = load_shell_preferences_bundle(
        settings_service,
        project_root="/tmp/project",
    )

    settings_service.load_global.assert_called_once()
    settings_service.load_project.assert_called_once_with("/tmp/project")
    assert bundle.effective_editor.tab_width == 2
    assert bundle.theme_mode == constants.UI_THEME_MODE_DARK


def test_load_shell_preferences_bundle_skips_project_read_without_root() -> None:
    settings_service = MagicMock()
    settings_service.load_global.return_value = {}

    load_shell_preferences_bundle(settings_service, project_root=None)

    settings_service.load_project.assert_not_called()
