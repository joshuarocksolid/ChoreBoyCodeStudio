"""Runtime-parity tests for packaging launchers under AppRun."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
from types import ModuleType

import pytest

from app.core import constants
from app.packaging.desktop_builder import build_portable_launcher
from app.packaging.installer_manifest import create_distribution_manifest
from app.packaging.layout import sanitize_project_name
from app.packaging.models import (
    LAUNCHER_MODE_PORTABLE_DESKTOP_ARGUMENT,
    PACKAGE_KIND_PROJECT,
    PACKAGE_PROFILE_PORTABLE,
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


def _extract_shell_script(exec_line: str) -> str:
    prefix = '/bin/sh -c "'
    suffix = '" dummy %k'
    assert exec_line.startswith(prefix)
    assert exec_line.endswith(suffix)
    return exec_line[len(prefix) : -len(suffix)].replace('\\"', '"')


def _build_portable_desktop_entry(project_name: str, entry_file: str, install_dir: str) -> str:
    manifest = create_distribution_manifest(
        package_kind=PACKAGE_KIND_PROJECT,
        profile=PACKAGE_PROFILE_PORTABLE,
        package_id=sanitize_project_name(project_name),
        display_name=project_name,
        version="0.1.0",
        description="",
        entry_relative_path=Path(install_dir, entry_file).as_posix(),
        launcher_mode=LAUNCHER_MODE_PORTABLE_DESKTOP_ARGUMENT,
        app_run_path=constants.APP_RUN_PATH,
    )
    return build_portable_launcher(manifest)


def test_portable_launcher_bootstrap_runs_under_apprun_when_given_desktop_path(tmp_path: Path) -> None:
    _require_apprun()
    package_root = tmp_path / "portable_package"
    (package_root / "app_files").mkdir(parents=True, exist_ok=True)
    (package_root / "app_files" / "main.py").write_text("print('portable-ok')\n", encoding="utf-8")
    desktop_path = package_root / "portable_tool.desktop"
    desktop_content = _build_portable_desktop_entry("Portable Tool", "main.py", "app_files")
    desktop_path.write_text(desktop_content, encoding="utf-8")
    exec_line = next(line for line in desktop_content.splitlines() if line.startswith("Exec="))[len("Exec=") :]
    shell_script = _extract_shell_script(exec_line)

    completed = subprocess.run(
        ["/bin/sh", "-c", shell_script, "dummy", str(desktop_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "portable-ok" in completed.stdout


def test_installed_launcher_bootstrap_runs_under_apprun_with_absolute_install_root(tmp_path: Path) -> None:
    _require_apprun()
    installer_module = _load_installer_module()
    install_root = tmp_path / "installed_package"
    (install_root / "app_files").mkdir(parents=True, exist_ok=True)
    (install_root / "app_files" / "main.py").write_text("print('installed-ok')\n", encoding="utf-8")
    manifest = installer_module.PackageManifest(
        package_kind="project",
        profile="installable",
        package_id="portable_test",
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
