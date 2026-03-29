"""Artifact-building helpers for project packaging exports."""

from __future__ import annotations

import json
from pathlib import Path
import shutil

from app.bootstrap.paths import ensure_directory, resolve_app_root
from app.core import constants
from app.core.models import ProjectMetadata, RuntimeIssueReport, WorkflowPreflightResult
from app.packaging.desktop_builder import (
    build_installable_install_text,
    build_installable_readme_text,
    build_installer_package_launcher,
    build_portable_install_text,
    build_portable_launcher,
    build_portable_readme_text,
)
from app.packaging.installer_manifest import (
    apply_checksums_to_manifest,
    build_artifact_checksums,
    create_distribution_manifest,
    save_distribution_manifest,
)
from app.packaging.layout import (
    build_artifact_root_name,
    build_installer_launcher_filename,
    paths_overlap,
    should_exclude_relative_path,
)
from app.packaging.models import (
    LAUNCHER_MODE_ABSOLUTE_INSTALL_ROOT,
    LAUNCHER_MODE_PORTABLE_DESKTOP_ARGUMENT,
    PACKAGE_APP_FILES_DIRNAME,
    PACKAGE_ARTIFACT_MANIFEST_FILENAME,
    PACKAGE_ARTIFACT_REPORT_FILENAME,
    PACKAGE_KIND_PROJECT,
    PACKAGE_PROFILE_INSTALLABLE,
    PackageExportResult,
    PackageValidationReport,
    ProjectPackageConfig,
)
from app.packaging.validator import build_package_validation_report, resolve_icon_relative_path


def build_project_package_artifact(
    *,
    project_root: str,
    project_metadata: ProjectMetadata,
    package_config: ProjectPackageConfig,
    output_dir: str,
    profile: str,
    known_runtime_modules: frozenset[str] | None = None,
) -> PackageExportResult:
    """Build an installable or portable project package artifact."""
    validation = build_package_validation_report(
        project_root=project_root,
        package_config=package_config,
        project_name=project_metadata.name,
        project_default_entry=project_metadata.default_entry,
        output_dir=output_dir,
        profile=profile,
        known_runtime_modules=known_runtime_modules,
    )
    if not validation.is_ready:
        return PackageExportResult(
            profile=profile,
            success=False,
            artifact_root="",
            manifest_path="",
            report_path="",
            readme_path="",
            install_notes_path="",
            launcher_path=None,
            validation=validation,
            error="Packaging validation failed.",
        )

    root = Path(project_root).expanduser().resolve()
    output_root = Path(output_dir).expanduser().resolve()
    ensure_directory(output_root)
    artifact_root = output_root / build_artifact_root_name(
        package_config.display_name or project_metadata.name,
        package_config.version,
        profile,
    )
    if paths_overlap(artifact_root, root):
        overlap_issue = RuntimeIssueReport(
            workflow="package",
            issues=list(validation.issue_report.issues),
        )
        failed_validation = PackageValidationReport(
            profile=profile,
            preflight=WorkflowPreflightResult(
                workflow="package",
                issues=list(validation.preflight.issues),
                summary=validation.preflight.summary,
            ),
            dependency_audit=validation.dependency_audit,
            issue_report=overlap_issue,
        )
        return PackageExportResult(
            profile=profile,
            success=False,
            artifact_root="",
            manifest_path="",
            report_path="",
            readme_path="",
            install_notes_path="",
            launcher_path=None,
            validation=failed_validation,
            error="Package output overlaps the live project.",
        )

    if artifact_root.exists():
        shutil.rmtree(artifact_root)
    artifact_root.mkdir(parents=True, exist_ok=False)

    try:
        result = _write_project_artifact(
            artifact_root=artifact_root,
            project_root=root,
            project_metadata=project_metadata,
            package_config=package_config,
            profile=profile,
            validation=validation,
        )
    except Exception as exc:
        return PackageExportResult(
            profile=profile,
            success=False,
            artifact_root=str(artifact_root),
            manifest_path="",
            report_path="",
            readme_path="",
            install_notes_path="",
            launcher_path=None,
            validation=validation,
            error=str(exc),
        )
    return result


