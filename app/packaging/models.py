"""Shared data models for project and distribution packaging."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.models import RuntimeIssue, RuntimeIssueReport, WorkflowPreflightResult

PACKAGE_CONFIG_SCHEMA_VERSION = 1
PACKAGE_MANIFEST_SCHEMA_VERSION = 1
PACKAGE_REPORT_SCHEMA_VERSION = 1

PACKAGE_KIND_PROJECT = "project"
PACKAGE_KIND_PRODUCT = "product"
PACKAGE_KINDS = (PACKAGE_KIND_PROJECT, PACKAGE_KIND_PRODUCT)

PACKAGE_PROFILE_INSTALLABLE = "installable"
PACKAGE_PROFILE_PORTABLE = "portable"
PACKAGE_PROFILES = (
    PACKAGE_PROFILE_INSTALLABLE,
    PACKAGE_PROFILE_PORTABLE,
)

LAUNCHER_MODE_ABSOLUTE_INSTALL_ROOT = "absolute_install_root"
LAUNCHER_MODE_PORTABLE_DESKTOP_ARGUMENT = "portable_desktop_argument"

PACKAGE_PAYLOAD_DIRNAME = "payload"
PACKAGE_INSTALLER_DIRNAME = "installer"
PACKAGE_APP_FILES_DIRNAME = "app_files"
PACKAGE_ARTIFACT_MANIFEST_FILENAME = "package_manifest.json"
PACKAGE_ARTIFACT_REPORT_FILENAME = "package_report.json"
PACKAGE_ARTIFACT_README_FILENAME = "README.txt"
PACKAGE_ARTIFACT_INSTALL_FILENAME = "INSTALL.txt"
PACKAGE_INSTALLED_MARKER_FILENAME = "cbcs_installed_package.json"

PACKAGE_CHECKSUM_ALGORITHM_SHA256 = "sha256"
DEFAULT_PACKAGE_VERSION = "0.1.0"


@dataclass(frozen=True)
class ProjectPackageConfig:
    """Project-local packaging metadata stored under `cbcs/package.json`."""

    schema_version: int
    package_id: str
    display_name: str
    version: str = DEFAULT_PACKAGE_VERSION
    description: str = ""
    entry_file: str = ""
    icon_path: str = ""

    def effective_entry_file(self, *, project_default_entry: str) -> str:
        """Return the packaging entry override or fall back to project metadata."""
        if self.entry_file.strip():
            return self.entry_file.strip()
        return project_default_entry.strip()

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "package_id": self.package_id,
            "display_name": self.display_name,
            "version": self.version,
        }
        if self.description:
            payload["description"] = self.description
        if self.entry_file:
            payload["entry_file"] = self.entry_file
        if self.icon_path:
            payload["icon_path"] = self.icon_path
        return payload


@dataclass(frozen=True)
class ArtifactChecksum:
    """Checksum entry for one generated artifact file."""

    relative_path: str
    sha256: str
    size_bytes: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "relative_path": self.relative_path,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
        }


@dataclass(frozen=True)
class DistributionManifest:
    """Machine-readable contract for one exported package artifact."""

    schema_version: int
    package_kind: str
    profile: str
    package_id: str
    display_name: str
    version: str
    description: str
    created_at: str
    payload_dirname: str
    installer_dirname: str
    readme_filename: str
    install_notes_filename: str
    install_marker_filename: str
    launcher_filename: str
    launcher_name: str
    launcher_comment: str
    launcher_mode: str
    entry_relative_path: str
    icon_relative_path: str = ""
    default_install_base: str = "/home/default"
    default_install_dirname: str = ""
    staging_parent: str = "/home/default"
    app_run_path: str = "/opt/freecad/AppRun"
    write_menu_entry: bool = False
    write_desktop_shortcut: bool = True
    checksum_algorithm: str = PACKAGE_CHECKSUM_ALGORITHM_SHA256
    checksums: tuple[ArtifactChecksum, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "package_kind": self.package_kind,
            "profile": self.profile,
            "package_id": self.package_id,
            "display_name": self.display_name,
            "version": self.version,
            "description": self.description,
            "created_at": self.created_at,
            "payload_dirname": self.payload_dirname,
            "installer_dirname": self.installer_dirname,
            "readme_filename": self.readme_filename,
            "install_notes_filename": self.install_notes_filename,
            "install_marker_filename": self.install_marker_filename,
            "launcher_filename": self.launcher_filename,
            "launcher_name": self.launcher_name,
            "launcher_comment": self.launcher_comment,
            "launcher_mode": self.launcher_mode,
            "entry_relative_path": self.entry_relative_path,
            "default_install_base": self.default_install_base,
            "default_install_dirname": self.default_install_dirname,
            "staging_parent": self.staging_parent,
            "app_run_path": self.app_run_path,
            "write_menu_entry": self.write_menu_entry,
            "write_desktop_shortcut": self.write_desktop_shortcut,
            "checksum_algorithm": self.checksum_algorithm,
            "checksums": [entry.to_dict() for entry in self.checksums],
        }
        if self.icon_relative_path:
            payload["icon_relative_path"] = self.icon_relative_path
        return payload


@dataclass(frozen=True)
class InstalledPackageRecord:
    """Record written into an installed package root for upgrades/cleanup."""

    package_id: str
    display_name: str
    version: str
    package_kind: str
    profile: str
    install_dir: str
    launcher_filename: str
    installed_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "package_id": self.package_id,
            "display_name": self.display_name,
            "version": self.version,
            "package_kind": self.package_kind,
            "profile": self.profile,
            "install_dir": self.install_dir,
            "launcher_filename": self.launcher_filename,
            "installed_at": self.installed_at,
        }


@dataclass(frozen=True)
class DependencyAuditRecord:
    """Classification for one imported dependency discovered during audit."""

    source_file: str
    line_number: int
    module_name: str
    classification: str
    resolved_path: str | None = None
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_file": self.source_file,
            "line_number": self.line_number,
            "module_name": self.module_name,
            "classification": self.classification,
            "resolved_path": self.resolved_path,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class DependencyAuditReport:
    """Structured dependency audit for a project package export."""

    project_root: str
    records: list[DependencyAuditRecord]
    issues: list[RuntimeIssue]
    summary: str

    @property
    def highest_severity(self) -> str:
        if not self.issues:
            return "clear"
        return RuntimeIssueReport(workflow="package_audit", issues=self.issues).highest_severity

    @property
    def is_ready(self) -> bool:
        return not any(issue.is_blocking for issue in self.issues)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_root": self.project_root,
            "summary": self.summary,
            "highest_severity": self.highest_severity,
            "is_ready": self.is_ready,
            "records": [record.to_dict() for record in self.records],
            "issues": [issue.to_dict() for issue in self.issues],
        }


@dataclass(frozen=True)
class PackageValidationReport:
    """Combined editor-side validation report for one packaging request."""

    profile: str
    preflight: WorkflowPreflightResult
    dependency_audit: DependencyAuditReport
    issue_report: RuntimeIssueReport

    @property
    def is_ready(self) -> bool:
        return self.preflight.is_ready and self.dependency_audit.is_ready

    @property
    def highest_severity(self) -> str:
        return self.issue_report.highest_severity

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "is_ready": self.is_ready,
            "highest_severity": self.highest_severity,
            "preflight": self.preflight.to_dict(),
            "dependency_audit": self.dependency_audit.to_dict(),
            "issue_report": self.issue_report.to_dict(),
        }


@dataclass(frozen=True)
class PackageExportResult:
    """Full outcome of building a distribution artifact for one project."""

    profile: str
    success: bool
    artifact_root: str
    manifest_path: str
    report_path: str
    readme_path: str
    install_notes_path: str
    launcher_path: str | None
    validation: PackageValidationReport
    error: str | None = None

    @property
    def artifact_root_path(self) -> Path:
        return Path(self.artifact_root)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": PACKAGE_REPORT_SCHEMA_VERSION,
            "profile": self.profile,
            "success": self.success,
            "artifact_root": self.artifact_root,
            "manifest_path": self.manifest_path,
            "report_path": self.report_path,
            "readme_path": self.readme_path,
            "install_notes_path": self.install_notes_path,
            "launcher_path": self.launcher_path,
            "error": self.error,
            "validation": self.validation.to_dict(),
        }
