"""Desktop-entry and human-readable docs builders for packaging artifacts."""

from __future__ import annotations

import os
from pathlib import Path

from app.packaging.models import DistributionManifest


def build_installer_package_launcher(
    *,
    manifest: DistributionManifest,
    package_root_name: str,
    icon_value: str = "",
) -> str:
    """Return the staging-package launcher that runs the standalone installer."""
    package_root = os.path.join(manifest.staging_parent, package_root_name)
    installer_rel_path = os.path.join(manifest.installer_dirname, "install.py").replace("\\", "/")
    bootstrap = _build_absolute_root_bootstrap(package_root, installer_rel_path)
    return _build_desktop_entry(
        name=f"Install {manifest.display_name}",
        comment=f"Install {manifest.display_name} on this ChoreBoy system",
        exec_value=f'{manifest.app_run_path} -c "{bootstrap}"',
        icon_value=icon_value,
    )


def build_installed_launcher(manifest: DistributionManifest, *, install_dir: str | Path) -> str:
    """Return the launcher written into an installed package directory."""
    resolved_install_dir = str(Path(install_dir).expanduser().resolve())
    bootstrap = _build_absolute_root_bootstrap(resolved_install_dir, manifest.entry_relative_path)
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
        f"2. Place the folder under `{manifest.staging_parent}` before launching the installer.\n"
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
    return (
        "import os,runpy,sys;"
        f"root={root_path!r};"
        "sys.path.insert(0, root) if root not in sys.path else None;"
        "os.chdir(root);"
        f"runpy.run_path(os.path.join(root, {entry_relative_path!r}), run_name='__main__')"
    )


def _build_portable_root_bootstrap(entry_relative_path: str) -> str:
    return (
        "import os,runpy,sys;"
        "desktop_path = sys.argv[1] if len(sys.argv) > 1 else '';"
        "root = os.path.dirname(os.path.abspath(desktop_path)) if desktop_path else os.getcwd();"
        "sys.path.insert(0, root) if root not in sys.path else None;"
        "os.chdir(root);"
        f"runpy.run_path(os.path.join(root, {entry_relative_path!r}), run_name='__main__')"
    )


def _build_portable_shell_wrapper(*, app_run_path: str, entry_relative_path: str) -> str:
    python_code = (
        "import os,runpy,sys;"
        'root=os.environ.get("CBCS_PACKAGE_ROOT", os.getcwd());'
        "sys.path.insert(0, root) if root not in sys.path else None;"
        "os.chdir(root);"
        f'runpy.run_path(os.path.join(root, "{entry_relative_path}"), run_name="__main__")'
    )
    shell_script = (
        'desktop_path="$1";'
        'root="$(dirname "$desktop_path")";'
        f'CBCS_PACKAGE_ROOT="$root" exec {app_run_path} -c \'{python_code}\''
    )
    return shell_script.replace('"', '\\"')


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
