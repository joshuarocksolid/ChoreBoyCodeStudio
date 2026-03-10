#!/usr/bin/env python3
"""Package ChoreBoy Code Studio for distribution.

Run on the dev machine (any Python 3.6+):
    python3 package.py

Produces:
    dist/ChoreBoyCodeStudio-v{version}/   -- staging directory to copy to /home/default/ on ChoreBoy
    dist/ChoreBoyCodeStudio-v{version}.zip -- password-protected archive for USB transfer
"""

from __future__ import annotations

import os
import re
import shutil
import sys
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent

INCLUDE_DIRS = [
    "app",
    "vendor",
    "templates",
    "example_projects",
]

INCLUDE_FILES = [
    "run_editor.py",
    "run_runner.py",
    "run_plugin_host.py",
    "launcher.py",
    "LICENSE",
]

PRUNE_DIR_NAMES = {
    "__pycache__",
    ".pyc",
}

PRUNE_DIR_SUFFIXES = {
    ".dist-info",
}

INSTALLER_SOURCE = REPO_ROOT / "packaging" / "install.py"
CHOREBOY_STAGING_ROOT = "/home/default"

INSTALLER_DESKTOP_TEMPLATE = """\
[Desktop Entry]
Type=Application
Version=1.0
Name=Install ChoreBoy Code Studio
Comment=Install ChoreBoy Code Studio on this system
Terminal=false
Categories=Utility;

Exec=/opt/freecad/AppRun -c "import os,runpy,sys;root='{staging_path}';sys.path.insert(0,root) if root not in sys.path else None;os.chdir(root);runpy.run_path(os.path.join(root,'installer','install.py'),run_name='__main__')"
"""

INSTALL_TXT = """\
ChoreBoy Code Studio - Installation Instructions
=================================================

1. Copy this entire folder into `/home/default/` on the ChoreBoy.

2. Keep the entire folder together.
   Do not move `install_choreboy_code_studio.desktop` away from the
   rest of this installer folder.

3. Open this copied folder from `/home/default/` in the ChoreBoy
   file manager.

4. Right-click the "install_choreboy_code_studio.desktop" file
   and select "Allow Launching" (you only need to do this once).

5. Double-click "install_choreboy_code_studio.desktop" to start
   the installer.

6. Follow the on-screen wizard to choose where the Code Studio files
   should live on disk.

7. The installer writes the application-menu entry (and optional
   desktop shortcut) to hardcode the chosen installation directory.

8. If you later move the installed Code Studio folder, rerun this
   installer so the launcher points at the new location.

9. Once installed, launch ChoreBoy Code Studio from your
   application menu or desktop shortcut.

10. After a successful install, you can delete this installer
   folder from your Home Folder.
"""


def build_installer_desktop_entry(staging_path: str) -> str:
    """Return the launcher used to start the bundled installer."""
    return INSTALLER_DESKTOP_TEMPLATE.format(staging_path=staging_path)


def build_install_instructions() -> str:
    """Return human instructions shipped with the installer package."""
    return INSTALL_TXT


def _read_version() -> str:
    constants = REPO_ROOT / "app" / "core" / "constants.py"
    text = constants.read_text(encoding="utf-8")
    match = re.search(r'^APP_VERSION\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
    if not match:
        print("WARNING: Could not parse APP_VERSION, defaulting to 'dev'")
        return "dev"
    return match.group(1)


def _should_prune_dir(name: str) -> bool:
    if name in PRUNE_DIR_NAMES:
        return True
    for suffix in PRUNE_DIR_SUFFIXES:
        if name.endswith(suffix):
            return True
    return False


def _copytree_filtered(src: Path, dst: Path) -> None:
    """Copy a directory tree, skipping pruned dirs and .pyc files."""
    dst.mkdir(parents=True, exist_ok=True)
    for entry in sorted(src.iterdir()):
        if entry.is_dir():
            if _should_prune_dir(entry.name):
                continue
            _copytree_filtered(entry, dst / entry.name)
        else:
            if entry.suffix == ".pyc":
                continue
            shutil.copy2(str(entry), str(dst / entry.name))


def _make_zip(source_dir: Path, output_path: Path, password: str = "rsd") -> None:
    """Create a password-protected, uncompressed zip via the ``zip`` CLI."""
    if output_path.exists():
        output_path.unlink()
    subprocess.run(
        [
            "zip", "-r", "-0",
            "-P", password,
            output_path.name,
            source_dir.name,
        ],
        cwd=str(source_dir.parent),
        check=True,
    )


def main() -> int:
    version = _read_version()
    package_name = f"choreboy_code_studio_installer_v{version}"

    dist_dir = REPO_ROOT / "dist"
    staging = dist_dir / package_name

    if staging.exists():
        print(f"Removing previous staging directory: {staging}")
        shutil.rmtree(staging)

    staging.mkdir(parents=True)
    print(f"Packaging {package_name} ...")

    payload_dir = staging / "payload"
    payload_dir.mkdir()

    for dir_name in INCLUDE_DIRS:
        src = REPO_ROOT / dir_name
        if not src.is_dir():
            print(f"  WARNING: directory not found, skipping: {dir_name}")
            continue
        print(f"  Copying payload/{dir_name}/ ...")
        _copytree_filtered(src, payload_dir / dir_name)

    for file_name in INCLUDE_FILES:
        src = REPO_ROOT / file_name
        if not src.is_file():
            print(f"  WARNING: file not found, skipping: {file_name}")
            continue
        print(f"  Copying payload/{file_name}")
        shutil.copy2(str(src), str(payload_dir / file_name))

    installer_dir = staging / "installer"
    installer_dir.mkdir()
    print("  Copying installer/install.py ...")
    if not INSTALLER_SOURCE.is_file():
        print(f"  ERROR: installer not found at {INSTALLER_SOURCE}")
        return 1
    shutil.copy2(str(INSTALLER_SOURCE), str(installer_dir / "install.py"))

    print("  Generating install_choreboy_code_studio.desktop ...")
    staging_path = f"{CHOREBOY_STAGING_ROOT}/{package_name}"
    desktop_path = staging / "install_choreboy_code_studio.desktop"
    desktop_path.write_text(build_installer_desktop_entry(staging_path), encoding="utf-8")
    desktop_path.chmod(desktop_path.stat().st_mode | 0o755)

    print("  Generating INSTALL.txt ...")
    (staging / "INSTALL.txt").write_text(build_install_instructions(), encoding="utf-8")

    archive_path = dist_dir / f"{package_name}.zip"
    print(f"  Creating archive: {archive_path.name} ...")
    _make_zip(staging, archive_path)

    archive_size_mb = archive_path.stat().st_size / (1024 * 1024)
    print()
    print(f"Done. Package ready at:")
    print(f"  Directory: {staging}")
    print(f"  Archive:   {archive_path} ({archive_size_mb:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
