"""Facade for manifest-driven project packaging workflows."""

from __future__ import annotations

from pathlib import Path

from app.core import constants
from app.core.models import ProjectMetadata
from app.packaging.artifact_builder import build_project_package_artifact
from app.packaging.config import load_or_create_project_package_config, save_project_package_config
from app.packaging.desktop_builder import build_portable_launcher
from app.packaging.installer_manifest import create_distribution_manifest
from app.packaging.layout import (
    paths_overlap as _paths_overlap,
    resolve_entry_path as _resolve_entry_path,
    sanitize_project_name,
    should_exclude_relative_path as _should_exclude,
)
from app.packaging.models import (
    LAUNCHER_MODE_PORTABLE_DESKTOP_ARGUMENT,
    PACKAGE_APP_FILES_DIRNAME,
    PACKAGE_KIND_PROJECT,
    PACKAGE_PROFILE_INSTALLABLE,
    PACKAGE_PROFILE_PORTABLE,
    PackageExportResult,
    ProjectPackageConfig,
)

PackageResult = PackageExportResult


def build_desktop_entry(project_name: str, entry_file: str, install_dir: str) -> str:
    """Compatibility wrapper for tests around the portable launcher contract."""
    manifest = create_distribution_manifest(
        package_kind=PACKAGE_KIND_PROJECT,
        profile=PACKAGE_PROFILE_PORTABLE,
        package_id=sanitize_project_name(project_name),
        display_name=project_name,
        version="0.1.0",
        description="",
        entry_relative_path=Path(install_dir, entry_file).as_posix(),
        launcher_mode=LAUNCHER_MODE_PORTABLE_DESKTOP_ARGUMENT,
        app_run_path=constants.APP_RUN_PATH,
    )
    return build_portable_launcher(manifest)


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
    from app.packaging.models import DependencyAuditReport, PackageValidationReport
    from app.core.models import RuntimeIssueReport, WorkflowPreflightResult

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
