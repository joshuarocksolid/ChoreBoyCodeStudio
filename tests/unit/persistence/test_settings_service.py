"""Unit tests for scope-aware settings service helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core import constants
from app.persistence.settings_service import SettingsService

pytestmark = pytest.mark.unit


def test_settings_service_load_and_save_global_payload(tmp_path: Path) -> None:
    service = SettingsService(state_root=tmp_path / "state")
    payload = {
        "schema_version": 1,
        constants.UI_EDITOR_SETTINGS_KEY: {
            constants.UI_EDITOR_TAB_WIDTH_KEY: 6,
        },
    }

    service.save_global(payload)
    loaded = service.load_global(force_refresh=True)

    assert loaded == payload


def test_settings_service_load_and_save_project_payload(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True)
    service = SettingsService(state_root=tmp_path / "state")
    payload = {
        "schema_version": 1,
        constants.UI_OUTPUT_SETTINGS_KEY: {
            constants.UI_OUTPUT_AUTO_OPEN_CONSOLE_ON_RUN_OUTPUT_KEY: False,
        },
        constants.UI_THEME_SETTINGS_KEY: {
            constants.UI_THEME_MODE_KEY: constants.UI_THEME_MODE_DARK,
        },
    }

    service.save_project(project_root, payload)
    loaded = service.load_project(project_root, force_refresh=True)

    assert loaded == {
        "schema_version": 1,
        constants.UI_OUTPUT_SETTINGS_KEY: {
            constants.UI_OUTPUT_AUTO_OPEN_CONSOLE_ON_RUN_OUTPUT_KEY: False,
        },
    }


def test_settings_service_load_effective_merges_global_and_project(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True)
    service = SettingsService(state_root=tmp_path / "state")
    service.save_global(
        {
            "schema_version": 1,
            constants.UI_EDITOR_SETTINGS_KEY: {
                constants.UI_EDITOR_TAB_WIDTH_KEY: 4,
                constants.UI_EDITOR_FONT_SIZE_KEY: 12,
            },
        }
    )
    service.save_project(
        project_root,
        {
            "schema_version": 1,
            constants.UI_EDITOR_SETTINGS_KEY: {
                constants.UI_EDITOR_TAB_WIDTH_KEY: 2,
            },
        },
    )

    effective = service.load_effective(project_root=project_root, force_refresh=True)

    assert effective[constants.UI_EDITOR_SETTINGS_KEY][constants.UI_EDITOR_TAB_WIDTH_KEY] == 2
    assert effective[constants.UI_EDITOR_SETTINGS_KEY][constants.UI_EDITOR_FONT_SIZE_KEY] == 12
