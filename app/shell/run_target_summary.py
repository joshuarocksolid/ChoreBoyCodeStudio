"""Pure helpers for the run toolbar summary (copy + tooltip + accessibility text)."""

from __future__ import annotations

from dataclasses import dataclass

from app.project.run_configs import RunConfiguration, env_overrides_to_text


@dataclass(frozen=True)
class RunTargetSummaryShortcutLabels:
    """Display strings for current keyboard shortcuts (from menus / overrides)."""

    run_file: str
    debug_file: str
    run_project: str
    debug_project: str


@dataclass(frozen=True)
class RunTargetSummaryInput:
    """Gathers everything needed to render the run summary (no Qt)."""

    shortcuts: RunTargetSummaryShortcutLabels
    active_file_path: str | None
    active_file_basename: str | None
    active_is_python: bool
    active_is_dirty: bool
    project_root: str | None
    project_default_entry: str | None
    project_working_directory: str | None
    named_config: RunConfiguration | None


@dataclass(frozen=True)
class RunTargetSummaryViewModel:
    """Strings consumed by RunTargetSummaryPanel."""

    line1: str
    line2: str
    tool_tip: str
    accessible_name: str
    accessible_description: str
    interactive_muted: bool


def build_run_target_summary(inp: RunTargetSummaryInput) -> RunTargetSummaryViewModel:
    """Build toolbar lines, tooltip, and accessibility strings."""
    sc = inp.shortcuts
    has_project = inp.project_root is not None and bool((inp.project_default_entry or "").strip())

    line1 = _strip_line_editor_file(
        active_file_path=inp.active_file_path,
        active_file_basename=inp.active_file_basename,
        active_is_python=inp.active_is_python,
    )
    line2 = _strip_line_project_run(
        has_project=has_project,
        default_entry=(inp.project_default_entry or "").strip() or None,
        named_config=inp.named_config,
    )

    active_section = _tooltip_active_file_section(inp, sc)
    project_section = _tooltip_project_section(inp)
    setup_section = _tooltip_saved_setup_section(inp)
    debug_section = (
        "Debug\n"
        "Debugging uses the same editor file and project entry as Run.\n"
        f"Shortcuts: Run file ({sc.run_file}), Debug file ({sc.debug_file}), "
        f"Run project ({sc.run_project}), Debug project ({sc.debug_project})."
    )
    footer = (
        "Named run setups live in the project file (run_configs). "
        "Use Run > Run With Configuration... to select one when defined."
    )

    tool_tip = "\n\n".join([active_section, project_section, setup_section, debug_section, footer])

    a11y_name = f"Run summary: {line1}. {line2}."
    a11y_desc = (
        f"{line1} {line2}. "
        "This panel summarizes the run target; it is not a control. "
        f"{footer} "
        "When no project is open, open a project first from the File menu."
    )

    return RunTargetSummaryViewModel(
        line1=line1,
        line2=line2,
        tool_tip=tool_tip,
        accessible_name=a11y_name,
        accessible_description=a11y_desc,
        interactive_muted=not has_project,
    )


def _strip_line_editor_file(
    *,
    active_file_path: str | None,
    active_file_basename: str | None,
    active_is_python: bool,
) -> str:
    label = "Editor file"
    if not active_file_path or not active_file_basename:
        return f"{label}: —"
    if not active_is_python:
        return f"{label}: {active_file_basename} (not Python)"
    return f"{label}: {active_file_basename}"


def _strip_line_project_run(
    *,
    has_project: bool,
    default_entry: str | None,
    named_config: RunConfiguration | None,
) -> str:
    label = "Project run"
    if not has_project or not default_entry:
        return f"{label}: open a project"
    setup = named_config.name if named_config is not None else "project default"
    return f"{label}: {default_entry} · {setup}"


def _tooltip_active_file_section(inp: RunTargetSummaryInput, sc: RunTargetSummaryShortcutLabels) -> str:
    head = f"Editor file (Run {sc.run_file} / Debug {sc.debug_file})"
    if inp.active_file_path is None or not inp.active_file_basename:
        return (
            f"{head}\n"
            f"No file is open. Open a Python file to run or debug the active editor tab."
        )
    detail = inp.active_file_path
    if inp.active_is_dirty:
        detail += " (unsaved changes run via a temporary copy)"
    if not inp.active_is_python:
        return (
            f"{head}\n"
            f"{detail}\n"
            "This tab is not a Python file. Open a .py file to use Run / Debug for the editor."
        )
    return f"{head}\n{detail}"


def _tooltip_project_section(inp: RunTargetSummaryInput) -> str:
    head = "Project run (Run Project / Debug Project)"
    if inp.project_root is None:
        return f"{head}\nOpen a project to run or debug the project entry script."
    entry = (inp.project_default_entry or "").strip()
    if not entry:
        return f"{head}\nProject is open but no default entry is configured."
    cwd = inp.project_working_directory or "."
    return (
        f"{head}\n"
        f"Project root: {inp.project_root}\n"
        f"Default entry: {entry}\n"
        f"Working directory: {cwd}"
    )


def _tooltip_saved_setup_section(inp: RunTargetSummaryInput) -> str:
    head = "Saved run setup"
    cfg = inp.named_config
    if cfg is None:
        return (
            f"{head}\n"
            "No named setup is selected. "
            "Run Project uses the project default entry above. "
            "Choose a named setup from the Run menu if you created one."
        )
    env_text = env_overrides_to_text(cfg.env_overrides) or "(none)"
    return (
        f"{head}\n"
        f"Name: {cfg.name}\n"
        f"Entry: {cfg.entry_file}\n"
        f"Working directory: {cfg.working_directory or '.'}\n"
        f"Env overrides: {env_text}"
    )
