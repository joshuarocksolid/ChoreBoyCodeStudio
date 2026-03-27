"""Unit tests for shortcut preference helpers."""

from __future__ import annotations

import pytest

from app.shell.shortcut_preferences import (
    build_effective_shortcut_map,
    close_tab_shortcut_id,
    default_shortcut_map,
    find_shortcut_conflicts,
    parse_shortcut_overrides,
)
from app.shell.shortcut_scope import should_route_designer_mode_shortcut

pytestmark = pytest.mark.unit


def test_default_shortcut_map_contains_known_command_ids() -> None:
    defaults = default_shortcut_map()
    assert defaults["designer.file.new_form"] == "Ctrl+Shift+N"
    assert defaults["shell.action.edit.cut"] == "Ctrl+X"
    assert defaults["shell.action.edit.copy"] == "Ctrl+C"
    assert defaults["shell.action.edit.paste"] == "Ctrl+V"
    assert defaults["designer.layout.horizontal"] == "Ctrl+1"
    assert defaults["designer.layout.vertical"] == "Ctrl+2"
    assert defaults["designer.layout.grid"] == "Ctrl+3"
    assert defaults["designer.layout.break"] == "Ctrl+0"
    assert defaults["designer.layout.align_left"] == ""
    assert defaults["designer.layout.align_hcenter"] == ""
    assert defaults["designer.layout.align_right"] == ""
    assert defaults["designer.layout.align_top"] == ""
    assert defaults["designer.layout.align_vcenter"] == ""
    assert defaults["designer.layout.align_bottom"] == ""
    assert defaults["designer.layout.distribute_horizontal"] == ""
    assert defaults["designer.layout.distribute_vertical"] == ""
    assert defaults["designer.layout.adjust_size"] == "Ctrl+J"
    assert defaults["designer.form.preview"] == "Ctrl+R"
    assert defaults["designer.form.preview.default"] == ""
    assert defaults["designer.form.preview.fusion"] == ""
    assert defaults["designer.form.preview.phone_portrait"] == ""
    assert defaults["designer.form.preview.tablet_portrait"] == ""
    assert defaults["designer.form.check_compat"] == "Ctrl+Shift+R"
    assert defaults["designer.form.add_resource"] == ""
    assert defaults["designer.form.promote_widget"] == ""
    assert defaults["designer.form.format_ui_xml"] == "Ctrl+Alt+Shift+F"
    assert defaults["designer.form.save_component"] == ""
    assert defaults["designer.form.insert_component"] == ""
    assert defaults["designer.form.duplicate_selection"] == "Ctrl+D"
    assert defaults["designer.mode.widget"] == "F3"
    assert defaults["designer.mode.signals_slots"] == "F4"
    assert defaults["designer.mode.buddy"] == "F5"
    assert defaults["designer.mode.tab_order"] == "F6"
    assert defaults["shell.action.run.run"] == "F5"
    assert defaults["shell.action.file.save"] == "Ctrl+S"
    assert defaults[close_tab_shortcut_id()] == "Ctrl+W"


def test_parse_shortcut_overrides_accepts_known_ids_and_discards_unknowns() -> None:
    parsed = parse_shortcut_overrides(
        {
            "keybindings": {
                "overrides": {
                    "shell.action.run.run": " Ctrl+R ",
                    "shell.action.unknown": "Ctrl+1",
                    "shell.action.file.save": 123,
                }
            }
        }
    )
    assert parsed == {"shell.action.run.run": "Ctrl+R"}


def test_build_effective_shortcut_map_applies_override_and_unbinds_empty() -> None:
    effective = build_effective_shortcut_map(
        {
            "shell.action.run.run": "Ctrl+R",
            "shell.action.file.save": "",
        }
    )
    assert effective["shell.action.run.run"] == "Ctrl+R"
    assert "shell.action.file.save" not in effective


def test_find_shortcut_conflicts_groups_action_ids_by_shortcut() -> None:
    conflicts = find_shortcut_conflicts(
        {
            "shell.action.run.run": "Ctrl+R",
            "shell.action.file.save": "Ctrl+R",
            "shell.action.file.openProject": "Ctrl+O",
        }
    )
    assert conflicts == {"Ctrl+R": ("shell.action.file.save", "shell.action.run.run")}


def test_should_route_designer_mode_shortcut_only_when_designer_tab_active() -> None:
    from app.shell import shortcut_scope as shortcut_scope_module

    class _Tabs:
        def __init__(self, current_widget: object | None) -> None:
            self._current_widget = current_widget

        def currentWidget(self) -> object | None:  # noqa: N802 - Qt-style
            return self._current_widget

    class _MainWindow:
        def __init__(self, current_widget: object | None) -> None:
            self._editor_tabs_widget = _Tabs(current_widget)

    sentinel = object()
    outsider = object()
    original_is_designer = shortcut_scope_module._is_designer_surface_instance
    original_focus_widget = shortcut_scope_module._focus_widget
    original_within = shortcut_scope_module._is_widget_within_container
    try:
        shortcut_scope_module._is_designer_surface_instance = lambda widget: widget is sentinel  # type: ignore[assignment]
        shortcut_scope_module._focus_widget = lambda: sentinel  # type: ignore[assignment]
        shortcut_scope_module._is_widget_within_container = lambda widget, container: widget is sentinel and container is sentinel  # type: ignore[assignment]
        assert should_route_designer_mode_shortcut(main_window=_MainWindow(current_widget=object())) is False
        assert should_route_designer_mode_shortcut(main_window=_MainWindow(current_widget=None)) is False
        assert should_route_designer_mode_shortcut(main_window=_MainWindow(current_widget=sentinel)) is True
        shortcut_scope_module._focus_widget = lambda: outsider  # type: ignore[assignment]
        assert should_route_designer_mode_shortcut(main_window=_MainWindow(current_widget=sentinel)) is False
    finally:
        shortcut_scope_module._is_designer_surface_instance = original_is_designer  # type: ignore[assignment]
        shortcut_scope_module._focus_widget = original_focus_widget  # type: ignore[assignment]
        shortcut_scope_module._is_widget_within_container = original_within  # type: ignore[assignment]
