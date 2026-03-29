"""Unit tests for run toolbar summary copy (no Qt)."""

from __future__ import annotations

import pytest

from app.project.run_configs import RunConfiguration
from app.shell.run_target_summary import (
    RunTargetSummaryInput,
    RunTargetSummaryShortcutLabels,
    build_run_target_summary,
)

pytestmark = pytest.mark.unit

_SC = RunTargetSummaryShortcutLabels(
    run_file="F5",
    debug_file="Ctrl+F5",
    run_project="Shift+F5",
    debug_project="Ctrl+Shift+F5",
)


def test_no_file_no_project_shows_dashes_and_muted() -> None:
    inp = RunTargetSummaryInput(
        shortcuts=_SC,
        active_file_path=None,
        active_file_basename=None,
        active_is_python=False,
        active_is_dirty=False,
        project_root=None,
        project_default_entry=None,
        project_working_directory=None,
        named_config=None,
    )
    vm = build_run_target_summary(inp)
    assert vm.line1 == "Editor file: —"
    assert vm.line2 == "Project run: open a project"
    assert vm.interactive_muted is True
    assert "No file is open" in vm.tool_tip
    assert "Open a project" in vm.tool_tip
    assert "Debugging uses the same" in vm.tool_tip
    assert "run_configs" in vm.tool_tip
    assert "Run With Configuration" in vm.tool_tip
    assert "not a control" in vm.accessible_description


def test_non_python_active_file() -> None:
    inp = RunTargetSummaryInput(
        shortcuts=_SC,
        active_file_path="/tmp/readme.md",
        active_file_basename="readme.md",
        active_is_python=False,
        active_is_dirty=False,
        project_root="/proj",
        project_default_entry="main.py",
        project_working_directory=".",
        named_config=None,
    )
    vm = build_run_target_summary(inp)
    assert "(not Python)" in vm.line1
    assert "not a Python file" in vm.tool_tip
    assert vm.interactive_muted is False


def test_python_dirty_note_in_tooltip() -> None:
    inp = RunTargetSummaryInput(
        shortcuts=_SC,
        active_file_path="/proj/app/x.py",
        active_file_basename="x.py",
        active_is_python=True,
        active_is_dirty=True,
        project_root="/proj",
        project_default_entry="main.py",
        project_working_directory=None,
        named_config=None,
    )
    vm = build_run_target_summary(inp)
    assert vm.line1 == "Editor file: x.py"
    assert "unsaved changes" in vm.tool_tip


def test_named_config_appears_on_second_line_and_tooltip() -> None:
    cfg = RunConfiguration(
        name="Tool",
        entry_file="tools/t.py",
        argv=["--a"],
        working_directory="tools",
        env_overrides={"APP_ENV": "dev"},
    )
    inp = RunTargetSummaryInput(
        shortcuts=_SC,
        active_file_path="/proj/a.py",
        active_file_basename="a.py",
        active_is_python=True,
        active_is_dirty=False,
        project_root="/proj",
        project_default_entry="main.py",
        project_working_directory=".",
        named_config=cfg,
    )
    vm = build_run_target_summary(inp)
    assert "main.py" in vm.line2
    assert "Tool" in vm.line2
    assert "APP_ENV=dev" in vm.tool_tip
    assert "Saved run setup" in vm.tool_tip


def test_project_without_entry_not_treated_as_has_project_for_strip() -> None:
    inp = RunTargetSummaryInput(
        shortcuts=_SC,
        active_file_path=None,
        active_file_basename=None,
        active_is_python=False,
        active_is_dirty=False,
        project_root="/proj",
        project_default_entry="",
        project_working_directory=".",
        named_config=None,
    )
    vm = build_run_target_summary(inp)
    assert vm.line2 == "Project run: open a project"
    assert vm.interactive_muted is True
