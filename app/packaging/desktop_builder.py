"""Desktop-entry and human-readable docs builders for packaging artifacts."""

from __future__ import annotations

from pathlib import Path

from app.packaging.launcher_bootstrap import (
    build_desktop_path_shell_wrapper,
    build_fixed_root_bootstrap,
    validate_packaged_entry_relative_path,
)
from app.packaging.models import DistributionManifest


def build_installer_package_launcher(
    *,
    manifest: DistributionManifest,
    package_root_name: str,
    icon_value: str = "",
) -> str:
    """Return the staging-package launcher that runs the standalone installer."""
    installer_rel_path = f"{manifest.installer_dirname}/install.py"
    shell_wrapper = build_desktop_path_shell_wrapper(
        app_run_path=manifest.app_run_path,
        entry_relative_path=installer_rel_path,
        missing_location_message=(
            "Could not determine this installer package location. Keep the installer desktop file, "
            "installer folder, and payload folder together, then launch the installer desktop file again."
        ),
        allow_cwd_fallback=False,
    )
    return _build_desktop_entry(
        name=f"Install {manifest.display_name}",
        comment=f"Install {manifest.display_name} on this ChoreBoy system",
        exec_value=f'/bin/sh -c "{shell_wrapper}" dummy %k',
        icon_value=icon_value,
    )


def build_installed_launcher(manifest: DistributionManifest, *, install_dir: str | Path) -> str:
    """Return the launcher written into an installed package directory."""
    resolved_install_dir = str(Path(install_dir).expanduser().resolve())
    bootstrap = build_fixed_root_bootstrap(resolved_install_dir, manifest.entry_relative_path)
    icon_value = ""
    if manifest.icon_relative_path:
        icon_value = str((Path(resolved_install_dir) / manifest.icon_relative_path).resolve())
    return _build_desktop_entry(
        name=manifest.launcher_name,
        comment=manifest.launcher_comment,
        exec_value=f'{manifest.app_run_path} -c "{bootstrap}"',
        icon_value=icon_value,
    )


def build_portable_launcher(manifest: DistributionManifest) -> str:
    """Return the portable launcher that resolves package root from `%k`."""
    shell_wrapper = _build_portable_shell_wrapper(
        app_run_path=manifest.app_run_path,
        entry_relative_path=manifest.entry_relative_path,
    )
    return _build_desktop_entry(
        name=manifest.launcher_name,
        comment=manifest.launcher_comment,
        exec_value=f'/bin/sh -c "{shell_wrapper}" dummy %k',
        icon_value="",
    )


def build_installable_readme_text(
    *,
    manifest: DistributionManifest,
    installer_launcher_filename: str,
) -> str:
    """Return the package README for installable artifacts."""
    return (
        f"{manifest.display_name}\n"
        f"Version: {manifest.version}\n"
        f"Package ID: {manifest.package_id}\n"
        f"Profile: {manifest.profile}\n"
        "\n"
        "This export is an installable package for ChoreBoy.\n"
        "\n"
        "Package contents:\n"
        f"- `{installer_launcher_filename}` launches the installer through FreeCAD AppRun.\n"
        f"- `{manifest.installer_dirname}/install.py` is the standalone installer runtime.\n"
        f"- `{manifest.installer_dirname}/launcher_bootstrap.py` is the shared launcher bootstrap helper.\n"
        f"- `{manifest.payload_dirname}/` contains the files that will be copied into the final install folder.\n"
        f"- `{manifest.readme_filename}` and `{manifest.install_notes_filename}` explain install and upgrade behavior.\n"
        f"- `package_manifest.json` and `package_report.json` contain machine-readable metadata and audit details.\n"
        "\n"
        "The installer verifies package checksums before copying files, writes a stable launcher,\n"
        "and can publish that launcher to the application menu plus an optional Desktop shortcut.\n"
    )


