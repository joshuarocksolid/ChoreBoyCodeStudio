"""Product distribution builder for ChoreBoy Code Studio."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Callable, Iterable, Sequence, cast

from app.core import constants
from app.packaging.artifact_builder import write_installable_artifact_tree
from app.packaging.desktop_builder import (
    build_installable_install_text,
    build_installer_package_launcher,
)
from app.packaging.installer_manifest import create_distribution_manifest
from app.packaging.layout import build_installer_launcher_filename
from app.packaging.models import (
    DistributionManifest,
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

INCLUDE_DIRS = ("app", "templates", "example_projects")
INCLUDE_FILES = (
    "run_editor.py",
    "run_runner.py",
    "run_plugin_host.py",
    "launcher.py",
    "LICENSE",
)
PRUNE_DIR_NAMES = {"__pycache__", ".pyc"}
PRUNE_DIR_SUFFIXES = {".dist-info"}
VENDOR_ALLOWLIST = (
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
)
CHOREBOY_STAGING_ROOT = "/home/default"
INSTALLER_ARCHIVE_BUDGET_BYTES = 15 * 1024 * 1024
ZIP_COMPRESSION_LEVEL = 9
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
_CPYTHON_SO_EXCLUDE_TAGS = ("cpython-312", "cpython-313", "cpython-314")


@dataclass(frozen=True)
class ProductArtifactResult:
    staging_dir: Path
    archive_path: Path
    manifest_path: Path
    report_path: Path
    archive_size_bytes: int
    archive_budget_bytes: int
    archive_within_budget: bool
    tree_sitter_bundle: dict[str, object]
    warnings: tuple[str, ...] = ()


TreeSitterCoreStager = Callable[[Path, Path], Path]


def default_artifacts_dir(repo_root: Path) -> Path:
    configured = os.environ.get("CBCS_ARTIFACTS_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return (repo_root.parent / "ChoreBoyCodeStudio_artifacts").resolve()


def build_product_manifest(
    *,
    version: str,
    staging_parent: str = CHOREBOY_STAGING_ROOT,
) -> DistributionManifest:
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


def build_installer_desktop_entry(staging_path: str, *, version: str | None = None) -> str:
    manifest = build_product_manifest(
        version=version or constants.APP_VERSION,
        staging_parent=str(Path(staging_path).parent),
    )
    return build_installer_package_launcher(
        manifest=manifest,
        package_root_name=Path(staging_path).name,
    )


def build_install_instructions(*, version: str | None = None) -> str:
    manifest = build_product_manifest(version=version or constants.APP_VERSION)
    return build_installable_install_text(
        manifest=manifest,
        installer_launcher_filename=build_installer_launcher_filename(manifest.display_name),
    )


def archive_budget_bytes() -> int:
    return INSTALLER_ARCHIVE_BUDGET_BYTES


def is_archive_within_budget(size_bytes: int) -> bool:
    return size_bytes <= archive_budget_bytes()


def build_archive_zip_command(
    source_dir: Path,
    output_path: Path,
    *,
    password: str | None = None,
) -> list[str]:
    return [
        "zip",
        "-r",
        f"-{ZIP_COMPRESSION_LEVEL}",
        "-P",
        password if password is not None else os.environ.get("CBCS_PACKAGE_ZIP_PASSWORD", "rsd"),
        output_path.name,
        source_dir.name,
    ]


def build_product_artifact(
    *,
    repo_root: Path,
    version: str,
    artifacts_dir: Path | None = None,
    include_dirs: Sequence[str] = INCLUDE_DIRS,
    include_files: Sequence[str] = INCLUDE_FILES,
    vendor_allowlist: Sequence[str] = VENDOR_ALLOWLIST,
    staging_parent: str = CHOREBOY_STAGING_ROOT,
    archive_password: str | None = None,
    tree_sitter_core_stager: TreeSitterCoreStager = stage_cp39_tree_sitter_core_binding,
    strip_shared_objects: bool = True,
    print_status: bool = True,
) -> ProductArtifactResult:
    """Build the product installer tree and password-protected release archive."""
    root = repo_root.expanduser().resolve()
    output_root = artifacts_dir.expanduser().resolve() if artifacts_dir is not None else default_artifacts_dir(root)
    dist_dir = output_root / "dist"
    package_name = f"choreboy_code_studio_installer_v{version}"
    staging = dist_dir / package_name
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=True)

    manifest = build_product_manifest(version=version, staging_parent=staging_parent)
    warnings: list[str] = []
    tree_sitter_bundle: dict[str, object] = {}

    installer_icon_value = ""
    installer_icon_source = root / "app" / "ui" / "icons" / "installer_icon.png"
    if installer_icon_source.is_file():
        installer_icon_filename = installer_icon_source.name
        shutil.copy2(str(installer_icon_source), str(staging / installer_icon_filename))
        installer_icon_value = f"{staging_parent}/{package_name}/{installer_icon_filename}"
    else:
        warnings.append(f"installer icon not found: {installer_icon_source}")

    def _copy_product_payload(payload_dir: Path) -> None:
        nonlocal tree_sitter_bundle
        for dir_name in include_dirs:
            src = root / dir_name
            if not src.is_dir():
                warnings.append(f"missing include dir: {dir_name}")
                continue
            _copytree_filtered(src, payload_dir / dir_name)

        vendor_src = output_root / "vendor"
        if not vendor_src.is_dir():
            raise RuntimeError(
                f"vendor directory not found at {vendor_src}. "
                "Set CBCS_ARTIFACTS_DIR or place vendor/ in the artifacts directory."
            )
        vendor_missing = _copy_vendor_allowlisted(
            vendor_src,
            payload_dir / "vendor",
            vendor_allowlist=vendor_allowlist,
        )
        for name in vendor_missing:
            warnings.append(f"allowlisted vendor entry not found: {name}")

        cp39_cache_dir = output_root / "vendor_cp39_cache"
        staged_cp39_binding = tree_sitter_core_stager(
            payload_dir / "vendor" / "tree_sitter",
            cp39_cache_dir,
        )
        if print_status:
            print(f"Staged cp39 tree-sitter core binding: {staged_cp39_binding.name}")
        tree_sitter_bundle = validate_choreboy_tree_sitter_bundle(payload_dir / "vendor")
        if print_status:
            validated_bindings = cast(Sequence[object], tree_sitter_bundle["validated_bindings"])
            print(
                "Validated ChoreBoy tree-sitter bundle: "
                f"{tree_sitter_bundle['target_soabi']} "
                f"({len(validated_bindings)} bindings)"
            )
        if strip_shared_objects:
            stripped = _strip_shared_objects(payload_dir / "vendor")
            if print_status:
                print(f"Stripped debug symbols from {stripped} .so file(s)")
        if print_status:
            _print_vendor_size_report(payload_dir / "vendor")

        for file_name in include_files:
            src = root / file_name
            if not src.is_file():
                warnings.append(f"missing include file: {file_name}")
                continue
            shutil.copy2(str(src), str(payload_dir / file_name))

    written = write_installable_artifact_tree(
        artifact_root=staging,
        manifest=manifest,
        package_root_name=package_name,
        copy_payload=_copy_product_payload,
        report_payload={},
        checksum_skip_relative_paths=(
            PACKAGE_ARTIFACT_MANIFEST_FILENAME,
            PACKAGE_ARTIFACT_REPORT_FILENAME,
        ),
        installer_icon_value=installer_icon_value,
        installer_source=root / "packaging" / "install.py",
        launcher_executable=True,
    )

    archive_path = dist_dir / f"{package_name}.zip"
    _make_zip(staging, archive_path, password=archive_password)
    archive_size_bytes = archive_path.stat().st_size
    _write_product_report(
        report_path=written.report_path,
        manifest=written.manifest,
        archive_path=archive_path,
        archive_size_bytes=archive_size_bytes,
        tree_sitter_bundle=tree_sitter_bundle,
    )

    return ProductArtifactResult(
        staging_dir=staging,
        archive_path=archive_path,
        manifest_path=written.manifest_path,
        report_path=written.report_path,
        archive_size_bytes=archive_size_bytes,
        archive_budget_bytes=archive_budget_bytes(),
        archive_within_budget=is_archive_within_budget(archive_size_bytes),
        tree_sitter_bundle=tree_sitter_bundle,
        warnings=tuple(warnings),
    )


def _should_prune_dir(name: str) -> bool:
    if name.startswith("."):
        return True
    if name in PRUNE_DIR_NAMES:
        return True
    return any(name.endswith(suffix) for suffix in PRUNE_DIR_SUFFIXES)


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


def _copy_vendor_allowlisted(
    vendor_src: Path,
    vendor_dst: Path,
    *,
    vendor_allowlist: Iterable[str] = VENDOR_ALLOWLIST,
) -> list[str]:
    """Copy only allowlisted entries from vendor_src into vendor_dst."""
    vendor_dst.mkdir(parents=True, exist_ok=True)
    missing: list[str] = []
    for entry_name in vendor_allowlist:
        src = vendor_src / entry_name
        if src.is_dir():
            _copytree_filtered(src, vendor_dst / entry_name)
        elif src.is_file():
            shutil.copy2(str(src), str(vendor_dst / entry_name))
        else:
            missing.append(entry_name)
    return missing


def _expected_tree_sitter_binding_name(
    soabi: str = CHOREBOY_PRODUCT_TREE_SITTER_SOABI,
) -> str:
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
    """Strip debug symbols from all .so files under *root*."""
    stripped = 0
    for so_file in sorted(root.rglob("*.so")):
        result = subprocess.run(
            ["strip", str(so_file)],
            capture_output=True,
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
    for size, name in sorted(entries, key=lambda item: item[0], reverse=True):
        if size >= 1024 * 1024:
            print(f"  {size / (1024 * 1024):6.1f} MB  {name}")
        else:
            print(f"  {size / 1024:6.0f} KB  {name}")
    print(f"  {'-' * 16}")
    print(f"  {total / (1024 * 1024):6.1f} MB  total vendor")


def _make_zip(
    source_dir: Path,
    output_path: Path,
    *,
    password: str | None = None,
) -> None:
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
    manifest: DistributionManifest,
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
    report_path.write_text(
        json.dumps(report_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
