"""Unit tests for distribution packaging and installer contract."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.unit


def _load_module(module_name: str, relative_path: str) -> ModuleType:
    repo_root = Path(__file__).resolve().parents[3]
    module_path = repo_root / relative_path
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_distribution_install_instructions_require_home_default_staging() -> None:
    package_module = _load_module("distribution_package", "package.py")

    instructions = package_module.build_install_instructions()

    assert "/home/default/" in instructions
    assert "Keep the entire folder together" in instructions
    assert "hardcode the chosen installation directory" in instructions


def test_distribution_installer_desktop_entry_uses_direct_apprun() -> None:
    package_module = _load_module("distribution_package", "package.py")

    desktop_entry = package_module.build_installer_desktop_entry(
        "/home/default/choreboy_code_studio_installer_v0.1"
    )

    assert "/home/default/choreboy_code_studio_installer_v0.1" in desktop_entry
    assert "installer" in desktop_entry
    assert "install.py" in desktop_entry
    assert "/opt/freecad/AppRun" in desktop_entry
    assert "/bin/sh" not in desktop_entry


def test_distribution_archive_budget_is_15_mb() -> None:
    package_module = _load_module("distribution_package", "package.py")

    assert package_module.archive_budget_bytes() == 15 * 1024 * 1024
    assert package_module.is_archive_within_budget(15 * 1024 * 1024) is True
    assert package_module.is_archive_within_budget((15 * 1024 * 1024) + 1) is False


def test_distribution_archive_zip_command_uses_compression() -> None:
    package_module = _load_module("distribution_package", "package.py")

    command = package_module.build_archive_zip_command(
        Path("/tmp/staging"),
        Path("/tmp/archive.zip"),
    )

    assert "-9" in command
    assert "-0" not in command
    assert "archive.zip" in command
    assert "staging" in command


def test_installed_desktop_entry_hardcodes_selected_install_dir() -> None:
    installer_module = _load_module("distribution_installer", "packaging/install.py")

    desktop_entry = installer_module.build_installed_desktop_entry("/home/default/tools/code_studio")

    assert "/home/default/tools/code_studio" in desktop_entry
    assert "run_editor.py" in desktop_entry
    assert "%k" not in desktop_entry
    assert "/bin/sh" not in desktop_entry
    assert "/opt/freecad/AppRun" in desktop_entry


def test_build_staging_location_warning_requires_home_default_staging() -> None:
    installer_module = _load_module("distribution_installer", "packaging/install.py")

    warning = installer_module.build_staging_location_warning(Path("/tmp/choreboy_code_studio_installer_v0.1"))

    assert warning is not None
    assert "/home/default/" in warning


def test_build_staging_location_warning_allows_home_default_staging() -> None:
    installer_module = _load_module("distribution_installer", "packaging/install.py")

    warning = installer_module.build_staging_location_warning(Path("/home/default/choreboy_code_studio_installer_v0.1"))

    assert warning is None
