#!/usr/bin/env python3
"""Package ChoreBoy Code Studio for distribution.

Run on the dev machine (any Python 3.6+):
    python3 package.py

Produces:
    dist/ChoreBoyCodeStudio-v{version}/   -- staging directory
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

INSTALL_TXT = """\
ChoreBoy Code Studio - Installation Instructions
=================================================

1. Plug the USB drive into your ChoreBoy system.

2. Open the file manager and navigate to this folder.

3. Open a terminal (right-click > "Open Terminal Here" if available)
   or use the LibrePy Console, then run:

       /opt/freecad/AppRun python3 {path_placeholder}/install.py

   Replace {path_placeholder} with the full path to this folder,
   for example:

       /opt/freecad/AppRun python3 /media/usb/ChoreBoyCodeStudio-v{version}/install.py

4. Follow the on-screen wizard to choose an install location.

5. Once installed, launch ChoreBoy Code Studio from your application
   menu or desktop shortcut.
"""


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
    package_name = f"ChoreBoyCodeStudio-v{version}"

    dist_dir = REPO_ROOT / "dist"
    staging = dist_dir / package_name

    if staging.exists():
        print(f"Removing previous staging directory: {staging}")
        shutil.rmtree(staging)

    staging.mkdir(parents=True)
    print(f"Packaging {package_name} ...")

    for dir_name in INCLUDE_DIRS:
        src = REPO_ROOT / dir_name
        if not src.is_dir():
            print(f"  WARNING: directory not found, skipping: {dir_name}")
            continue
        print(f"  Copying {dir_name}/ ...")
        _copytree_filtered(src, staging / dir_name)

    for file_name in INCLUDE_FILES:
        src = REPO_ROOT / file_name
        if not src.is_file():
            print(f"  WARNING: file not found, skipping: {file_name}")
            continue
        print(f"  Copying {file_name}")
        shutil.copy2(str(src), str(staging / file_name))

    print("  Copying install.py ...")
    if not INSTALLER_SOURCE.is_file():
        print(f"  ERROR: installer not found at {INSTALLER_SOURCE}")
        return 1
    shutil.copy2(str(INSTALLER_SOURCE), str(staging / "install.py"))

    print("  Generating INSTALL.txt ...")
    install_txt = INSTALL_TXT.format(
        path_placeholder="<this-folder>",
        version=version,
    )
    (staging / "INSTALL.txt").write_text(install_txt, encoding="utf-8")

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
