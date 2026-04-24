"""Unit tests for desktop_builder launcher generation."""

from __future__ import annotations

import pytest

from app.packaging.desktop_builder import (
    build_installed_launcher,
    build_installer_package_launcher,
    build_portable_launcher,
)
from app.packaging.installer_manifest import create_distribution_manifest
from app.packaging.models import (
    LAUNCHER_MODE_ABSOLUTE_INSTALL_ROOT,
    PACKAGE_KIND_PRODUCT,
    PACKAGE_PROFILE_INSTALLABLE,
)

pytestmark = pytest.mark.unit


def _make_manifest(**overrides):
    defaults = dict(
        package_kind=PACKAGE_KIND_PRODUCT,
        profile=PACKAGE_PROFILE_INSTALLABLE,
        package_id="test_app",
        display_name="Test App",
        version="1.0.0",
        description="A test application.",
        entry_relative_path="run_editor.py",
        icon_relative_path="app/ui/icons/Python_Icon.png",
        launcher_mode=LAUNCHER_MODE_ABSOLUTE_INSTALL_ROOT,
        default_install_base="/home/default",
        default_install_dirname="test_app_v1.0.0",
        staging_parent="/home/default",
        app_run_path="/opt/freecad/AppRun",
        write_menu_entry=False,
        write_desktop_shortcut=True,
    )
    defaults.update(overrides)
    return create_distribution_manifest(**defaults)


def test_installer_launcher_omits_icon_when_no_value_given() -> None:
    manifest = _make_manifest()

    content = build_installer_package_launcher(
        manifest=manifest,
        package_root_name="test_app_installer_v1.0.0",
    )

    assert "Icon=" not in content
    assert "Install Test App" in content
    assert "/opt/freecad/AppRun" in content


def test_installer_launcher_includes_icon_when_value_given() -> None:
    manifest = _make_manifest()

    content = build_installer_package_launcher(
        manifest=manifest,
        package_root_name="test_app_installer_v1.0.0",
        icon_value="/home/default/test_app_installer_v1.0.0/installer_icon.png",
    )

    assert "Icon=/home/default/test_app_installer_v1.0.0/installer_icon.png" in content
    assert "Install Test App" in content


def test_installed_launcher_includes_icon_from_manifest() -> None:
    manifest = _make_manifest(icon_relative_path="app/ui/icons/Python_Icon.png")

    content = build_installed_launcher(manifest, install_dir="/home/default/test_app_v1.0.0")

    assert "Icon=" in content
    assert "Python_Icon.png" in content


def test_installed_launcher_omits_icon_when_manifest_has_none() -> None:
    manifest = _make_manifest(icon_relative_path="")

    content = build_installed_launcher(manifest, install_dir="/home/default/test_app_v1.0.0")

    assert "Icon=" not in content
