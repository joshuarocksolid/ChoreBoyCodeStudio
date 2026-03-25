"""Editor-side preflight helpers for run and packaging workflows."""
from __future__ import annotations

from pathlib import Path

from app.core.models import LoadedProject, RuntimeIssue, WorkflowPreflightResult
from app.packaging.layout import (
    paths_overlap as _paths_overlap,
    resolve_entry_path as _resolve_entry_path,
    sanitize_project_name,
    should_exclude_relative_path as _should_exclude,
)


def build_run_preflight(
    *,
    loaded_project: LoadedProject | None,
    entry_file: str | None = None,
    working_directory: str | None = None,
    config_name: str | None = None,
) -> WorkflowPreflightResult:
    """Return run-target issues that are knowable before launching the runner."""
    issues: list[RuntimeIssue] = []
    if loaded_project is None:
        issues.append(
            RuntimeIssue(
                issue_id="run.no_project",
                workflow="run",
                severity="blocking",
                title="Open a project before running code",
                summary="Run workflows need an open project so the entry file and working directory can be resolved.",
                why_it_happened="There is no active project loaded in the editor.",
                next_steps=[
                    "Open an existing project folder.",
                    "Or create a new project from a template before running code.",
                ],
                help_topic="getting_started",
            )
        )
        return WorkflowPreflightResult(
            workflow="run",
            issues=issues,
            summary=_summarize_preflight("run", issues),
        )

    project_root = Path(loaded_project.project_root).expanduser().resolve()
    effective_entry_file = (entry_file or loaded_project.metadata.default_entry).strip()
    effective_working_directory = (
        working_directory
        if working_directory is not None
        else loaded_project.metadata.working_directory
    )
    effective_working_directory = (effective_working_directory or ".").strip() or "."

    resolved_entry, entry_error = _resolve_entry_path(root=project_root, entry_file=effective_entry_file)
    if entry_error is not None:
        issues.append(
            RuntimeIssue(
                issue_id=_run_entry_issue_id(entry_error),
                workflow="run",
                severity="blocking",
                title="Run entry file is not ready",
                summary=entry_error,
                why_it_happened=(
                    "The active run target points to an entry file that cannot be resolved inside the project."
                ),
                next_steps=[
                    "Choose an existing `.py` file inside the project as the entry target.",
                    "Update the project's default entry or named run configuration before retrying.",
                ],
                help_topic="getting_started",
                evidence={
                    "entry_file": effective_entry_file,
                    "config_name": config_name,
                    "project_root": str(project_root),
                },
            )
        )
    elif resolved_entry is not None and not resolved_entry.is_file():
        issues.append(
            RuntimeIssue(
                issue_id="run.entry_not_file",
                workflow="run",
                severity="blocking",
                title="Run entry path is not a file",
                summary="The chosen run entry resolves to something that is not a file.",
                why_it_happened="Run targets must resolve to a `.py` file inside the project.",
                next_steps=[
                    "Select a concrete Python file as the run target.",
                    "Update the run configuration or project default entry before retrying.",
                ],
                help_topic="getting_started",
                evidence={"entry_file": effective_entry_file, "config_name": config_name},
            )
        )

    working_root = Path(effective_working_directory).expanduser()
    resolved_working_directory = (
        working_root.resolve()
        if working_root.is_absolute()
        else (project_root / working_root).resolve()
    )
    try:
        resolved_working_directory.relative_to(project_root)
    except ValueError:
        issues.append(
            RuntimeIssue(
                issue_id="run.working_directory_outside_project",
                workflow="run",
                severity="blocking",
                title="Working directory points outside the project",
                summary="The selected working directory must stay inside the current project folder.",
                why_it_happened=(
                    "Code Studio resolves run targets relative to the project and avoids ambiguous or unsafe external working directories."
                ),
                next_steps=[
                    "Choose a working directory inside the project root.",
                    "Leave the working directory blank to use the project's default location.",
                ],
                help_topic="getting_started",
                evidence={
                    "working_directory": effective_working_directory,
                    "config_name": config_name,
                    "project_root": str(project_root),
                },
            )
        )
    else:
        if not resolved_working_directory.exists():
            issues.append(
                RuntimeIssue(
                    issue_id="run.working_directory_missing",
                    workflow="run",
                    severity="blocking",
                    title="Working directory does not exist",
                    summary="The selected working directory could not be found inside the project.",
                    why_it_happened="The run target points to a working directory that is missing or was renamed.",
                    next_steps=[
                        "Create the directory or choose an existing one.",
                        "Leave the working directory blank to use the project default.",
                    ],
                    help_topic="getting_started",
                    evidence={
                        "working_directory": effective_working_directory,
                        "config_name": config_name,
                    },
                )
            )
        elif not resolved_working_directory.is_dir():
            issues.append(
                RuntimeIssue(
                    issue_id="run.working_directory_not_directory",
                    workflow="run",
                    severity="blocking",
                    title="Working directory is not a folder",
                    summary="The selected working directory resolves to a file instead of a directory.",
                    why_it_happened="Runs need a directory as the process working directory.",
                    next_steps=[
                        "Choose a real directory inside the project.",
                        "Leave the working directory blank to use the project default.",
                    ],
                    help_topic="getting_started",
                    evidence={
                        "working_directory": effective_working_directory,
                        "config_name": config_name,
                    },
                )
            )

    return WorkflowPreflightResult(
        workflow="run",
        issues=issues,
        summary=_summarize_preflight("run", issues),
    )