def _write_project_artifact(
    *,
    artifact_root: Path,
    project_root: Path,
    project_metadata: ProjectMetadata,
    package_config: ProjectPackageConfig,
    profile: str,
    validation: PackageValidationReport,
) -> PackageExportResult:
    effective_entry = package_config.effective_entry_file(project_default_entry=project_metadata.default_entry)
    entry_relative_path = Path(PACKAGE_APP_FILES_DIRNAME, effective_entry).as_posix()
    icon_relative_path = resolve_icon_relative_path(
        project_root=str(project_root),
        package_config=package_config,
    )
    manifest = create_distribution_manifest(
        package_kind=PACKAGE_KIND_PROJECT,
        profile=profile,
        package_id=package_config.package_id,
        display_name=package_config.display_name,
        version=package_config.version,
        description=package_config.description,
        entry_relative_path=entry_relative_path,
        icon_relative_path=(
            Path(PACKAGE_APP_FILES_DIRNAME, icon_relative_path).as_posix()
            if icon_relative_path
            else ""
        ),
        launcher_mode=(
            LAUNCHER_MODE_PORTABLE_DESKTOP_ARGUMENT
            if profile != PACKAGE_PROFILE_INSTALLABLE
            else LAUNCHER_MODE_ABSOLUTE_INSTALL_ROOT
        ),
        default_install_base="/home/default",
        default_install_dirname="",
        staging_parent="/home/default",
        app_run_path=constants.APP_RUN_PATH,
        write_menu_entry=False,
        write_desktop_shortcut=True,
    )

    readme_path = artifact_root / manifest.readme_filename
    install_notes_path = artifact_root / manifest.install_notes_filename
    launcher_path: Path | None = None

    if profile == PACKAGE_PROFILE_INSTALLABLE:
        payload_root = artifact_root / manifest.payload_dirname
        app_files_root = payload_root / PACKAGE_APP_FILES_DIRNAME
        ensure_directory(app_files_root)
        _copy_project_tree(project_root, app_files_root)

        installer_root = artifact_root / manifest.installer_dirname
        ensure_directory(installer_root)
        installer_source = resolve_app_root() / "packaging" / "install.py"
        shutil.copy2(installer_source, installer_root / "install.py")

        installer_launcher_filename = build_installer_launcher_filename(manifest.display_name)
        launcher_path = artifact_root / installer_launcher_filename
        launcher_path.write_text(
            build_installer_package_launcher(
                manifest=manifest,
                package_root_name=artifact_root.name,
            ),
            encoding="utf-8",
        )
        readme_path.write_text(
            build_installable_readme_text(
                manifest=manifest,
                installer_launcher_filename=installer_launcher_filename,
            ),
            encoding="utf-8",
        )
        install_notes_path.write_text(
            build_installable_install_text(
                manifest=manifest,
                installer_launcher_filename=installer_launcher_filename,
            ),
            encoding="utf-8",
        )
    else:
        app_files_root = artifact_root / PACKAGE_APP_FILES_DIRNAME
        ensure_directory(app_files_root)
        _copy_project_tree(project_root, app_files_root)
        launcher_path = artifact_root / manifest.launcher_filename
        launcher_path.write_text(build_portable_launcher(manifest), encoding="utf-8")
        readme_path.write_text(build_portable_readme_text(manifest), encoding="utf-8")
        install_notes_path.write_text(build_portable_install_text(manifest), encoding="utf-8")

    report_path = artifact_root / PACKAGE_ARTIFACT_REPORT_FILENAME
    report_payload = {
        **PackageExportResult(
            profile=profile,
            success=True,
            artifact_root=str(artifact_root),
            manifest_path=str(artifact_root / PACKAGE_ARTIFACT_MANIFEST_FILENAME),
            report_path=str(report_path),
            readme_path=str(readme_path),
            install_notes_path=str(install_notes_path),
            launcher_path=None if launcher_path is None else str(launcher_path),
            validation=validation,
        ).to_dict(),
        "package_config": package_config.to_dict(),
        "project_metadata": project_metadata.to_dict(),
    }
    report_path.write_text(json.dumps(report_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    manifest_path = artifact_root / PACKAGE_ARTIFACT_MANIFEST_FILENAME
    checksums = build_artifact_checksums(
        artifact_root,
        skip_relative_paths=(PACKAGE_ARTIFACT_MANIFEST_FILENAME,),
    )
    manifest = apply_checksums_to_manifest(manifest, checksums)
    save_distribution_manifest(manifest_path, manifest)

    return PackageExportResult(
        profile=profile,
        success=True,
        artifact_root=str(artifact_root),
        manifest_path=str(manifest_path),
        report_path=str(report_path),
        readme_path=str(readme_path),
        install_notes_path=str(install_notes_path),
        launcher_path=None if launcher_path is None else str(launcher_path),
        validation=validation,
        error=None,
    )


def _copy_project_tree(source_root: Path, destination_root: Path) -> None:
    for path in sorted(source_root.rglob("*")):
        rel_path = path.relative_to(source_root)
        if should_exclude_relative_path(rel_path):
            continue
        target_path = destination_root / rel_path
        if path.is_dir():
            target_path.mkdir(parents=True, exist_ok=True)
            continue
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target_path)
