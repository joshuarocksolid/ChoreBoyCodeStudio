"""Unit tests for MainWindow syntax override loading contract."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.core import constants
from app.shell.shell_theme_workflow import ShellThemeWorkflow
from app.shell.syntax_color_preferences import THEME_HC_LIGHT, parse_syntax_color_overrides
from app.shell.theme_tokens import apply_syntax_token_overrides, tokens_from_palette

pytestmark = pytest.mark.unit


def test_load_syntax_color_overrides_includes_high_contrast_scopes() -> None:
    settings = MagicMock()
    settings.load_global.return_value = {
        constants.UI_SYNTAX_COLORS_SETTINGS_KEY: {
            constants.UI_SYNTAX_COLORS_HIGH_CONTRAST_LIGHT_KEY: {"keyword": "#000080"},
        }
    }

    overrides = ShellThemeWorkflow.load_syntax_color_overrides(settings)

    assert overrides[THEME_HC_LIGHT]["keyword"] == "#000080"


def test_resolve_theme_tokens_applies_high_contrast_syntax_overrides() -> None:
    payload = {
        constants.UI_SYNTAX_COLORS_SETTINGS_KEY: {
            constants.UI_SYNTAX_COLORS_HIGH_CONTRAST_LIGHT_KEY: {"keyword": "#000080"},
        }
    }
    overrides = parse_syntax_color_overrides(payload)
    base_tokens = tokens_from_palette(
        MagicMock(),
        force_mode=constants.UI_THEME_MODE_HIGH_CONTRAST_LIGHT,
    )
    merged = apply_syntax_token_overrides(
        base_tokens,
        overrides[constants.UI_SYNTAX_COLORS_HIGH_CONTRAST_LIGHT_KEY],
    )
    assert merged.syntax_keyword == "#000080"
