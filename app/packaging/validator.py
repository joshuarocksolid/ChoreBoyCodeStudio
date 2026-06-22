"""Packaging validation and preflight orchestration."""

from __future__ import annotations

from pathlib import Path

from app.bootstrap.paths import project_manifest_path
from app.bootstrap.runtime_module_probe import load_cached_runtime_modules
from app.core.models import RuntimeIssue, RuntimeIssueReport, WorkflowPreflightResult
from app.packaging.dependency_audit import check_manifest_consistency, run_dependency_audit
from app.packaging.layout import is_packaging_excluded_path
from app.packaging.models import (
    DependencyAuditReport,
    PACKAGE_PROFILE_INSTALLABLE,
    PackageValidationReport,
    ProjectPackageConfig,
)
from app.packaging.payload_policy import DEFAULT_PACKAGING_PAYLOAD_POLICY
from app.project.file_excludes import should_exclude_relative_path
from app.project.file_inventory import walk_project
from app.project.project_manifest import load_project_manifest
from app.support.preflight import build_package_preflight
from app.support.runtime_explainer import HELP_TOPIC_PACKAGING

_SEVERITY_ORDER = {
    "blocking": 3,
    "degraded": 2,
    "advisory": 1,
}


def build_package_validation_report(
    *,
    project_root: str,
    package_config: ProjectPackageConfig,
    project_name: str,
    project_default_entry: str,
    output_dir: str,
    profile: str,
    known_runtime_modules: frozenset[str] | None = None,
) -> PackageValidationReport:
    """Build the combined package preflight + dependency audit report."""
    resolved_root = str(Path(project_root).expanduser().resolve())
    effective_entry = package_config.effective_entry_file(project_default_entry=project_default_entry)
    base_preflight = build_package_preflight(
        project_root=project_root,
        project_name=package_config.display_name or project_name,
        entry_file=effective_entry,
        output_dir=output_dir,
    )
    config_issues = validate_package_config(
        project_root=project_root,
        package_config=package_config,
        project_default_entry=project_default_entry,
        profile=profile,
    )
    combined_issues = _sort_issues(list(base_preflight.issues) + config_issues)
    preflight = WorkflowPreflightResult(
        workflow="package",
        issues=combined_issues,
        summary=_summarize_package_preflight(combined_issues),
    )
    if not preflight.is_ready:
        dependency_audit = DependencyAuditReport(
            project_root=resolved_root,
            records=[],
            issues=[],
            summary="Dependency audit skipped because packaging preflight has blocking issues.",
        )
        issue_report = RuntimeIssueReport(
            workflow="package",
            issues=_sort_issues(list(preflight.issues)),
        )
        return PackageValidationReport(
            profile=profile,
            preflight=preflight,
            dependency_audit=dependency_audit,
            issue_report=issue_report,
        )

    effective_runtime_modules = known_runtime_modules or load_cached_runtime_modules()
    dependency_audit = run_dependency_audit(
        project_root=project_root,
        known_runtime_modules=effective_runtime_modules,
        allow_runtime_import_probe=False,
    )
    manifest_issues = check_manifest_consistency(project_root=project_root)
    issue_report = RuntimeIssueReport(
        workflow="package",
        issues=_sort_issues(
            list(preflight.issues) + list(dependency_audit.issues) + manifest_issues
        ),
    )
    return PackageValidationReport(
        profile=profile,
        preflight=preflight,
        dependency_audit=dependency_audit,
        issue_report=issue_report,
    )


