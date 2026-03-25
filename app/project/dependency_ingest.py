"""Terminal-free dependency ingestion helpers for ChoreBoy projects."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import zipfile

from app.project.dependency_manifest import (
    CLASSIFICATION_NATIVE_EXTENSION,
    CLASSIFICATION_PURE_PYTHON,
    DependencyEntry,
    DependencyManifest,
    SOURCE_FOLDER,
    SOURCE_WHEEL,
    SOURCE_ZIP,
    load_dependency_manifest,
    save_dependency_manifest,
)

_COMPILED_EXTENSION_SUFFIXES = frozenset({".so", ".pyd", ".dll", ".dylib"})


@dataclass(frozen=True)
class IngestResult:
    """Outcome of one dependency ingestion operation."""

    success: bool
    name: str
    version: str
    classification: str
    vendor_path: str
    message: str


def classify_package_path(source_path: Path) -> str:
    """Determine if a package path contains native extensions."""
    if source_path.is_file():
        if source_path.suffix == ".whl":
            return _classify_wheel(source_path)
        if source_path.suffix == ".zip":
            return _classify_zip(source_path)
    elif source_path.is_dir():
        return _classify_directory(source_path)
    return CLASSIFICATION_PURE_PYTHON


def ingest_wheel(
    *,
    project_root: str,
    wheel_path: str,
    name: str | None = None,
    version: str | None = None,
) -> IngestResult:
    """Extract a .whl file into vendor/ and update the manifest."""
    source = Path(wheel_path).expanduser().resolve()
    if not source.is_file() or source.suffix != ".whl":
        return IngestResult(False, "", "", "", "", f"Not a valid wheel file: {wheel_path}")

    inferred_name, inferred_version = _parse_wheel_filename(source.name)
    effective_name = name or inferred_name
    effective_version = version or inferred_version
    classification = _classify_wheel(source)

    vendor_dir = _ensure_vendor_dir(project_root)
    target_dir = vendor_dir / effective_name
    if target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(str(source), "r") as zf:
            zf.extractall(str(target_dir))
    except (zipfile.BadZipFile, OSError) as exc:
        return IngestResult(False, effective_name, effective_version, classification, "", f"Extraction failed: {exc}")

    relative_vendor_path = f"vendor/{effective_name}"
    _update_manifest(project_root, effective_name, effective_version, SOURCE_WHEEL, classification, relative_vendor_path)
    return IngestResult(True, effective_name, effective_version, classification, relative_vendor_path, "Wheel ingested successfully.")


def ingest_zip(
    *,
    project_root: str,
    zip_path: str,
    name: str,
    version: str = "",
) -> IngestResult:
    """Extract a .zip file containing Python packages into vendor/."""
    source = Path(zip_path).expanduser().resolve()
    if not source.is_file() or source.suffix != ".zip":
        return IngestResult(False, name, version, "", "", f"Not a valid zip file: {zip_path}")

    classification = _classify_zip(source)
    vendor_dir = _ensure_vendor_dir(project_root)
    target_dir = vendor_dir / name
    if target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(str(source), "r") as zf:
            zf.extractall(str(target_dir))
    except (zipfile.BadZipFile, OSError) as exc:
        return IngestResult(False, name, version, classification, "", f"Extraction failed: {exc}")

    relative_vendor_path = f"vendor/{name}"
    _update_manifest(project_root, name, version, SOURCE_ZIP, classification, relative_vendor_path)
    return IngestResult(True, name, version, classification, relative_vendor_path, "Zip package ingested successfully.")


def ingest_folder(
    *,
    project_root: str,
    folder_path: str,
    name: str | None = None,
    version: str = "",
) -> IngestResult:
    """Copy a folder into vendor/ and update the manifest."""
    source = Path(folder_path).expanduser().resolve()
    if not source.is_dir():
        return IngestResult(False, name or "", version, "", "", f"Not a valid directory: {folder_path}")

    effective_name = name or source.name
    classification = _classify_directory(source)
    vendor_dir = _ensure_vendor_dir(project_root)
    target_dir = vendor_dir / effective_name
    if target_dir.exists():
        shutil.rmtree(target_dir)
    shutil.copytree(str(source), str(target_dir))

    relative_vendor_path = f"vendor/{effective_name}"
    _update_manifest(project_root, effective_name, version, SOURCE_FOLDER, classification, relative_vendor_path)
    return IngestResult(True, effective_name, version, classification, relative_vendor_path, "Folder ingested successfully.")


def remove_vendored_dependency(*, project_root: str, name: str, delete_files: bool = False) -> bool:
    """Mark a dependency as removed and optionally delete vendor files."""
    manifest = load_dependency_manifest(project_root)
    entry = manifest.find_by_name(name)
    if entry is None:
        return False

    if delete_files and entry.vendor_path:
        vendor_path = Path(project_root).expanduser().resolve() / entry.vendor_path
        if vendor_path.exists():
            shutil.rmtree(str(vendor_path))

    manifest.remove_entry(name)
    save_dependency_manifest(project_root, manifest)
    return True


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _ensure_vendor_dir(project_root: str) -> Path:
    vendor_dir = Path(project_root).expanduser().resolve() / "vendor"
    vendor_dir.mkdir(parents=True, exist_ok=True)
    return vendor_dir


def _parse_wheel_filename(filename: str) -> tuple[str, str]:
    """Parse name and version from a PEP 427 wheel filename."""
    parts = filename.split("-")
    if len(parts) >= 2:
        return parts[0], parts[1]
    return filename.removesuffix(".whl"), ""


def _classify_wheel(wheel_path: Path) -> str:
    try:
        with zipfile.ZipFile(str(wheel_path), "r") as zf:
            for name in zf.namelist():
                if any(name.endswith(suffix) for suffix in _COMPILED_EXTENSION_SUFFIXES):
                    return CLASSIFICATION_NATIVE_EXTENSION
    except (zipfile.BadZipFile, OSError):
        pass
    return CLASSIFICATION_PURE_PYTHON


def _classify_zip(zip_path: Path) -> str:
    try:
        with zipfile.ZipFile(str(zip_path), "r") as zf:
            for name in zf.namelist():
                if any(name.endswith(suffix) for suffix in _COMPILED_EXTENSION_SUFFIXES):
                    return CLASSIFICATION_NATIVE_EXTENSION
    except (zipfile.BadZipFile, OSError):
        pass
    return CLASSIFICATION_PURE_PYTHON


def _classify_directory(dir_path: Path) -> str:
    for child in dir_path.rglob("*"):
        if child.suffix in _COMPILED_EXTENSION_SUFFIXES:
            return CLASSIFICATION_NATIVE_EXTENSION
    return CLASSIFICATION_PURE_PYTHON


def _update_manifest(
    project_root: str,
    name: str,
    version: str,
    source: str,
    classification: str,
    vendor_path: str,
) -> None:
    manifest = load_dependency_manifest(project_root)
    manifest.add_entry(
        DependencyEntry(
            name=name,
            version=version,
            source=source,
            classification=classification,
            vendor_path=vendor_path,
        )
    )
    save_dependency_manifest(project_root, manifest)
