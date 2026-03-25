"""Unit tests for distribution packaging and standalone installer contract."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
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
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _build_installer_manifest(installer_module: ModuleType):
    return installer_module.PackageManifest(
        package_kind="product",
        profile="installable",
        package_id="choreboy_code_studio",
        display_name="ChoreBoy Code Studio",
        version="0.2.0",
        description="Editor package.",
        payload_dirname="payload",
        installer_dirname="installer",
        readme_filename="README.txt",
        install_notes_filename="INSTALL.txt",
        install_marker_filename="cbcs_installed_package.json",
        launcher_filename="choreboy_code_studio.desktop",
        launcher_name="ChoreBoy Code Studio",
        launcher_comment="Launch ChoreBoy Code Studio (Qt via FreeCAD AppRun)",
        launcher_mode="absolute_install_root",
        entry_relative_path="run_editor.py",
        icon_relative_path="app/ui/icons/Python_Icon.png",
        default_install_base="/home/default",
        default_install_dirname="choreboy_code_studio_v0.2.0",
        staging_parent="/home/default",
        app_run_path="/opt/freecad/AppRun",
        write_menu_entry=True,
        write_desktop_shortcut=False,
        checksums=tuple(),
    )


def test_distribution_install_instructions_require_home_default_staging() -> None:
    package_module = _load_module("distribution_package", "package.py")

    instructions = package_module.build_install_instructions()

    assert "/home/default/" in instructions
    assert "application-menu launcher" in instructions
    assert "Desktop shortcut" in instructions
    assert "staged copy" in instructions


def test_distribution_installer_desktop_entry_uses_direct_apprun() -> None:
    package_module = _load_module("distribution_package", "package.py")

    desktop_entry = package_module.build_installer_desktop_entry(
        "/home/default/choreboy_code_studio_installer_v0.2"
    )

    assert "/home/default/choreboy_code_studio_installer_v0.2" in desktop_entry
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
    manifest = _build_installer_manifest(installer_module)

    desktop_entry = installer_module.build_installed_desktop_entry(
        "/home/default/tools/code_studio",
        manifest,
    )

    assert "/home/default/tools/code_studio" in desktop_entry
    assert "run_editor.py" in desktop_entry
    assert "%k" not in desktop_entry
    assert "/bin/sh" not in desktop_entry
    assert "/opt/freecad/AppRun" in desktop_entry


def test_build_staging_location_warning_requires_home_default_staging() -> None:
    installer_module = _load_module("distribution_installer", "packaging/install.py")
    manifest = _build_installer_manifest(installer_module)

    warning = installer_module.build_staging_location_warning(
        Path("/tmp/choreboy_code_studio_installer_v0.2"),
        manifest,
    )

    assert warning is not None
    assert "/home/default/" in warning


def test_build_staging_location_warning_allows_home_default_staging() -> None:
    installer_module = _load_module("distribution_installer", "packaging/install.py")
    manifest = _build_installer_manifest(installer_module)

    warning = installer_module.build_staging_location_warning(
        Path("/home/default/choreboy_code_studio_installer_v0.2"),
        manifest,
    )

    assert warning is None


def test_verify_package_checksums_accepts_matching_file(tmp_path: Path) -> None:
    installer_module = _load_module("distribution_installer", "packaging/install.py")
    file_path = tmp_path / "payload" / "run_editor.py"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text("print('ok')\n", encoding="utf-8")
    digest = installer_module._compute_sha256(file_path)
    manifest = _build_installer_manifest(installer_module)
    manifest = installer_module.PackageManifest(
        **{
            **manifest.__dict__,
            "checksums": (
                installer_module.ArtifactChecksum(
                    relative_path="payload/run_editor.py",
                    sha256=digest,
                    size_bytes=file_path.stat().st_size,
                ),
            ),
        }
    )

    installer_module.verify_package_checksums(tmp_path, manifest)


def test_discover_existing_installs_filters_on_package_id(tmp_path: Path) -> None:
    installer_module = _load_module("distribution_installer", "packaging/install.py")
    manifest = _build_installer_manifest(installer_module)
    matching = tmp_path / "code_studio_v0.1"
    matching.mkdir()
    (matching / manifest.install_marker_filename).write_text(
        json.dumps({"package_id": manifest.package_id, "version": "0.1.0"}),
        encoding="utf-8",
    )
    other = tmp_path / "other_tool"
    other.mkdir()
    (other / manifest.install_marker_filename).write_text(
        json.dumps({"package_id": "different_package", "version": "1.0.0"}),
        encoding="utf-8",
    )

    installs = installer_module.discover_existing_installs(
        parent_dir=tmp_path,
        manifest=manifest,
    )

    assert installs == [{"path": str(matching.resolve()), "version": "0.1.0"}]
