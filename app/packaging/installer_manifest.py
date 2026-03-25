"""Helpers for package manifests, install markers, and artifact checksums."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from app.packaging.layout import build_default_install_dirname, build_launcher_filename
from app.packaging.models import (
    ArtifactChecksum,
    DistributionManifest,
    InstalledPackageRecord,
    PACKAGE_ARTIFACT_INSTALL_FILENAME,
    PACKAGE_ARTIFACT_MANIFEST_FILENAME,
    PACKAGE_ARTIFACT_README_FILENAME,
    PACKAGE_CHECKSUM_ALGORITHM_SHA256,
    PACKAGE_CONFIG_SCHEMA_VERSION,
    PACKAGE_INSTALLER_DIRNAME,
    PACKAGE_INSTALLED_MARKER_FILENAME,
    PACKAGE_MANIFEST_SCHEMA_VERSION,
    PACKAGE_PAYLOAD_DIRNAME,
)


def create_distribution_manifest(
    *,
    package_kind: str,
    profile: str,
    package_id: str,
    display_name: str,
    version: str,
    description: str,
    entry_relative_path: str,
    icon_relative_path: str = "",
    launcher_name: str | None = None,
    launcher_comment: str | None = None,
    launcher_filename: str | None = None,
    launcher_mode: str,
    default_install_base: str = "/home/default",
    default_install_dirname: str | None = None,
    staging_parent: str = "/home/default",
    app_run_path: str = "/opt/freecad/AppRun",
    write_menu_entry: bool = True,
    write_desktop_shortcut: bool = False,
) -> DistributionManifest:
    """Create a normalized manifest with stable defaults."""
    effective_display_name = display_name.strip()
    effective_launcher_name = launcher_name.strip() if isinstance(launcher_name, str) and launcher_name.strip() else effective_display_name
    effective_launcher_filename = (
        launcher_filename.strip()
        if isinstance(launcher_filename, str) and launcher_filename.strip()
        else build_launcher_filename(effective_display_name)
    )
    effective_comment = launcher_comment.strip() if isinstance(launcher_comment, str) and launcher_comment.strip() else f"Launch {effective_display_name} (Qt via FreeCAD AppRun)"
    effective_install_dirname = (
        default_install_dirname.strip()
        if isinstance(default_install_dirname, str) and default_install_dirname.strip()
        else build_default_install_dirname(effective_display_name, version)
    )
    return DistributionManifest(
        schema_version=PACKAGE_MANIFEST_SCHEMA_VERSION,
        package_kind=package_kind,
        profile=profile,
        package_id=package_id,
        display_name=effective_display_name,
        version=version,
        description=description.strip(),
        created_at=datetime.now(timezone.utc).isoformat(),
        payload_dirname=PACKAGE_PAYLOAD_DIRNAME,
        installer_dirname=PACKAGE_INSTALLER_DIRNAME,
        readme_filename=PACKAGE_ARTIFACT_README_FILENAME,
        install_notes_filename=PACKAGE_ARTIFACT_INSTALL_FILENAME,
        install_marker_filename=PACKAGE_INSTALLED_MARKER_FILENAME,
        launcher_filename=effective_launcher_filename,
        launcher_name=effective_launcher_name,
        launcher_comment=effective_comment,
        launcher_mode=launcher_mode,
        entry_relative_path=entry_relative_path.strip(),
        icon_relative_path=icon_relative_path.strip(),
        default_install_base=default_install_base,
        default_install_dirname=effective_install_dirname,
        staging_parent=staging_parent,
        app_run_path=app_run_path,
        write_menu_entry=bool(write_menu_entry),
        write_desktop_shortcut=bool(write_desktop_shortcut),
        checksum_algorithm=PACKAGE_CHECKSUM_ALGORITHM_SHA256,
        checksums=tuple(),
    )


def apply_checksums_to_manifest(
    manifest: DistributionManifest,
    checksums: Iterable[ArtifactChecksum],
) -> DistributionManifest:
    """Return a manifest copy with populated checksum entries."""
    return replace(manifest, checksums=tuple(sorted(checksums, key=lambda item: item.relative_path)))


def save_distribution_manifest(path: str | Path, manifest: DistributionManifest) -> None:
    """Write one distribution manifest JSON file."""
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(manifest.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_distribution_manifest(path: str | Path) -> DistributionManifest:
    """Load and validate a distribution manifest from disk."""
    target = Path(path).expanduser().resolve()
    payload = json.loads(target.read_text(encoding="utf-8"))
    return parse_distribution_manifest(payload)


def parse_distribution_manifest(payload: Mapping[str, Any]) -> DistributionManifest:
    """Validate raw JSON manifest data."""
    schema_version = payload.get("schema_version")
    if schema_version != PACKAGE_MANIFEST_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported distribution manifest schema_version: {schema_version}. "
            f"Expected {PACKAGE_MANIFEST_SCHEMA_VERSION}."
        )

    checksums_payload = payload.get("checksums", [])
    if not isinstance(checksums_payload, list):
        raise ValueError("checksums must be a list.")
    checksums: list[ArtifactChecksum] = []
    for item in checksums_payload:
        if not isinstance(item, Mapping):
            raise ValueError("checksum entries must be objects.")
        relative_path = item.get("relative_path")
        sha256 = item.get("sha256")
        size_bytes = item.get("size_bytes")
        if not isinstance(relative_path, str) or not relative_path.strip():
            raise ValueError("checksum relative_path must be a non-empty string.")
        if not isinstance(sha256, str) or not sha256.strip():
            raise ValueError("checksum sha256 must be a non-empty string.")
        if not isinstance(size_bytes, int):
            raise ValueError("checksum size_bytes must be an integer.")
        checksums.append(
            ArtifactChecksum(
                relative_path=relative_path.strip(),
                sha256=sha256.strip(),
                size_bytes=size_bytes,
            )
        )

    return DistributionManifest(
        schema_version=schema_version,
        package_kind=str(payload["package_kind"]),
        profile=str(payload["profile"]),
        package_id=str(payload["package_id"]),
        display_name=str(payload["display_name"]),
        version=str(payload["version"]),
        description=str(payload.get("description", "")),
        created_at=str(payload["created_at"]),
        payload_dirname=str(payload.get("payload_dirname", PACKAGE_PAYLOAD_DIRNAME)),
        installer_dirname=str(payload.get("installer_dirname", PACKAGE_INSTALLER_DIRNAME)),
        readme_filename=str(payload.get("readme_filename", PACKAGE_ARTIFACT_README_FILENAME)),
        install_notes_filename=str(payload.get("install_notes_filename", PACKAGE_ARTIFACT_INSTALL_FILENAME)),
        install_marker_filename=str(payload.get("install_marker_filename", PACKAGE_INSTALLED_MARKER_FILENAME)),
        launcher_filename=str(payload["launcher_filename"]),
        launcher_name=str(payload["launcher_name"]),
        launcher_comment=str(payload["launcher_comment"]),
        launcher_mode=str(payload["launcher_mode"]),
        entry_relative_path=str(payload["entry_relative_path"]),
        icon_relative_path=str(payload.get("icon_relative_path", "")),
        default_install_base=str(payload.get("default_install_base", "/home/default")),
        default_install_dirname=str(payload.get("default_install_dirname", "")),
        staging_parent=str(payload.get("staging_parent", "/home/default")),
        app_run_path=str(payload.get("app_run_path", "/opt/freecad/AppRun")),
        write_menu_entry=bool(payload.get("write_menu_entry", True)),
        write_desktop_shortcut=bool(payload.get("write_desktop_shortcut", False)),
        checksum_algorithm=str(payload.get("checksum_algorithm", PACKAGE_CHECKSUM_ALGORITHM_SHA256)),
        checksums=tuple(checksums),
    )


def build_installed_package_record(
    *,
    manifest: DistributionManifest,
    install_dir: str | Path,
) -> InstalledPackageRecord:
    """Create the marker record written into an installed package."""
    return InstalledPackageRecord(
        package_id=manifest.package_id,
        display_name=manifest.display_name,
        version=manifest.version,
        package_kind=manifest.package_kind,
        profile=manifest.profile,
        install_dir=str(Path(install_dir).expanduser().resolve()),
        launcher_filename=manifest.launcher_filename,
        installed_at=datetime.now(timezone.utc).isoformat(),
    )


def save_installed_package_record(path: str | Path, record: InstalledPackageRecord) -> None:
    """Persist the visible installed-package marker file."""
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(record.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_installed_package_record(path: str | Path) -> InstalledPackageRecord:
    """Load one installed-package marker file."""
    target = Path(path).expanduser().resolve()
    payload = json.loads(target.read_text(encoding="utf-8"))
    return InstalledPackageRecord(
        package_id=str(payload["package_id"]),
        display_name=str(payload["display_name"]),
        version=str(payload["version"]),
        package_kind=str(payload["package_kind"]),
        profile=str(payload["profile"]),
        install_dir=str(payload["install_dir"]),
        launcher_filename=str(payload["launcher_filename"]),
        installed_at=str(payload["installed_at"]),
    )


def compute_file_sha256(path: str | Path) -> str:
    """Return the SHA-256 digest for one file."""
    digest = hashlib.sha256()
    with Path(path).expanduser().resolve().open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_artifact_checksums(
    package_root: str | Path,
    *,
    skip_relative_paths: Iterable[str] = (),
) -> tuple[ArtifactChecksum, ...]:
    """Return checksums for all files under *package_root* except skipped paths."""
    root = Path(package_root).expanduser().resolve()
    skipped = {item.strip() for item in skip_relative_paths if item.strip()}
    checksums: list[ArtifactChecksum] = []
    for file_path in sorted(root.rglob("*")):
        if not file_path.is_file():
            continue
        relative_path = file_path.relative_to(root).as_posix()
        if relative_path in skipped:
            continue
        checksums.append(
            ArtifactChecksum(
                relative_path=relative_path,
                sha256=compute_file_sha256(file_path),
                size_bytes=file_path.stat().st_size,
            )
        )
    return tuple(checksums)