def validate_package_config(
    *,
    project_root: str,
    package_config: ProjectPackageConfig,
    project_default_entry: str,
    profile: str,
) -> list[RuntimeIssue]:
    """Return package-config issues that should surface before export."""
    root = Path(project_root).expanduser().resolve()
    issues: list[RuntimeIssue] = []

    if profile != PACKAGE_PROFILE_INSTALLABLE:
        issues.append(
            RuntimeIssue(
                issue_id="package.profile.unsupported",
                workflow="package",
                severity="blocking",
                title="Package profile is no longer supported",
                summary="Only installable packages are supported on ChoreBoy.",
                why_it_happened=(
                    "Real desktop probes showed portable launchers depend on desktop metadata "
                    "that ChoreBoy does not reliably provide."
                ),
                next_steps=[
                    "Export the project using the installable profile.",
                ],
                help_topic=HELP_TOPIC_PACKAGING,
                evidence={"profile": profile},
            )
        )

    effective_entry = package_config.effective_entry_file(project_default_entry=project_default_entry)
    if not effective_entry.strip():
        issues.append(
            RuntimeIssue(
                issue_id="package.config.entry_missing",
                workflow="package",
                severity="blocking",
                title="Package entry file is missing",
                summary="Packaging needs an entry file from the package config or project manifest.",
                why_it_happened="The exporter cannot generate a launcher without knowing which Python file should start the package.",
                next_steps=[
                    "Set default_entry in cbcs/project.json or entry_file in cbcs/package.json.",
                ],
                help_topic=HELP_TOPIC_PACKAGING,
            )
        )

    if package_config.description.strip():
        pass
    else:
        issues.append(
            RuntimeIssue(
                issue_id="package.config.description_missing",
                workflow="package",
                severity="advisory",
                title="Package description is still generic",
                summary="This package has no description yet, so generated README/INSTALL text will be less specific.",
                why_it_happened="Package metadata exists primarily to make exports clearer for the recipient, not just for the source project.",
                next_steps=[
                    "Add a short description in cbcs/package.json before sharing the package widely.",
                ],
                help_topic=HELP_TOPIC_PACKAGING,
            )
        )

    if package_config.icon_path.strip():
        icon_issue = _validate_icon_path(root=root, icon_path=package_config.icon_path)
        if icon_issue is not None:
            issues.append(icon_issue)
    else:
        issues.append(
            RuntimeIssue(
                issue_id="package.config.icon_missing",
                workflow="package",
                severity="advisory",
                title="Package launcher has no custom icon",
                summary="The export will work without an icon, but installable packages look more polished with one.",
                why_it_happened="No icon_path was declared in cbcs/package.json.",
                next_steps=[
                    "Add a project-local `.png` or `.svg` icon path in cbcs/package.json if you want a branded launcher.",
                ],
                help_topic=HELP_TOPIC_PACKAGING,
            )
        )

    hidden_paths = _discover_hidden_paths(root)
    if hidden_paths:
        issues.append(
            RuntimeIssue(
                issue_id="package.project.hidden_paths_present",
                workflow="package",
                severity="degraded",
                title="Project contains hidden files or folders that will not be packaged",
                summary="Dot-prefixed paths were found in the project and are excluded from the exported artifact.",
                why_it_happened="ChoreBoy environments do not reliably expose hidden folders, so packaging treats them as unsupported distribution content.",
                next_steps=[
                    "Move any real project assets out of hidden folders before packaging.",
                    "Keep packaging-relevant content in visible project paths.",
                ],
                help_topic=HELP_TOPIC_PACKAGING,
                evidence={"hidden_paths": hidden_paths[:10]},
            )
        )

    excluded_python = _discover_user_excluded_python_that_ships(root)
    if excluded_python:
        issues.append(
            RuntimeIssue(
                issue_id="package.project.user_excluded_python_will_ship",
                workflow="package",
                severity="degraded",
                title="Some user-excluded Python files will still be packaged",
                summary=(
                    "Project exclude patterns hide these files in the editor tree, "
                    "but packaging still ships them in the exported artifact."
                ),
                why_it_happened=(
                    "Packaging uses its own payload policy and always includes vendor/; "
                    "editor file excludes do not automatically remove files from exports."
                ),
                next_steps=[
                    "Review the listed Python files before sharing the package.",
                    "Move excluded code out of the project or update cbcs/project.json exclude_patterns if export should omit them.",
                ],
                help_topic=HELP_TOPIC_PACKAGING,
                evidence={"python_files": excluded_python[:10]},
            )
        )

    return issues


def resolve_icon_relative_path(
    *,
    project_root: str,
    package_config: ProjectPackageConfig,
) -> str:
    """Return the normalized icon path relative to project root, or empty when unset."""
    root = Path(project_root).expanduser().resolve()
    icon_path = package_config.icon_path.strip()
    if not icon_path:
        return ""
    candidate = Path(icon_path).expanduser()
    resolved = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError:
        return ""