def build_installable_install_text(
    *,
    manifest: DistributionManifest,
    installer_launcher_filename: str,
) -> str:
    """Return install/upgrade instructions for installable artifacts."""
    return (
        f"Install {manifest.display_name}\n"
        "\n"
        "1. Copy this entire folder onto the ChoreBoy machine.\n"
        f"2. Recommended: place the folder under `{manifest.staging_parent}` before launching the installer.\n"
        f"3. Open `{installer_launcher_filename}`.\n"
        "4. Review the suggested install location and any older-version cleanup options.\n"
        "5. Keep the package files together until installation finishes successfully.\n"
        "\n"
        "Installer behavior:\n"
        f"- default install folder: `{manifest.default_install_base}/{manifest.default_install_dirname}`\n"
        "- verifies checksums before copying payload files\n"
        "- performs staged copy + launcher write before swapping Desktop shortcuts\n"
        "- can publish a Desktop shortcut and optional application-menu launcher\n"
        "- can keep older versions side-by-side or remove them after a successful upgrade\n"
        "\n"
        "The installer launcher resolves this package folder from its own `.desktop` path.\n"
        "If the desktop environment cannot provide that path, keep the installer `.desktop`,\n"
        "`installer/`, and `payload/` together and launch the installer from the copied folder.\n"
        "\n"
        "After install, the launcher inside the installed folder becomes the source of truth.\n"
        "Any Desktop shortcut points at that installed folder, not back at this staging package.\n"
    )


def build_portable_readme_text(manifest: DistributionManifest) -> str:
    """Return the package README for portable artifacts."""
    return (
        f"{manifest.display_name}\n"
        f"Version: {manifest.version}\n"
        f"Package ID: {manifest.package_id}\n"
        f"Profile: {manifest.profile}\n"
        "\n"
        "This export is a portable package.\n"
        "\n"
        "Portable package contents:\n"
        f"- `{manifest.launcher_filename}` launches the app through FreeCAD AppRun.\n"
        f"- `{manifest.entry_relative_path}` is the packaged entry file path.\n"
        f"- `{manifest.readme_filename}` and `{manifest.install_notes_filename}` explain usage limits.\n"
        f"- `package_manifest.json` and `package_report.json` contain machine-readable metadata and audit details.\n"
        "\n"
        "Portable mode depends on the desktop launcher resolving its own `.desktop` file path.\n"
        "Keep the launcher in the same folder as the packaged files.\n"
    )


def build_portable_install_text(manifest: DistributionManifest) -> str:
    """Return usage instructions for portable artifacts."""
    return (
        f"Run {manifest.display_name} as a portable package\n"
        "\n"
        "1. Copy this entire folder to the target machine or USB device.\n"
        f"2. Keep `{manifest.launcher_filename}` in the root of this exported folder.\n"
        "3. Launch the `.desktop` file directly from that folder.\n"
        "\n"
        "Portable package rules:\n"
        "- do not separate the launcher from the packaged files\n"
        "- if the target desktop environment does not pass `.desktop` metadata correctly, use the installable profile instead\n"
        "- portable mode does not create application-menu entries automatically\n"
    )


def _build_absolute_root_bootstrap(root_path: str, entry_relative_path: str) -> str:
    return build_fixed_root_bootstrap(root_path, entry_relative_path)


def _build_portable_shell_wrapper(*, app_run_path: str, entry_relative_path: str) -> str:
    entry_relative_path = validate_packaged_entry_relative_path(entry_relative_path)
    return build_desktop_path_shell_wrapper(
        app_run_path=app_run_path,
        entry_relative_path=entry_relative_path,
        missing_location_message="Invalid package root",
        allow_cwd_fallback=True,
    )


def _build_desktop_entry(
    *,
    name: str,
    comment: str,
    exec_value: str,
    icon_value: str,
) -> str:
    lines = [
        "[Desktop Entry]",
        "Version=1.0",
        "Type=Application",
        f"Name={name}",
        f"Comment={comment}",
        f"Exec={exec_value}",
        "Terminal=false",
        "Categories=Utility;Development;",
        "StartupNotify=true",
    ]
    if icon_value:
        lines.append(f"Icon={icon_value}")
    return "\n".join(lines) + "\n"
