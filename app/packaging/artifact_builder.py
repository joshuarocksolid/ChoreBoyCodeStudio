"""Artifact-building helpers for project packaging exports."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import shutil
from typing import Any, Callable, Mapping

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
    is_packaging_excluded_path,
    paths_overlap,
)
from app.packaging.models import (
    DistributionManifest,
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


@dataclass(frozen=True)
class WrittenInstallableArtifact:
    manifest: DistributionManifest
    payload_root: Path
    installer_root: Path
    launcher_path: Path
    readme_path: Path
    install_notes_path: Path
    report_path: Path
    manifest_path: Path


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


def write_installable_artifact_tree(
    *,
    artifact_root: Path,
    manifest: DistributionManifest,
    package_root_name: str,
    copy_payload: Callable[[Path], None],
    report_payload: Mapping[str, Any],
    checksum_skip_relative_paths: tuple[str, ...] = (PACKAGE_ARTIFACT_MANIFEST_FILENAME,),
    installer_icon_value: str = "",
    installer_source: Path | None = None,
    launcher_executable: bool = False,
) -> WrittenInstallableArtifact:
    """Write the shared manifest-driven installable artifact layout."""
    payload_root = artifact_root / manifest.payload_dirname
    ensure_directory(payload_root)
    copy_payload(payload_root)

    installer_root = artifact_root / manifest.installer_dirname
    ensure_directory(installer_root)
    effective_installer_source = installer_source or resolve_app_root() / "packaging" / "install.py"
    shutil.copy2(effective_installer_source, installer_root / "install.py")
    shutil.copy2(
        resolve_app_root() / "app" / "packaging" / "launcher_bootstrap.py",
        installer_root / "launcher_bootstrap.py",
    )

    installer_launcher_filename = build_installer_launcher_filename(manifest.display_name)
    launcher_path = artifact_root / installer_launcher_filename
    launcher_path.write_text(
        build_installer_package_launcher(
            manifest=manifest,
            package_root_name=package_root_name,
            icon_value=installer_icon_value,
        ),
        encoding="utf-8",
    )
    if launcher_executable:
        launcher_path.chmod(launcher_path.stat().st_mode | 0o755)

    readme_path = artifact_root / manifest.readme_filename
    install_notes_path = artifact_root / manifest.install_notes_filename
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

    report_path = artifact_root / PACKAGE_ARTIFACT_REPORT_FILENAME
    report_path.write_text(
        json.dumps(dict(report_payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    manifest_path = artifact_root / PACKAGE_ARTIFACT_MANIFEST_FILENAME
    checksums = build_artifact_checksums(
        artifact_root,
        skip_relative_paths=checksum_skip_relative_paths,
    )
    manifest = apply_checksums_to_manifest(manifest, checksums)
    save_distribution_manifest(manifest_path, manifest)

    return WrittenInstallableArtifact(
        manifest=manifest,
        payload_root=payload_root,
        installer_root=installer_root,
        launcher_path=launcher_path,
        readme_path=readme_path,
        install_notes_path=install_notes_path,
        report_path=report_path,
        manifest_path=manifest_path,
    )


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

    if profile == PACKAGE_PROFILE_INSTALLABLE:
        installer_launcher_filename = build_installer_launcher_filename(manifest.display_name)
        readme_path = artifact_root / manifest.readme_filename
        install_notes_path = artifact_root / manifest.install_notes_filename
        report_path = artifact_root / PACKAGE_ARTIFACT_REPORT_FILENAME
        launcher_path = artifact_root / installer_launcher_filename
        manifest_path = artifact_root / PACKAGE_ARTIFACT_MANIFEST_FILENAME

        installer_icon_value = ""
        if manifest.icon_relative_path and icon_relative_path:
            source_icon = project_root / icon_relative_path
            if source_icon.is_file():
                installer_icon_value = str(
                    Path(manifest.staging_parent)
                    / artifact_root.name
                    / manifest.payload_dirname
                    / manifest.icon_relative_path
                )

        def _copy_payload(payload_root: Path) -> None:
            app_files_root = payload_root / PACKAGE_APP_FILES_DIRNAME
            ensure_directory(app_files_root)
            _copy_project_tree(project_root, app_files_root)

        report_payload = {
            **PackageExportResult(
                profile=profile,
                success=True,
                artifact_root=str(artifact_root),
                manifest_path=str(manifest_path),
                report_path=str(report_path),
                readme_path=str(readme_path),
                install_notes_path=str(install_notes_path),
                launcher_path=str(launcher_path),
                validation=validation,
            ).to_dict(),
            "package_config": package_config.to_dict(),
            "project_metadata": project_metadata.to_dict(),
        }
        written = write_installable_artifact_tree(
            artifact_root=artifact_root,
            manifest=manifest,
            package_root_name=artifact_root.name,
            copy_payload=_copy_payload,
            report_payload=report_payload,
            installer_icon_value=installer_icon_value,
        )
        return PackageExportResult(
            profile=profile,
            success=True,
            artifact_root=str(artifact_root),
            manifest_path=str(written.manifest_path),
            report_path=str(written.report_path),
            readme_path=str(written.readme_path),
            install_notes_path=str(written.install_notes_path),
            launcher_path=str(written.launcher_path),
            validation=validation,
            error=None,
        )

    readme_path = artifact_root / manifest.readme_filename
    install_notes_path = artifact_root / manifest.install_notes_filename
    app_files_root = artifact_root / PACKAGE_APP_FILES_DIRNAME
    ensure_directory(app_files_root)
    _copy_project_tree(project_root, app_files_root)
    launcher_path = artifact_root / manifest.launcher_filename
    launcher_path.write_text(build_portable_launcher(manifest), encoding="utf-8")
    readme_path.write_text(build_portable_readme_text(manifest), encoding="utf-8")
    install_notes_path.write_text(build_portable_install_text(manifest), encoding="utf-8")
    report_path = artifact_root / PACKAGE_ARTIFACT_REPORT_FILENAME
    manifest_path = artifact_root / PACKAGE_ARTIFACT_MANIFEST_FILENAME
    report_payload = {
        **PackageExportResult(
            profile=profile,
            success=True,
            artifact_root=str(artifact_root),
            manifest_path=str(manifest_path),
            report_path=str(report_path),
            readme_path=str(readme_path),
            install_notes_path=str(install_notes_path),
            launcher_path=str(launcher_path),
            validation=validation,
        ).to_dict(),
        "package_config": package_config.to_dict(),
        "project_metadata": project_metadata.to_dict(),
    }
    report_path.write_text(json.dumps(report_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

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
        if is_packaging_excluded_path(rel_path):
            continue
        target_path = destination_root / rel_path
        if path.is_dir():
            target_path.mkdir(parents=True, exist_ok=True)
            continue
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target_path)
