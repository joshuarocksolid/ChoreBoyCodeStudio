#!/usr/bin/env python3
"""Package ChoreBoy Code Studio for distribution."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from app.core import constants
from app.packaging.desktop_builder import (
    build_installable_install_text,
    build_installable_readme_text,
    build_installer_package_launcher,
)
from app.packaging.installer_manifest import (
    apply_checksums_to_manifest,
    build_artifact_checksums,
    create_distribution_manifest,
    save_distribution_manifest,
)
from app.packaging.layout import build_installer_launcher_filename
from app.packaging.models import (
    LAUNCHER_MODE_ABSOLUTE_INSTALL_ROOT,
    PACKAGE_ARTIFACT_MANIFEST_FILENAME,
    PACKAGE_ARTIFACT_REPORT_FILENAME,
    PACKAGE_KIND_PRODUCT,
    PACKAGE_PROFILE_INSTALLABLE,
)
from app.packaging.tree_sitter_cp39 import (
    CP39_TREE_SITTER_SOABI,
    stage_cp39_tree_sitter_core_binding,
)
from app.treesitter.language_specs import LANGUAGE_SPECS

REPO_ROOT = Path(__file__).resolve().parent
ARTIFACTS_DIR = Path(os.environ.get("CBCS_ARTIFACTS_DIR", "") or str(REPO_ROOT.parent / "ChoreBoyCodeStudio_artifacts"))

INCLUDE_DIRS = ["app", "templates", "example_projects"]
INCLUDE_FILES = [
    "run_editor.py",
    "run_runner.py",
    "run_plugin_host.py",
    "launcher.py",
    "LICENSE",
]
PRUNE_DIR_NAMES = {"__pycache__", ".pyc"}
PRUNE_DIR_SUFFIXES = {".dist-info"}
VENDOR_ALLOWLIST = [
    # Formatting
    "black", "blib2to3", "click", "mypy_extensions.py",
    "_black_version.py", "_black_version.pyi",
    "pathspec", "platformdirs", "isort", "tomli",
    # Linting
    "pyflakes",
    # Tree-sitter core + curated grammars
    "tree_sitter", "tree_sitter_python", "tree_sitter_json",
    "tree_sitter_html", "tree_sitter_xml", "tree_sitter_css",
    "tree_sitter_bash", "tree_sitter_markdown", "tree_sitter_yaml",
    "tree_sitter_javascript", "tree_sitter_toml", "tree_sitter_sql",
    # Intelligence (code completion, refactoring)
    "jedi", "parso", "rope", "pytoolconfig",
]
INSTALLER_SOURCE = REPO_ROOT / "packaging" / "install.py"
INSTALLER_ICON_SOURCE = REPO_ROOT / "app" / "ui" / "icons" / "installer_icon.png"
CHOREBOY_STAGING_ROOT = "/home/default"
INSTALLER_ARCHIVE_BUDGET_BYTES = 15 * 1024 * 1024
ZIP_COMPRESSION_LEVEL = 9
ARCHIVE_PASSWORD = os.environ.get("CBCS_PACKAGE_ZIP_PASSWORD", "rsd")
CHOREBOY_PRODUCT_TREE_SITTER_SOABI = CP39_TREE_SITTER_SOABI
CHOREBOY_PRODUCT_TREE_SITTER_PACKAGES = ("tree_sitter",) + tuple(
    spec.package_name for spec in LANGUAGE_SPECS if spec.included_by_default
)
CHOREBOY_PRODUCT_TREE_SITTER_BINDINGS = {
    "tree_sitter": f"_binding.{CHOREBOY_PRODUCT_TREE_SITTER_SOABI}.so",
    **{
        spec.package_name: "_binding.abi3.so"
        for spec in LANGUAGE_SPECS
        if spec.included_by_default
    },
}
CHOREBOY_OPTIONAL_TREE_SITTER_PACKAGES = tuple(
    spec.package_name for spec in LANGUAGE_SPECS if not spec.included_by_default
)
APP_VERSION_PATTERN = re.compile(
    r'^(?P<prefix>\s*APP_VERSION\s*=\s*)(?P<quote>["\'])(?P<version>[^"\']*)(?P=quote)(?P<suffix>.*)$',
    re.MULTILINE,
)


def build_product_manifest(*, version: str, staging_parent: str = CHOREBOY_STAGING_ROOT):
    return create_distribution_manifest(
        package_kind=PACKAGE_KIND_PRODUCT,
        profile=PACKAGE_PROFILE_INSTALLABLE,
        package_id="choreboy_code_studio",
        display_name="ChoreBoy Code Studio",
        version=version,
        description="Project-first editor + runner for constrained systems.",
        entry_relative_path="run_editor.py",
        icon_relative_path="app/ui/icons/Python_Icon.png",
        launcher_mode=LAUNCHER_MODE_ABSOLUTE_INSTALL_ROOT,
        default_install_base=CHOREBOY_STAGING_ROOT,
        default_install_dirname=f"choreboy_code_studio_v{version}",
        staging_parent=staging_parent,
        app_run_path=constants.APP_RUN_PATH,
        write_menu_entry=False,
        write_desktop_shortcut=True,
    )


def build_installer_desktop_entry(staging_path: str) -> str:
    manifest = build_product_manifest(version=_read_version(), staging_parent=str(Path(staging_path).parent))
    return build_installer_package_launcher(
        manifest=manifest,
        package_root_name=Path(staging_path).name,
    )


def build_install_instructions() -> str:
    manifest = build_product_manifest(version=_read_version())
    return build_installable_install_text(
        manifest=manifest,
        installer_launcher_filename=build_installer_launcher_filename(manifest.display_name),
    )


def _read_version() -> str:
    constants_path = REPO_ROOT / "app" / "core" / "constants.py"
    text = constants_path.read_text(encoding="utf-8")
    match = APP_VERSION_PATTERN.search(text)
    return match.group("version") if match else "dev"


def _suggest_next_version(current: str) -> str:
    parts = current.split(".")
    try:
        normalized = [str(int(part)) for part in parts]
    except ValueError:
        return current
    while len(normalized) < 3:
        normalized.append("0")
    normalized[2] = str(int(normalized[2]) + 1)
    return ".".join(normalized)


def _substitute_version_in_text(text: str, new_version: str) -> str:
    def _replace(match: re.Match[str]) -> str:
        return (
            f"{match.group('prefix')}"
            f"{match.group('quote')}{new_version}{match.group('quote')}"
            f"{match.group('suffix')}"
        )

    updated_text, replacements = APP_VERSION_PATTERN.subn(_replace, text, count=1)
    if replacements != 1:
        raise RuntimeError("APP_VERSION assignment not found in app/core/constants.py")
    return updated_text


def _write_version(new_version: str) -> None:
    constants_path = REPO_ROOT / "app" / "core" / "constants.py"
    text = constants_path.read_text(encoding="utf-8")
    updated_text = _substitute_version_in_text(text, new_version)
    constants_path.write_text(updated_text, encoding="utf-8")


def _prompt_version() -> str:
    current = _read_version()
    suggested = _suggest_next_version(current)
    print(f"Current version: {current}")
    new_version = input(f"New version (Enter for '{suggested}'): ").strip()
    if not new_version:
        new_version = suggested
    if new_version != current:
        _write_version(new_version)
        print(f"Version updated: {current} -> {new_version}")
        return new_version
    print(f"Keeping version: {current}")
    return current


def _should_prune_dir(name: str) -> bool:
    if name in PRUNE_DIR_NAMES:
        return True
    return any(name.endswith(suffix) for suffix in PRUNE_DIR_SUFFIXES)


_CPYTHON_SO_EXCLUDE_TAGS = ("cpython-312", "cpython-313", "cpython-314")


def _should_skip_file(name: str) -> bool:
    if name.endswith(".pyc"):
        return True
    if name.endswith(".so"):
        return any(tag in name for tag in _CPYTHON_SO_EXCLUDE_TAGS)
    return False


def _copytree_filtered(src: Path, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for entry in sorted(src.iterdir()):
        if entry.is_dir():
            if _should_prune_dir(entry.name):
                continue
            _copytree_filtered(entry, dst / entry.name)
            continue
        if _should_skip_file(entry.name):
            continue
        shutil.copy2(str(entry), str(dst / entry.name))


def _copy_vendor_allowlisted(vendor_src: Path, vendor_dst: Path) -> list[str]:
    """Copy only allowlisted entries from vendor_src into vendor_dst.

    Returns a list of allowlist entries that were not found in vendor_src.
    """
    vendor_dst.mkdir(parents=True, exist_ok=True)
    missing: list[str] = []
    for entry_name in VENDOR_ALLOWLIST:
        src = vendor_src / entry_name
        if src.is_dir():
            _copytree_filtered(src, vendor_dst / entry_name)
        elif src.is_file():
            shutil.copy2(str(src), str(vendor_dst / entry_name))
        else:
            missing.append(entry_name)
    return missing


def _expected_tree_sitter_binding_name(soabi: str = CHOREBOY_PRODUCT_TREE_SITTER_SOABI) -> str:
    return f"_binding.{soabi}.so"


def validate_choreboy_tree_sitter_bundle(vendor_dir: Path) -> dict[str, object]:
    """Validate that staged tree-sitter extensions match the shipped ChoreBoy ABI."""
    validated_bindings: list[dict[str, str]] = []
    for package_name in CHOREBOY_PRODUCT_TREE_SITTER_PACKAGES:
        expected_binding_name = CHOREBOY_PRODUCT_TREE_SITTER_BINDINGS[package_name]
        package_dir = vendor_dir / package_name
        if not package_dir.is_dir():
            raise RuntimeError(f"missing required ChoreBoy tree-sitter package: {package_dir}")
        candidates = tuple(sorted(path.name for path in package_dir.glob("_binding*.so")))
        if not candidates:
            raise RuntimeError(
                f"missing required binding {expected_binding_name} in {package_dir}"
            )
        if candidates != (expected_binding_name,):
            if expected_binding_name in candidates:
                raise RuntimeError(
                    f"tree-sitter package {package_name} must contain only "
                    f"{expected_binding_name}; found {', '.join(candidates)}"
                )
            raise RuntimeError(
                f"tree-sitter package {package_name} expected {expected_binding_name}; "
                f"found incompatible bindings: {', '.join(candidates)}"
            )
        validated_bindings.append(
            {"package": package_name, "binding": expected_binding_name}
        )
    return {
        "product_target_runtime": "choreboy-freecad-python39",
        "target_soabi": CHOREBOY_PRODUCT_TREE_SITTER_SOABI,
        "required_packages": list(CHOREBOY_PRODUCT_TREE_SITTER_PACKAGES),
        "required_bindings": dict(CHOREBOY_PRODUCT_TREE_SITTER_BINDINGS),
        "optional_packages_not_shipped": list(CHOREBOY_OPTIONAL_TREE_SITTER_PACKAGES),
        "validated_bindings": validated_bindings,
    }


def _strip_shared_objects(root: Path) -> int:
    """Strip debug symbols from all .so files under *root*.

    Returns the number of files successfully stripped.
    """
    stripped = 0
    for so_file in sorted(root.rglob("*.so")):
        result = subprocess.run(
            ["strip", str(so_file)], capture_output=True,
        )
        if result.returncode == 0:
            stripped += 1
    return stripped


def _print_vendor_size_report(vendor_dir: Path) -> None:
    """Print a per-package size breakdown of the staged vendor directory."""
    entries: list[tuple[int, str]] = []
    total = 0
    for child in sorted(vendor_dir.iterdir()):
        if child.is_dir():
            size = sum(f.stat().st_size for f in child.rglob("*") if f.is_file())
        elif child.is_file():
            size = child.stat().st_size
        else:
            continue
        entries.append((size, child.name))
        total += size
    print("Vendor size breakdown:")
    for size, name in sorted(entries, key=lambda t: t[0], reverse=True):
        if size >= 1024 * 1024:
            print(f"  {size / (1024 * 1024):6.1f} MB  {name}")
        else:
            print(f"  {size / 1024:6.0f} KB  {name}")
    print(f"  {'─' * 16}")
    print(f"  {total / (1024 * 1024):6.1f} MB  total vendor")


def archive_budget_bytes() -> int:
    return INSTALLER_ARCHIVE_BUDGET_BYTES


def is_archive_within_budget(size_bytes: int) -> bool:
    return size_bytes <= archive_budget_bytes()


def build_archive_zip_command(source_dir: Path, output_path: Path, password: str = ARCHIVE_PASSWORD) -> list[str]:
    return [
        "zip",
        "-r",
        f"-{ZIP_COMPRESSION_LEVEL}",
        "-P",
        password,
        output_path.name,
        source_dir.name,
    ]


def _make_zip(source_dir: Path, output_path: Path, password: str = ARCHIVE_PASSWORD) -> None:
    if output_path.exists():
        output_path.unlink()
    subprocess.run(
        build_archive_zip_command(source_dir, output_path, password=password),
        cwd=str(source_dir.parent),
        check=True,
    )


def _write_product_report(
    *,
    report_path: Path,
    manifest,
    archive_path: Path,
    archive_size_bytes: int,
    tree_sitter_bundle: dict[str, object],
) -> None:
    report_payload = {
        "package_kind": manifest.package_kind,
        "profile": manifest.profile,
        "package_id": manifest.package_id,
        "display_name": manifest.display_name,
        "version": manifest.version,
        "archive_path": str(archive_path),
        "archive_size_bytes": archive_size_bytes,
        "archive_budget_bytes": archive_budget_bytes(),
        "tree_sitter_bundle": tree_sitter_bundle,
    }
    report_path.write_text(json.dumps(report_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    version = _prompt_version()
    manifest = build_product_manifest(version=version)
    package_name = f"choreboy_code_studio_installer_v{version}"
    installer_launcher_filename = build_installer_launcher_filename(manifest.display_name)

    dist_dir = ARTIFACTS_DIR / "dist"
    staging = dist_dir / package_name
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=True)

    payload_dir = staging / manifest.payload_dirname
    payload_dir.mkdir(parents=True, exist_ok=True)

    for dir_name in INCLUDE_DIRS:
        src = REPO_ROOT / dir_name
        if not src.is_dir():
            print(f"WARNING: missing include dir: {dir_name}")
            continue
        _copytree_filtered(src, payload_dir / dir_name)

    vendor_src = ARTIFACTS_DIR / "vendor"
    if not vendor_src.is_dir():
        print(f"ERROR: vendor directory not found at {vendor_src}")
        print("Set CBCS_ARTIFACTS_DIR or place vendor/ in the artifacts directory.")
        return 1
    vendor_missing = _copy_vendor_allowlisted(vendor_src, payload_dir / "vendor")
    for name in vendor_missing:
        print(f"WARNING: allowlisted vendor entry not found: {name}")
    cp39_cache_dir = ARTIFACTS_DIR / "vendor_cp39_cache"
    staged_cp39_binding = stage_cp39_tree_sitter_core_binding(
        payload_dir / "vendor" / "tree_sitter",
        cp39_cache_dir,
    )
    print(f"Staged cp39 tree-sitter core binding: {staged_cp39_binding.name}")
    tree_sitter_bundle = validate_choreboy_tree_sitter_bundle(payload_dir / "vendor")
    print(
        "Validated ChoreBoy tree-sitter bundle: "
        f"{tree_sitter_bundle['target_soabi']} "
        f"({len(tree_sitter_bundle['validated_bindings'])} bindings)"
    )
    stripped = _strip_shared_objects(payload_dir / "vendor")
    print(f"Stripped debug symbols from {stripped} .so file(s)")
    _print_vendor_size_report(payload_dir / "vendor")

    for file_name in INCLUDE_FILES:
        src = REPO_ROOT / file_name
        if not src.is_file():
            print(f"WARNING: missing include file: {file_name}")
            continue
        shutil.copy2(str(src), str(payload_dir / file_name))

    installer_dir = staging / manifest.installer_dirname
    installer_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(INSTALLER_SOURCE), str(installer_dir / "install.py"))

    installer_icon_value = ""
    if INSTALLER_ICON_SOURCE.is_file():
        installer_icon_filename = INSTALLER_ICON_SOURCE.name
        shutil.copy2(str(INSTALLER_ICON_SOURCE), str(staging / installer_icon_filename))
        installer_icon_value = f"{CHOREBOY_STAGING_ROOT}/{package_name}/{installer_icon_filename}"
    else:
        print(f"WARNING: installer icon not found: {INSTALLER_ICON_SOURCE}")

    installer_launcher_path = staging / installer_launcher_filename
    installer_launcher_path.write_text(
        build_installer_package_launcher(
            manifest=manifest,
            package_root_name=package_name,
            icon_value=installer_icon_value,
        ),
        encoding="utf-8",
    )
    installer_launcher_path.chmod(installer_launcher_path.stat().st_mode | 0o755)

    (staging / manifest.readme_filename).write_text(
        build_installable_readme_text(
            manifest=manifest,
            installer_launcher_filename=installer_launcher_filename,
        ),
        encoding="utf-8",
    )
    (staging / manifest.install_notes_filename).write_text(
        build_installable_install_text(
            manifest=manifest,
            installer_launcher_filename=installer_launcher_filename,
        ),
        encoding="utf-8",
    )

    report_path = staging / PACKAGE_ARTIFACT_REPORT_FILENAME
    report_path.write_text("{}", encoding="utf-8")
    checksums = build_artifact_checksums(
        staging,
        skip_relative_paths=(PACKAGE_ARTIFACT_MANIFEST_FILENAME, PACKAGE_ARTIFACT_REPORT_FILENAME),
    )
    manifest = apply_checksums_to_manifest(manifest, checksums)
    save_distribution_manifest(staging / PACKAGE_ARTIFACT_MANIFEST_FILENAME, manifest)

    archive_path = dist_dir / f"{package_name}.zip"
    _make_zip(staging, archive_path)
    archive_size_bytes = archive_path.stat().st_size
    _write_product_report(
        report_path=report_path,
        manifest=manifest,
        archive_path=archive_path,
        archive_size_bytes=archive_size_bytes,
        tree_sitter_bundle=tree_sitter_bundle,
    )

    archive_size_mb = archive_size_bytes / (1024 * 1024)
    budget_mb = archive_budget_bytes() / (1024 * 1024)
    print(f"Directory: {staging}")
    print(f"Archive:   {archive_path} ({archive_size_mb:.1f} MB)")
    print(f"Budget:    {budget_mb:.1f} MB maximum for email delivery")
    if not is_archive_within_budget(archive_size_bytes):
        print(f"ERROR: Archive exceeds the email budget ({archive_size_mb:.1f} MB > {budget_mb:.1f} MB).")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
