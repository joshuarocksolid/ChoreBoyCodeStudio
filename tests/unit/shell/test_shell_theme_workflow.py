"""Unit tests for shell theme workflow orchestration."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.core import constants  # noqa: E402
from app.shell.shell_theme_workflow import (  # noqa: E402
    ExplorerThemeHost,
    ExplorerThemeSink,
    ShellThemeChildCallbacks,
    ShellThemeWorkflow,
    ShellThemeWorkflowHost,
)
from app.shell.syntax_color_preferences import THEME_HC_LIGHT, parse_syntax_color_overrides  # noqa: E402
from app.shell.theme_tokens import ShellThemeTokens, tokens_from_palette  # noqa: E402

pytestmark = pytest.mark.unit


def _make_palette(lightness: int = 240) -> MagicMock:
    palette = MagicMock()
    window_color = MagicMock()
    window_color.lightness.return_value = lightness
    palette.color.return_value = window_color
    return palette


@dataclass
class RecordingChildCallbacks:
    style_sheets: list[str] = field(default_factory=list)
    tooltip_style_sheets: list[str] = field(default_factory=list)
    editor_tokens: list[ShellThemeTokens] = field(default_factory=list)
    markdown_tokens: list[ShellThemeTokens] = field(default_factory=list)
    console_tokens: list[ShellThemeTokens] = field(default_factory=list)
    run_log_tokens: list[ShellThemeTokens] = field(default_factory=list)
    search_tokens: list[ShellThemeTokens] = field(default_factory=list)
    activity_bar_tokens: list[ShellThemeTokens] = field(default_factory=list)
    test_explorer_tokens: list[ShellThemeTokens] = field(default_factory=list)
    outline_tokens: list[ShellThemeTokens] = field(default_factory=list)

    def as_shell_callbacks(self) -> ShellThemeChildCallbacks:
        return ShellThemeChildCallbacks(
            set_shell_style_sheet=self.style_sheets.append,
            set_app_tooltip_style_sheet=self.tooltip_style_sheets.append,
            apply_editor_themes=self.editor_tokens.append,
            apply_markdown_themes=self.markdown_tokens.append,
            apply_python_console_theme=self.console_tokens.append,
            apply_run_log_theme=self.run_log_tokens.append,
            apply_search_sidebar_theme=self.search_tokens.append,
            apply_activity_bar_view_icons=self.activity_bar_tokens.append,
            apply_test_explorer_theme=self.test_explorer_tokens.append,
            apply_outline_theme=self.outline_tokens.append,
        )


class FakeExplorerButton:
    def __init__(self) -> None:
        self.icon: object | None = None

    def setIcon(self, icon: object) -> None:
        self.icon = icon


def _build_host(
    *,
    theme_mode: str = constants.UI_THEME_MODE_LIGHT,
    ui_font_weight: str = constants.UI_THEME_FONT_WEIGHT_DEFAULT,
    dark_chrome_palette: str = constants.UI_THEME_DARK_CHROME_PALETTE_DEFAULT,
    syntax_color_overrides: dict[str, dict[str, str]] | None = None,
    recording: RecordingChildCallbacks | None = None,
    explorer: ExplorerThemeHost | None = None,
    system_dark_theme_preference: bool | None = None,
) -> ShellThemeWorkflowHost:
    recording = recording or RecordingChildCallbacks()
    return ShellThemeWorkflowHost(
        palette_accessor=lambda: _make_palette(),
        theme_mode=theme_mode,
        ui_font_weight=ui_font_weight,
        dark_chrome_palette=dark_chrome_palette,
        syntax_color_overrides=syntax_color_overrides or {},
        child_callbacks=recording.as_shell_callbacks(),
        explorer=explorer,
        system_dark_theme_preference=system_dark_theme_preference,
    )


class TestLoadSettings:
    def test_load_syntax_color_overrides_includes_high_contrast_scopes(self) -> None:
        settings = MagicMock()
        settings.load_global.return_value = {
            constants.UI_SYNTAX_COLORS_SETTINGS_KEY: {
                constants.UI_SYNTAX_COLORS_HIGH_CONTRAST_LIGHT_KEY: {"keyword": "#000080"},
            }
        }

        overrides = ShellThemeWorkflow.load_syntax_color_overrides(settings)

        assert overrides[THEME_HC_LIGHT]["keyword"] == "#000080"

    def test_load_theme_mode_from_editor_snapshot(self) -> None:
        settings = MagicMock()
        settings.load_global.return_value = {
            constants.UI_THEME_SETTINGS_KEY: {constants.UI_THEME_MODE_KEY: "dark"},
        }

        assert ShellThemeWorkflow.load_theme_mode(settings) == "dark"

    def test_load_ui_font_weight_from_editor_snapshot(self) -> None:
        settings = MagicMock()
        settings.load_global.return_value = {
            constants.UI_THEME_SETTINGS_KEY: {
                constants.UI_THEME_FONT_WEIGHT_KEY: "bold",
            },
        }

        assert ShellThemeWorkflow.load_ui_font_weight(settings) == "bold"

    def test_load_dark_chrome_palette_from_editor_snapshot(self) -> None:
        settings = MagicMock()
        settings.load_global.return_value = {
            constants.UI_THEME_SETTINGS_KEY: {
                constants.UI_THEME_DARK_CHROME_PALETTE_KEY: (
                    constants.UI_THEME_DARK_CHROME_PALETTE_NEUTRAL_GRAY
                ),
            },
        }

        assert (
            ShellThemeWorkflow.load_dark_chrome_palette(settings)
            == constants.UI_THEME_DARK_CHROME_PALETTE_NEUTRAL_GRAY
        )


class TestResolveThemeTokens:
    def test_resolve_theme_tokens_uses_neutral_dark_chrome_palette(self) -> None:
        host = _build_host(
            theme_mode=constants.UI_THEME_MODE_DARK,
            dark_chrome_palette=constants.UI_THEME_DARK_CHROME_PALETTE_NEUTRAL_GRAY,
        )
        workflow = ShellThemeWorkflow(host)

        tokens = workflow.resolve_theme_tokens()

        assert tokens.panel_bg == "#303030"

    def test_applies_high_contrast_syntax_overrides(self) -> None:
        payload = {
            constants.UI_SYNTAX_COLORS_SETTINGS_KEY: {
                constants.UI_SYNTAX_COLORS_HIGH_CONTRAST_LIGHT_KEY: {"keyword": "#000080"},
            }
        }
        overrides = parse_syntax_color_overrides(payload)
        host = _build_host(
            theme_mode=constants.UI_THEME_MODE_HIGH_CONTRAST_LIGHT,
            syntax_color_overrides=overrides,
        )
        workflow = ShellThemeWorkflow(host)

        tokens = workflow.resolve_theme_tokens()

        assert tokens.syntax_keyword == "#000080"

    def test_system_mode_uses_cached_dark_preference(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[list[str]] = []

        def fake_run(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
            calls.append(command)
            return subprocess.CompletedProcess(args=command, returncode=0, stdout="'prefer-dark'\n", stderr="")

        monkeypatch.setattr("app.shell.shell_theme_workflow.subprocess.run", fake_run)
        host = _build_host(theme_mode=constants.UI_THEME_MODE_SYSTEM)
        workflow = ShellThemeWorkflow(host)

        first = workflow.resolve_theme_tokens()
        second = workflow.resolve_theme_tokens()

        assert first.is_dark is True
        assert second.is_dark is True
        assert len(calls) == 1


@pytest.mark.usefixtures("qapp")
class TestApplyThemeStyles:
    def test_applies_child_callbacks_in_order(self) -> None:
        recording = RecordingChildCallbacks()
        host = _build_host(recording=recording)
        workflow = ShellThemeWorkflow(host)

        workflow.apply_theme_styles()

        assert len(recording.style_sheets) == 1
        assert recording.style_sheets[0]
        assert len(recording.tooltip_style_sheets) == 1
        assert recording.tooltip_style_sheets[0]
        assert len(recording.editor_tokens) == 1
        assert len(recording.markdown_tokens) == 1
        assert len(recording.console_tokens) == 1
        assert len(recording.run_log_tokens) == 1
        assert len(recording.search_tokens) == 1
        assert len(recording.activity_bar_tokens) == 1
        assert len(recording.test_explorer_tokens) == 1
        assert len(recording.outline_tokens) == 1
        assert recording.editor_tokens[0] is recording.markdown_tokens[0]

    def test_reentrancy_guard_skips_nested_apply(self) -> None:
        recording = RecordingChildCallbacks()
        host = _build_host(recording=recording)
        workflow = ShellThemeWorkflow(host)
        host.is_applying_theme_styles = True

        workflow.apply_theme_styles()

        assert recording.style_sheets == []
        assert recording.tooltip_style_sheets == []

    def test_tab_close_icon_paths_are_set_on_tokens(self) -> None:
        recording = RecordingChildCallbacks()
        host = _build_host(recording=recording)
        workflow = ShellThemeWorkflow(host)

        workflow.apply_theme_styles()

        tokens = recording.editor_tokens[0]
        assert tokens.tab_close_icon_path
        assert tokens.tab_close_icon_hover_path

    def test_emits_theme_aware_tooltip_stylesheet_for_dark_mode(self) -> None:
        recording = RecordingChildCallbacks()
        host = _build_host(
            recording=recording,
            theme_mode=constants.UI_THEME_MODE_DARK,
        )
        workflow = ShellThemeWorkflow(host)

        workflow.apply_theme_styles()

        tooltip_qss = recording.tooltip_style_sheets[0]
        tokens = recording.editor_tokens[0]
        assert "QToolTip" in tooltip_qss
        assert tokens.popup_bg in tooltip_qss
        assert tokens.text_primary in tooltip_qss
        assert tokens.popup_border in tooltip_qss or tokens.border in tooltip_qss


@pytest.mark.usefixtures("qapp")
class TestApplyExplorerTheme:
    def test_updates_sink_and_buttons_without_tree_repopulate(self) -> None:
        sink = ExplorerThemeSink()
        new_file_btn = FakeExplorerButton()
        new_folder_btn = FakeExplorerButton()
        refresh_btn = FakeExplorerButton()
        populate_calls: list[str] = []

        explorer = ExplorerThemeHost(
            sink=sink,
            explorer_new_file_btn=new_file_btn,
            explorer_new_folder_btn=new_folder_btn,
            explorer_refresh_btn=refresh_btn,
            loaded_project=object(),
            populate_project_tree=lambda: populate_calls.append("refresh"),
        )
        host = _build_host(explorer=explorer)
        workflow = ShellThemeWorkflow(host)
        tokens = tokens_from_palette(_make_palette(), force_mode="light")

        workflow.apply_explorer_theme(tokens)

        assert sink.tree_file_icon is not None
        assert sink.tree_file_icon_map
        assert sink.tree_filename_icon_map
        assert sink.tree_folder_icon is not None
        assert sink.tree_folder_open_icon is not None
        assert sink.tree_entrypoint_icon is not None
        assert new_file_btn.icon is not None
        assert new_folder_btn.icon is not None
        assert refresh_btn.icon is not None
        assert populate_calls == []

    def test_skips_tree_refresh_without_loaded_project(self) -> None:
        populate_calls: list[str] = []
        explorer = ExplorerThemeHost(
            sink=ExplorerThemeSink(),
            populate_project_tree=lambda: populate_calls.append("refresh"),
        )
        host = _build_host(explorer=explorer)
        workflow = ShellThemeWorkflow(host)

        workflow.apply_explorer_theme(tokens_from_palette(_make_palette(), force_mode="light"))

        assert populate_calls == []


class TestSystemDarkThemePreference:
    def test_handles_subprocess_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def fake_run(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(args=command, returncode=1, stdout="", stderr="boom")

        monkeypatch.setattr("app.shell.shell_theme_workflow.subprocess.run", fake_run)
        host = _build_host()
        workflow = ShellThemeWorkflow(host)

        assert workflow.system_prefers_dark_theme() is False
        assert host.system_dark_theme_preference is False

    def test_invalidate_clears_cache(self) -> None:
        host = _build_host(system_dark_theme_preference=True)
        workflow = ShellThemeWorkflow(host)

        workflow.invalidate_system_dark_theme_preference()

        assert host.system_dark_theme_preference is None
