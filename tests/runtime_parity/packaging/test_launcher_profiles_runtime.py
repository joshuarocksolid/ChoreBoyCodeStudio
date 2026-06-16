"""Runtime-parity tests for packaging launchers under AppRun."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys
from types import ModuleType

import pytest

from app.core import constants
from app.packaging.desktop_builder import build_installer_package_launcher
from app.packaging.installer_manifest import create_distribution_manifest
from app.packaging.models import (
    LAUNCHER_MODE_ABSOLUTE_INSTALL_ROOT,
    PACKAGE_KIND_PROJECT,
    PACKAGE_PROFILE_INSTALLABLE,
)

pytestmark = pytest.mark.runtime_parity


def _require_apprun() -> None:
    app_run = Path(constants.APP_RUN_PATH)
    if not app_run.exists():
        pytest.skip(f"AppRun not available at {app_run}; skipping packaging runtime tests.")


def _load_installer_module() -> ModuleType:
    repo_root = Path(__file__).resolve().parents[3]
    module_path = repo_root / "packaging" / "install.py"
    spec = importlib.util.spec_from_file_location("distribution_installer_runtime", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["distribution_installer_runtime"] = module
    spec.loader.exec_module(module)
    return module


def _extract_bootstrap(exec_line: str) -> str:
    prefix = ' -c "'
    assert prefix in exec_line
    command_body = exec_line.split(prefix, 1)[1]
    if command_body.endswith('" %k'):
        return command_body[: -len('" %k')]
    assert command_body.endswith('"')
    return command_body[:-1]


def test_installed_launcher_bootstrap_runs_under_apprun_with_absolute_install_root(tmp_path: Path) -> None:
    _require_apprun()
    installer_module = _load_installer_module()
    install_root = tmp_path / "installed_package"
    (install_root / "app_files").mkdir(parents=True, exist_ok=True)
    (install_root / "app_files" / "main.py").write_text(
        "import os,sys\n"
        "print('installed-ok')\n"
        "print('cwd=' + os.path.basename(os.getcwd()))\n"
        "print('path0=' + os.path.basename(sys.path[0]))\n",
        encoding="utf-8",
    )
    manifest = installer_module.PackageManifest(
        package_kind="project",
        profile="installable",
        package_id="installed_test",
        display_name="Installed Test",
        version="1.0.0",
        description="",
        payload_dirname="payload",
        installer_dirname="installer",
        readme_filename="README.txt",
        install_notes_filename="INSTALL.txt",
        install_marker_filename="cbcs_installed_package.json",
        launcher_filename="installed_test.desktop",
        launcher_name="Installed Test",
        launcher_comment="Launch Installed Test",
        launcher_mode="absolute_install_root",
        entry_relative_path="app_files/main.py",
        icon_relative_path="",
        default_install_base="/home/default",
        default_install_dirname="installed_test_v1.0.0",
        staging_parent="/home/default",
        app_run_path=constants.APP_RUN_PATH,
        write_menu_entry=False,
        write_desktop_shortcut=True,
        checksums=tuple(),
    )
    desktop_content = installer_module.build_installed_desktop_entry(install_root, manifest)
    exec_line = next(line for line in desktop_content.splitlines() if line.startswith("Exec="))[len("Exec=") :]
    bootstrap = _extract_bootstrap(exec_line)

    completed = subprocess.run(
        [constants.APP_RUN_PATH, "-c", bootstrap],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "installed-ok" in completed.stdout
    assert "cwd=app_files" in completed.stdout
    assert "path0=app_files" in completed.stdout


def test_installer_package_launcher_resolves_root_from_desktop_path(tmp_path: Path) -> None:
    _require_apprun()
    repo_root = Path(__file__).resolve().parents[3]
    package_root = tmp_path / "renamed_installer_package"
    installer_root = package_root / "installer"
    installer_root.mkdir(parents=True, exist_ok=True)
    (package_root / "payload").mkdir()
    shutil.copy2(repo_root / "packaging" / "bootstrap.py", installer_root / "bootstrap.py")
    (installer_root / "install.py").write_text(
        "import os\n"
        "print('installer-ok')\n"
        "print('cwd=' + os.path.basename(os.getcwd()))\n",
        encoding="utf-8",
    )
    desktop_path = package_root / "install_test.desktop"
    manifest = create_distribution_manifest(
        package_kind=PACKAGE_KIND_PROJECT,
        profile=PACKAGE_PROFILE_INSTALLABLE,
        package_id="installer_test",
        display_name="Installer Test",
        version="1.0.0",
        description="",
        entry_relative_path="app_files/main.py",
        launcher_mode=LAUNCHER_MODE_ABSOLUTE_INSTALL_ROOT,
        app_run_path=constants.APP_RUN_PATH,
    )
    desktop_content = build_installer_package_launcher(
        manifest=manifest,
        package_root=package_root,
    )
    desktop_path.write_text(desktop_content, encoding="utf-8")
    assert f"Path={package_root.resolve()}" in desktop_content
    assert "%k" not in desktop_content
    assert "/bin/sh" not in desktop_content
    exec_line = next(line for line in desktop_content.splitlines() if line.startswith("Exec="))[len("Exec=") :]
    bootstrap = _extract_bootstrap(exec_line)

    completed = subprocess.run(
        [constants.APP_RUN_PATH, "-c", bootstrap],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(package_root),
    )

    assert completed.returncode == 0, completed.stderr
    assert "installer-ok" in completed.stdout
    assert "cwd=installer" in completed.stdout
    assert (package_root / "launch_diagnostic.json").is_file()
