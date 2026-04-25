"""Unit tests for distribution packaging and standalone installer contract."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType
import zipfile

import pytest

from app.packaging import product_builder as product_package

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
        write_menu_entry=False,
        write_desktop_shortcut=True,
        checksums=tuple(),
    )


def _stage_tree_sitter_bundle(
    root: Path,
    package_module: ModuleType,
    *,
    core_soabi: str | None = None,
    grammar_binding_name: str | None = None,
    extra_binding_name: str | None = None,
) -> Path:
    vendor_dir = root / "vendor"
    vendor_dir.mkdir(parents=True, exist_ok=True)
    for package_name in package_module.CHOREBOY_PRODUCT_TREE_SITTER_PACKAGES:
        package_dir = vendor_dir / package_name
        package_dir.mkdir(parents=True, exist_ok=True)
        if package_name == "tree_sitter":
            binding_name = package_module._expected_tree_sitter_binding_name(
                core_soabi or package_module.CHOREBOY_PRODUCT_TREE_SITTER_SOABI
            )
        else:
            binding_name = grammar_binding_name or package_module.CHOREBOY_PRODUCT_TREE_SITTER_BINDINGS[package_name]
        (package_dir / binding_name).write_bytes(b"binding")
        if extra_binding_name is not None:
            (package_dir / extra_binding_name).write_bytes(b"extra")
    return vendor_dir


def _make_product_repo(root: Path) -> Path:
    (root / "app" / "ui" / "icons").mkdir(parents=True, exist_ok=True)
    (root / "app" / "ui" / "icons" / "installer_icon.png").write_bytes(b"icon")
    (root / "app" / "main.py").write_text("print('product')\n", encoding="utf-8")
    (root / "app" / ".hidden_cache").mkdir(parents=True, exist_ok=True)
    (root / "app" / ".hidden_cache" / "state.json").write_text("{}\n", encoding="utf-8")
    (root / "templates").mkdir(parents=True, exist_ok=True)
    (root / "templates" / "template.txt").write_text("template\n", encoding="utf-8")
    (root / "example_projects").mkdir(parents=True, exist_ok=True)
    (root / "example_projects" / "demo.py").write_text("print('demo')\n", encoding="utf-8")
    (root / "packaging").mkdir(parents=True, exist_ok=True)
    (root / "packaging" / "install.py").write_text("print('install')\n", encoding="utf-8")
    for file_name in product_package.INCLUDE_FILES:
        (root / file_name).parent.mkdir(parents=True, exist_ok=True)
        (root / file_name).write_text(f"{file_name}\n", encoding="utf-8")
    return root


def _existing_tree_sitter_stager(staged_tree_sitter_dir: Path, _cache_dir: Path) -> Path:
    return staged_tree_sitter_dir / product_package.CHOREBOY_PRODUCT_TREE_SITTER_BINDINGS["tree_sitter"]


def test_distribution_install_instructions_require_home_default_staging() -> None:
    instructions = product_package.build_install_instructions()

    assert "/home/default/" in instructions
    assert "application-menu launcher" in instructions
    assert "Desktop shortcut" in instructions
    assert "staged copy" in instructions


def test_distribution_installer_desktop_entry_uses_direct_apprun() -> None:
    desktop_entry = product_package.build_installer_desktop_entry(
        "/home/default/choreboy_code_studio_installer_v0.2"
    )

    assert "/home/default/choreboy_code_studio_installer_v0.2" in desktop_entry
    assert "installer" in desktop_entry
    assert "install.py" in desktop_entry
    assert "/opt/freecad/AppRun" in desktop_entry
    assert "/bin/sh" not in desktop_entry


def test_distribution_archive_budget_is_15_mb() -> None:
    assert product_package.archive_budget_bytes() == 15 * 1024 * 1024
    assert product_package.is_archive_within_budget(15 * 1024 * 1024) is True
    assert product_package.is_archive_within_budget((15 * 1024 * 1024) + 1) is False


def test_distribution_archive_zip_command_uses_compression() -> None:
    command = product_package.build_archive_zip_command(
        Path("/tmp/staging"),
        Path("/tmp/archive.zip"),
        password="release-password",
    )

    assert "-9" in command
    assert "-0" not in command
    assert "archive.zip" in command
    assert "staging" in command
    assert "release-password" in command


def test_distribution_archive_zip_command_requires_explicit_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CBCS_PACKAGE_ZIP_PASSWORD", raising=False)

    with pytest.raises(ValueError, match="CBCS_PACKAGE_ZIP_PASSWORD"):
        product_package.build_archive_zip_command(
            Path("/tmp/staging"),
            Path("/tmp/archive.zip"),
        )


def test_distribution_archive_zip_command_uses_environment_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CBCS_PACKAGE_ZIP_PASSWORD", "env-release-password")

    command = product_package.build_archive_zip_command(
        Path("/tmp/staging"),
        Path("/tmp/archive.zip"),
    )

    assert "env-release-password" in command


def test_suggest_next_version_pads_two_part_to_three_and_bumps_patch() -> None:
    package_module = _load_module("distribution_package_cli", "package.py")

    assert package_module._suggest_next_version("0.2") == "0.2.1"


def test_suggest_next_version_bumps_existing_three_part_patch() -> None:
    package_module = _load_module("distribution_package_cli", "package.py")

    assert package_module._suggest_next_version("0.2.1") == "0.2.2"


def test_suggest_next_version_normalizes_single_component() -> None:
    package_module = _load_module("distribution_package_cli", "package.py")

    assert package_module._suggest_next_version("1") == "1.0.1"


def test_suggest_next_version_returns_input_for_non_numeric() -> None:
    package_module = _load_module("distribution_package_cli", "package.py")

    assert package_module._suggest_next_version("dev") == "dev"


def test_substitute_version_in_text_preserves_quote_style() -> None:
    package_module = _load_module("distribution_package_cli", "package.py")

    double_quoted = 'APP_VERSION = "0.2"\nAPP_RUN_PATH = "/opt/freecad/AppRun"\n'
    single_quoted = "APP_VERSION = '0.2'\nAPP_RUN_PATH = '/opt/freecad/AppRun'\n"

    updated_double = package_module._substitute_version_in_text(double_quoted, "0.2.1")
    updated_single = package_module._substitute_version_in_text(single_quoted, "0.2.1")

    assert 'APP_VERSION = "0.2.1"' in updated_double
    assert 'APP_RUN_PATH = "/opt/freecad/AppRun"' in updated_double
    assert "APP_VERSION = '0.2.1'" in updated_single
    assert "APP_RUN_PATH = '/opt/freecad/AppRun'" in updated_single


def test_substitute_version_in_text_raises_when_missing() -> None:
    package_module = _load_module("distribution_package_cli", "package.py")

    with pytest.raises(RuntimeError, match="APP_VERSION"):
        package_module._substitute_version_in_text('APP_RUN_PATH = "/opt/freecad/AppRun"\n', "0.2.1")


def test_validate_choreboy_tree_sitter_bundle_rejects_wrong_abi(tmp_path: Path) -> None:
    vendor_dir = _stage_tree_sitter_bundle(
        tmp_path,
        product_package,
        core_soabi="cpython-311-x86_64-linux-gnu",
    )

    with pytest.raises(RuntimeError, match="_binding.cpython-39-x86_64-linux-gnu.so"):
        product_package.validate_choreboy_tree_sitter_bundle(vendor_dir)


def test_validate_choreboy_tree_sitter_bundle_rejects_mixed_bindings(tmp_path: Path) -> None:
    vendor_dir = _stage_tree_sitter_bundle(
        tmp_path,
        product_package,
        extra_binding_name="_binding.cpython-311-x86_64-linux-gnu.so",
    )

    with pytest.raises(RuntimeError, match="must contain only _binding.cpython-39-x86_64-linux-gnu.so"):
        product_package.validate_choreboy_tree_sitter_bundle(vendor_dir)


def test_product_report_records_tree_sitter_bundle_contract(tmp_path: Path) -> None:
    vendor_dir = _stage_tree_sitter_bundle(tmp_path, product_package)
    bundle = product_package.validate_choreboy_tree_sitter_bundle(vendor_dir)
    report_path = tmp_path / "package_report.json"

    product_package._write_product_report(
        report_path=report_path,
        manifest=product_package.build_product_manifest(version="0.2.0"),
        archive_path=tmp_path / "archive.zip",
        archive_size_bytes=123,
        tree_sitter_bundle=bundle,
    )

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["tree_sitter_bundle"]["target_soabi"] == product_package.CHOREBOY_PRODUCT_TREE_SITTER_SOABI
    assert payload["tree_sitter_bundle"]["required_packages"] == list(
        product_package.CHOREBOY_PRODUCT_TREE_SITTER_PACKAGES
    )
    assert payload["tree_sitter_bundle"]["required_bindings"]["tree_sitter_python"] == "_binding.abi3.so"


def test_build_product_artifact_writes_manifest_zip_and_no_hidden_runtime_dirs(tmp_path: Path) -> None:
    repo_root = _make_product_repo(tmp_path / "repo")
    artifacts_dir = tmp_path / "artifacts"
    _stage_tree_sitter_bundle(artifacts_dir, product_package)

    result = product_package.build_product_artifact(
        repo_root=repo_root,
        version="0.2.0",
        artifacts_dir=artifacts_dir,
        tree_sitter_core_stager=_existing_tree_sitter_stager,
        strip_shared_objects=False,
        print_status=False,
        archive_password="pw",
    )

    manifest_payload = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    report_payload = json.loads(result.report_path.read_text(encoding="utf-8"))
    checksum_paths = {item["relative_path"] for item in manifest_payload["checksums"]}
    hidden_dirs = [
        path
        for path in result.staging_dir.rglob("*")
        if path.is_dir()
        and any(part.startswith(".") for part in path.relative_to(result.staging_dir).parts)
    ]

    assert result.archive_within_budget is True
    assert manifest_payload["package_kind"] == "product"
    assert manifest_payload["profile"] == "installable"
    assert manifest_payload["entry_relative_path"] == "run_editor.py"
    assert "package_report.json" not in checksum_paths
    assert report_payload["tree_sitter_bundle"]["target_soabi"] == product_package.CHOREBOY_PRODUCT_TREE_SITTER_SOABI
    assert hidden_dirs == []

    with zipfile.ZipFile(result.archive_path) as archive:
        archive_names = set(archive.namelist())
    package_root = result.staging_dir.name
    assert f"{package_root}/package_manifest.json" in archive_names
    assert f"{package_root}/payload/run_editor.py" in archive_names
    assert all(".hidden_cache" not in name for name in archive_names)


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


def test_installed_desktop_entry_must_not_reference_staging_suffix() -> None:
    """Regression: _do_install must pass the final install_dir, not stage_dir.

    The staged-install flow creates a temporary directory named
    ``<install_dir>_installing`` and later renames it to the final path.
    The .desktop entry must embed the *final* path so that Exec= and Icon=
    resolve correctly after the rename.
    """
    installer_module = _load_module("distribution_installer", "packaging/install.py")
    manifest = _build_installer_manifest(installer_module)

    final_install_dir = "/home/default/choreboy_code_studio_v0.2.0"
    desktop_entry = installer_module.build_installed_desktop_entry(
        final_install_dir,
        manifest,
    )

    assert final_install_dir in desktop_entry
    assert "_installing" not in desktop_entry
    assert "Icon=" in desktop_entry
    assert "Python_Icon.png" in desktop_entry
    assert "StartupNotify=true" in desktop_entry


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


def test_directory_page_is_complete_with_default_path(qapp) -> None:
    installer_module = _load_module("distribution_installer", "packaging/install.py")
    manifest = _build_installer_manifest(installer_module)
    page = installer_module.DirectoryPage(manifest)

    assert page.path_edit.text() == installer_module.build_default_install_dir(manifest)
    assert page.isComplete() is True


def test_directory_page_is_not_complete_when_empty(qapp) -> None:
    installer_module = _load_module("distribution_installer", "packaging/install.py")
    manifest = _build_installer_manifest(installer_module)
    page = installer_module.DirectoryPage(manifest)

    page.path_edit.clear()
    assert page.isComplete() is False
