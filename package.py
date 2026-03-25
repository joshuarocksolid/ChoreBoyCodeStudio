#!/usr/bin/env python3
"""Package ChoreBoy Code Studio for distribution."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from app.core import constants
from app.packaging.desktop_builder import (
    build_installable_install_text,
    build_installable_readme_text,
    build_installer_package_launcher,
)
from app.packaging.installer_manifest import (
    apply_checksums_to_manifest,
    build_artifact_checksums,
    create_distribution_manifest,
    save_distribution_manifest,
)
from app.packaging.layout import build_installer_launcher_filename
from app.packaging.models import (
    LAUNCHER_MODE_ABSOLUTE_INSTALL_ROOT,
    PACKAGE_ARTIFACT_MANIFEST_FILENAME,
    PACKAGE_ARTIFACT_REPORT_FILENAME,
    PACKAGE_KIND_PRODUCT,
    PACKAGE_PROFILE_INSTALLABLE,
)

REPO_ROOT = Path(__file__).resolve().parent
ARTIFACTS_DIR = Path(os.environ.get("CBCS_ARTIFACTS_DIR", "") or str(REPO_ROOT.parent / "ChoreBoyCodeStudio_artifacts"))

INCLUDE_DIRS = ["app", "templates", "example_projects"]
INCLUDE_FILES = [
    "run_editor.py",
    "run_runner.py",
    "run_plugin_host.py",
    "launcher.py",
    "LICENSE",
]
PRUNE_DIR_NAMES = {"__pycache__", ".pyc"}
PRUNE_DIR_SUFFIXES = {".dist-info"}
INSTALLER_SOURCE = REPO_ROOT / "packaging" / "install.py"
CHOREBOY_STAGING_ROOT = "/home/default"
INSTALLER_ARCHIVE_BUDGET_BYTES = 15 * 1024 * 1024
ZIP_COMPRESSION_LEVEL = 9
ARCHIVE_PASSWORD = os.environ.get("CBCS_PACKAGE_ZIP_PASSWORD", "rsd")


def build_product_manifest(*, version: str, staging_parent: str = CHOREBOY_STAGING_ROOT):
    return create_distribution_manifest(
        package_kind=PACKAGE_KIND_PRODUCT,
        profile=PACKAGE_PROFILE_INSTALLABLE,
        package_id="choreboy_code_studio",
        display_name="ChoreBoy Code Studio",
        version=version,
        description="Project-first editor + runner for constrained systems.",
        entry_relative_path="run_editor.py",
        icon_relative_path="app/ui/icons/Python_Icon.png",
        launcher_mode=LAUNCHER_MODE_ABSOLUTE_INSTALL_ROOT,
        default_install_base=CHOREBOY_STAGING_ROOT,
        default_install_dirname=f"choreboy_code_studio_v{version}",
        staging_parent=staging_parent,
        app_run_path=constants.APP_RUN_PATH,
        write_menu_entry=True,
        write_desktop_shortcut=False,
    )


def build_installer_desktop_entry(staging_path: str) -> str:
    manifest = build_product_manifest(version=_read_version(), staging_parent=str(Path(staging_path).parent))
    return build_installer_package_launcher(
        manifest=manifest,
        package_root_name=Path(staging_path).name,
    )


def build_install_instructions() -> str:
    manifest = build_product_manifest(version=_read_version())
    return build_installable_install_text(
        manifest=manifest,
        installer_launcher_filename=build_installer_launcher_filename(manifest.display_name),
    )


def _read_version() -> str:
    constants_path = REPO_ROOT / "app" / "core" / "constants.py"
    text = constants_path.read_text(encoding="utf-8")
    match = re.search(r'^APP_VERSION\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
    return match.group(1) if match else "dev"


def _should_prune_dir(name: str) -> bool:
    if name in PRUNE_DIR_NAMES:
        return True
    return any(name.endswith(suffix) for suffix in PRUNE_DIR_SUFFIXES)


def _copytree_filtered(src: Path, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for entry in sorted(src.iterdir()):
        if entry.is_dir():
            if _should_prune_dir(entry.name):
                continue
            _copytree_filtered(entry, dst / entry.name)
            continue
        if entry.suffix == ".pyc":
            continue
        shutil.copy2(str(entry), str(dst / entry.name))


def archive_budget_bytes() -> int:
    return INSTALLER_ARCHIVE_BUDGET_BYTES


def is_archive_within_budget(size_bytes: int) -> bool:
    return size_bytes <= archive_budget_bytes()


def build_archive_zip_command(source_dir: Path, output_path: Path, password: str = ARCHIVE_PASSWORD) -> list[str]:
    return [
        "zip",
        "-r",
        f"-{ZIP_COMPRESSION_LEVEL}",
        "-P",
        password,
        output_path.name,
        source_dir.name,
    ]


def _make_zip(source_dir: Path, output_path: Path, password: str = ARCHIVE_PASSWORD) -> None:
    if output_path.exists():
        output_path.unlink()
    subprocess.run(
        build_archive_zip_command(source_dir, output_path, password=password),
        cwd=str(source_dir.parent),
        check=True,
    )


def _write_product_report(*, report_path: Path, manifest, archive_path: Path, archive_size_bytes: int) -> None:
    report_payload = {
        "package_kind": manifest.package_kind,
        "profile": manifest.profile,
        "package_id": manifest.package_id,
        "display_name": manifest.display_name,
        "version": manifest.version,
        "archive_path": str(archive_path),
        "archive_size_bytes": archive_size_bytes,
        "archive_budget_bytes": archive_budget_bytes(),
    }
    report_path.write_text(json.dumps(report_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    version = _read_version()
    manifest = build_product_manifest(version=version)
    package_name = f"choreboy_code_studio_installer_v{version}"
    installer_launcher_filename = build_installer_launcher_filename(manifest.display_name)

    dist_dir = ARTIFACTS_DIR / "dist"
    staging = dist_dir / package_name
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=True)

    payload_dir = staging / manifest.payload_dirname
    payload_dir.mkdir(parents=True, exist_ok=True)

    for dir_name in INCLUDE_DIRS:
        src = REPO_ROOT / dir_name
        if not src.is_dir():
            print(f"WARNING: missing include dir: {dir_name}")
            continue
        _copytree_filtered(src, payload_dir / dir_name)

    vendor_src = ARTIFACTS_DIR / "vendor"
    if not vendor_src.is_dir():
        print(f"ERROR: vendor directory not found at {vendor_src}")
        print("Set CBCS_ARTIFACTS_DIR or place vendor/ in the artifacts directory.")
        return 1
    _copytree_filtered(vendor_src, payload_dir / "vendor")

    for file_name in INCLUDE_FILES:
        src = REPO_ROOT / file_name
        if not src.is_file():
            print(f"WARNING: missing include file: {file_name}")
            continue
        shutil.copy2(str(src), str(payload_dir / file_name))

    installer_dir = staging / manifest.installer_dirname
    installer_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(INSTALLER_SOURCE), str(installer_dir / "install.py"))

    installer_launcher_path = staging / installer_launcher_filename
    installer_launcher_path.write_text(
        build_installer_package_launcher(manifest=manifest, package_root_name=package_name),
        encoding="utf-8",
    )
    installer_launcher_path.chmod(installer_launcher_path.stat().st_mode | 0o755)

    (staging / manifest.readme_filename).write_text(
        build_installable_readme_text(
            manifest=manifest,
            installer_launcher_filename=installer_launcher_filename,
        ),
        encoding="utf-8",
    )
    (staging / manifest.install_notes_filename).write_text(
        build_installable_install_text(
            manifest=manifest,
            installer_launcher_filename=installer_launcher_filename,
        ),
        encoding="utf-8",
    )

    report_path = staging / PACKAGE_ARTIFACT_REPORT_FILENAME
    report_path.write_text("{}", encoding="utf-8")
    checksums = build_artifact_checksums(
        staging,
        skip_relative_paths=(PACKAGE_ARTIFACT_MANIFEST_FILENAME, PACKAGE_ARTIFACT_REPORT_FILENAME),
    )
    manifest = apply_checksums_to_manifest(manifest, checksums)
    save_distribution_manifest(staging / PACKAGE_ARTIFACT_MANIFEST_FILENAME, manifest)

    archive_path = dist_dir / f"{package_name}.zip"
    _make_zip(staging, archive_path)
    archive_size_bytes = archive_path.stat().st_size
    _write_product_report(
        report_path=report_path,
        manifest=manifest,
        archive_path=archive_path,
        archive_size_bytes=archive_size_bytes,
    )

    archive_size_mb = archive_size_bytes / (1024 * 1024)
    budget_mb = archive_budget_bytes() / (1024 * 1024)
    print(f"Directory: {staging}")
    print(f"Archive:   {archive_path} ({archive_size_mb:.1f} MB)")
    print(f"Budget:    {budget_mb:.1f} MB maximum for email delivery")
    if not is_archive_within_budget(archive_size_bytes):
        print(f"ERROR: Archive exceeds the email budget ({archive_size_mb:.1f} MB > {budget_mb:.1f} MB).")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