def build_package_preflight(
    *,
    project_root: str | None,
    project_name: str,
    entry_file: str,
    output_dir: str | None,
) -> WorkflowPreflightResult:
    """Return packaging/export issues that are knowable before packaging."""
    issues: list[RuntimeIssue] = []
    if not project_root:
        issues.append(
            RuntimeIssue(
                issue_id="package.no_project",
                workflow="package",
                severity="blocking",
                title="Open a project before packaging",
                summary="Packaging needs a project root, project name, and entry file to build an exportable bundle.",
                why_it_happened="There is no active project loaded in the editor.",
                next_steps=[
                    "Open a project before using Package Project.",
                ],
                help_topic="packaging_backup",
            )
        )
        return WorkflowPreflightResult(
            workflow="package",
            issues=issues,
            summary=_summarize_preflight("package", issues),
        )

    root = Path(project_root).expanduser().resolve()
    if not root.is_dir():
        issues.append(
            RuntimeIssue(
                issue_id="package.project_root_missing",
                workflow="package",
                severity="blocking",
                title="Project root no longer exists",
                summary="The project folder could not be found when packaging was requested.",
                why_it_happened="The project path is missing or no longer points to a directory.",
                next_steps=[
                    "Reopen the project from its current location.",
                    "Verify that the project folder still exists on disk.",
                ],
                help_topic="packaging_backup",
                evidence={"project_root": project_root},
            )
        )
        return WorkflowPreflightResult(
            workflow="package",
            issues=issues,
            summary=_summarize_preflight("package", issues),
        )

    resolved_entry, entry_error = _resolve_entry_path(root=root, entry_file=entry_file)
    if entry_error is not None:
        issues.append(
            RuntimeIssue(
                issue_id="package.entry_invalid",
                workflow="package",
                severity="blocking",
                title="Packaged entry file is not ready",
                summary=entry_error,
                why_it_happened="Packaging needs a concrete entry file inside the project so the exported launcher can start correctly.",
                next_steps=[
                    "Choose an existing entry file inside the project root.",
                    "Update the project's default entry before packaging again.",
                ],
                help_topic="packaging_backup",
                evidence={"entry_file": entry_file, "project_root": str(root)},
            )
        )
    elif resolved_entry is not None:
        rel_entry = resolved_entry.relative_to(root)
        if _should_exclude(rel_entry):
            issues.append(
                RuntimeIssue(
                    issue_id="package.entry_excluded",
                    workflow="package",
                    severity="blocking",
                    title="Entry file would be excluded from the package",
                    summary="The configured entry file resolves into a path that packaging intentionally excludes.",
                    why_it_happened="Excluded paths like run logs and cache directories are not copied into exported project bundles.",
                    next_steps=[
                        "Choose an entry file from the real project source tree.",
                        "Avoid pointing the packaged entry at files under excluded `cbcs/` subdirectories.",
                    ],
                    help_topic="packaging_backup",
                    evidence={"entry_file": entry_file, "relative_entry": rel_entry.as_posix()},
                )
            )

    if output_dir:
        out = Path(output_dir).expanduser().resolve()
        package_dir = out / sanitize_project_name(project_name)
        if _paths_overlap(package_dir, root):
            issues.append(
                RuntimeIssue(
                    issue_id="package.output_overlaps_project",
                    workflow="package",
                    severity="blocking",
                    title="Package output overlaps the live project",
                    summary="The selected package destination would overlap with the project directory itself.",
                    why_it_happened="Packaging deletes and recreates the destination bundle folder, so overlap would risk clobbering the live project.",
                    next_steps=[
                        "Choose an output folder outside the current project.",
                        "Package to a neutral export/share directory before copying the result elsewhere.",
                    ],
                    help_topic="packaging_backup",
                    evidence={
                        "project_root": str(root),
                        "output_dir": str(out),
                        "package_dir": str(package_dir),
                    },
                )
            )

    return WorkflowPreflightResult(
        workflow="package",
        issues=issues,
        summary=_summarize_preflight("package", issues),
    )


def _run_entry_issue_id(error_text: str) -> str:
    normalized = error_text.lower()
    if "non-empty" in normalized:
        return "run.entry_missing"
    if "inside project root" in normalized:
        return "run.entry_outside_project"
    if "not found" in normalized:
        return "run.entry_not_found"
    return "run.entry_invalid"


def _summarize_preflight(workflow: str, issues: list[RuntimeIssue]) -> str:
    if not issues:
        if workflow == "package":
            return "Package export is ready."
        return "Run target is ready."
    if any(issue.is_blocking for issue in issues):
        if workflow == "package":
            return "Packaging needs attention before export."
        return "Run target needs attention before launch."
    if workflow == "package":
        return "Packaging can continue, but there are warnings to review."
    return "Run can continue, but there are warnings to review."