def _validate_icon_path(*, root: Path, icon_path: str) -> RuntimeIssue | None:
    candidate = Path(icon_path).expanduser()
    resolved = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    try:
        relative_path = resolved.relative_to(root)
    except ValueError:
        return RuntimeIssue(
            issue_id="package.config.icon_outside_project",
            workflow="package",
            severity="blocking",
            title="Package icon must live inside the project",
            summary="icon_path points outside the current project root.",
            why_it_happened="Packaging should remain self-contained and not depend on external machine-local assets.",
            next_steps=[
                "Copy the icon into the project folder and reference it with a relative path in cbcs/package.json.",
            ],
            help_topic=HELP_TOPIC_PACKAGING,
            evidence={"icon_path": icon_path},
        )
    if not resolved.exists() or not resolved.is_file():
        return RuntimeIssue(
            issue_id="package.config.icon_missing",
            workflow="package",
            severity="blocking",
            title="Package icon path does not exist",
            summary="icon_path points to a file that could not be found.",
            why_it_happened="The configured launcher icon is missing or was renamed.",
            next_steps=[
                "Fix icon_path in cbcs/package.json or remove it until the icon file exists.",
            ],
            help_topic=HELP_TOPIC_PACKAGING,
            evidence={"icon_path": icon_path, "relative_path": relative_path.as_posix()},
        )
    if is_packaging_excluded_path(relative_path):
        return RuntimeIssue(
            issue_id="package.config.icon_excluded",
            workflow="package",
            severity="blocking",
            title="Package icon sits in an excluded path",
            summary="icon_path resolves into a hidden or packaging-excluded location.",
            why_it_happened="Exports skip hidden folders and cache/log metadata paths by design.",
            next_steps=[
                "Move the icon into a visible project folder and update cbcs/package.json.",
            ],
            help_topic=HELP_TOPIC_PACKAGING,
            evidence={"icon_path": icon_path, "relative_path": relative_path.as_posix()},
        )
    return None


def _discover_hidden_paths(root: Path) -> list[str]:
    hidden_paths: list[str] = []
    for _current_path, relative_dir, dir_names, file_names in walk_project(
        root,
        include_meta_dir=True,
    ):
        for name in dir_names + file_names:
            rel_path = Path(name) if not relative_dir else Path(relative_dir) / name
            if any(part.startswith(".") for part in rel_path.parts if part not in {".", ".."}):
                hidden_paths.append(rel_path.as_posix())
    return sorted(hidden_paths)


def _load_project_exclude_patterns(root: Path) -> tuple[str, ...]:
    manifest_path = project_manifest_path(root)
    if not manifest_path.is_file():
        return ()
    try:
        metadata = load_project_manifest(manifest_path)
    except (OSError, ValueError):
        return ()
    return tuple(metadata.exclude_patterns)


def _discover_user_excluded_python_that_ships(root: Path) -> list[str]:
    exclude_patterns = _load_project_exclude_patterns(root)
    if not exclude_patterns:
        return []
    shipped: list[str] = []
    for path in DEFAULT_PACKAGING_PAYLOAD_POLICY.iter_payload_entries(root):
        if not path.is_file() or path.suffix != ".py":
            continue
        rel_path = path.relative_to(root).as_posix()
        if rel_path == "vendor" or rel_path.startswith("vendor/"):
            continue
        if should_exclude_relative_path(
            rel_path,
            exclude_patterns,
            is_directory=False,
        ):
            shipped.append(rel_path)
    return sorted(shipped)


def _sort_issues(issues: list[RuntimeIssue]) -> list[RuntimeIssue]:
    return sorted(
        issues,
        key=lambda issue: (
            -_SEVERITY_ORDER.get(issue.severity, 0),
            issue.title.lower(),
            issue.issue_id,
        ),
    )


def _summarize_package_preflight(issues: list[RuntimeIssue]) -> str:
    if not issues:
        return "Package export is ready."
    if any(issue.is_blocking for issue in issues):
        return "Packaging needs attention before export."
    return "Packaging can continue, but there are warnings to review."
