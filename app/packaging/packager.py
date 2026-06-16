"""Facade for manifest-driven project packaging workflows."""

from __future__ import annotations

from pathlib import Path

from app.core import constants
from app.core.models import ProjectMetadata, RuntimeIssue, RuntimeIssueReport, WorkflowPreflightResult
from app.packaging.artifact_builder import build_project_package_artifact
from app.packaging.config import load_or_create_project_package_config, save_project_package_config
from app.packaging.layout import (
    paths_overlap as _paths_overlap,
    sanitize_project_name,
)
from app.packaging.models import (
    DependencyAuditReport,
    PACKAGE_PROFILE_INSTALLABLE,
    PackageValidationReport,
    PackageExportResult,
    ProjectPackageConfig,
)

PackageResult = PackageExportResult


def package_project(
    *,
    project_root: str,
    project_name: str,
    entry_file: str,
    output_dir: str,
    profile: str = PACKAGE_PROFILE_INSTALLABLE,
    package_config: ProjectPackageConfig | None = None,
    project_metadata: ProjectMetadata | None = None,
    known_runtime_modules: frozenset[str] | None = None,
) -> PackageResult:
    """Build a manifest-driven project package artifact."""
    if profile != PACKAGE_PROFILE_INSTALLABLE:
        return PackageResult(
            profile=profile,
            success=False,
            artifact_root="",
            manifest_path="",
            report_path="",
            readme_path="",
            install_notes_path="",
            launcher_path=None,
            validation=_unsupported_profile_validation_report(profile=profile),
            error=f"Unsupported package profile: {profile}. Use installable.",
        )

    root = Path(project_root).expanduser().resolve()
    if not root.is_dir():
        empty_validation = _empty_validation_report(profile=profile)
        return PackageResult(
            profile=profile,
            success=False,
            artifact_root="",
            manifest_path="",
            report_path="",
            readme_path="",
            install_notes_path="",
            launcher_path=None,
            validation=empty_validation,
            error=f"Project root does not exist: {project_root}",
        )

    effective_metadata = project_metadata or ProjectMetadata(
        schema_version=1,
        name=project_name,
        project_id=sanitize_project_name(project_name),
        default_entry=entry_file,
    )
    effective_config = package_config or load_or_create_project_package_config(
        project_root=str(root),
        project_metadata=effective_metadata,
    )

    # Persist the latest wizard-reviewed package metadata before export.
    save_project_package_config(root / constants.PROJECT_META_DIRNAME / constants.PROJECT_PACKAGE_CONFIG_FILENAME, effective_config)

    return build_project_package_artifact(
        project_root=str(root),
        project_metadata=effective_metadata,
        package_config=effective_config,
        output_dir=output_dir,
        profile=profile,
        known_runtime_modules=known_runtime_modules,
    )


def _empty_validation_report(*, profile: str):
    preflight = WorkflowPreflightResult(
        workflow="package",
        issues=[],
        summary="Packaging did not start.",
    )
    audit = DependencyAuditReport(
        project_root="",
        records=[],
        issues=[],
        summary="Packaging did not start.",
    )
    issue_report = RuntimeIssueReport(workflow="package", issues=[])
    return PackageValidationReport(
        profile=profile,
        preflight=preflight,
        dependency_audit=audit,
        issue_report=issue_report,
    )


def _unsupported_profile_validation_report(*, profile: str) -> PackageValidationReport:
    issue = RuntimeIssue(
        issue_id="package.profile.unsupported",
        workflow="package",
        severity="blocking",
        title="Package profile is no longer supported",
        summary="Only installable packages are supported on ChoreBoy.",
        why_it_happened="Real desktop probes showed the old portable launcher contract depends on desktop metadata that ChoreBoy does not reliably provide.",
        next_steps=[
            "Export the project using the installable profile.",
            "Keep the installer folder together and launch it from its generated .desktop file.",
        ],
        evidence={"profile": profile},
    )
    preflight = WorkflowPreflightResult(
        workflow="package",
        issues=[issue],
        summary="Packaging needs attention before export.",
    )
    audit = DependencyAuditReport(
        project_root="",
        records=[],
        issues=[],
        summary="Dependency audit skipped because the requested package profile is unsupported.",
    )
    issue_report = RuntimeIssueReport(workflow="package", issues=[issue])
    return PackageValidationReport(
        profile=profile,
        preflight=preflight,
        dependency_audit=audit,
        issue_report=issue_report,
    )
