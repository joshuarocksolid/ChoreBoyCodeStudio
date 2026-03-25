"""Unit tests for terminal-free dependency ingestion helpers."""
from __future__ import annotations

from pathlib import Path
import zipfile

import pytest

from app.project.dependency_ingest import (
    IngestResult,
    classify_package_path,
    ingest_folder,
    ingest_wheel,
    ingest_zip,
    remove_vendored_dependency,
)
from app.project.dependency_manifest import (
    CLASSIFICATION_NATIVE_EXTENSION,
    CLASSIFICATION_PURE_PYTHON,
    STATUS_ACTIVE,
    STATUS_REMOVED,
    load_dependency_manifest,
)

pytestmark = pytest.mark.unit


def _make_wheel(tmp_path: Path, name: str = "sample_pkg", version: str = "1.0.0", native: bool = False) -> Path:
    """Create a minimal .whl file for testing."""
    wheel_name = f"{name}-{version}-py3-none-any.whl"
    wheel_path = tmp_path / wheel_name
    with zipfile.ZipFile(str(wheel_path), "w") as zf:
        zf.writestr(f"{name}/__init__.py", "# sample package\n")
        zf.writestr(f"{name}/core.py", "def hello():\n    return 'hello'\n")
        if native:
            zf.writestr(f"{name}/_native.so", b"fake native extension")
    return wheel_path


def _make_zip(tmp_path: Path, name: str = "sample_pkg", native: bool = False) -> Path:
    """Create a minimal .zip file for testing."""
    zip_path = tmp_path / f"{name}.zip"
    with zipfile.ZipFile(str(zip_path), "w") as zf:
        zf.writestr(f"{name}/__init__.py", "# sample package\n")
        if native:
            zf.writestr(f"{name}/_ext.pyd", b"fake native")
    return zip_path


def _make_folder(tmp_path: Path, name: str = "sample_pkg", native: bool = False) -> Path:
    """Create a minimal package folder for testing."""
    pkg_dir = tmp_path / "source_packages" / name
    pkg_dir.mkdir(parents=True)
    (pkg_dir / "__init__.py").write_text("# sample\n")
    (pkg_dir / "core.py").write_text("def hello():\n    return 'hello'\n")
    if native:
        (pkg_dir / "_ext.so").write_bytes(b"fake native")
    return pkg_dir


def _project_root(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    project.mkdir()
    (project / "cbcs").mkdir()
    return project


# ---------------------------------------------------------------------------
# Classification tests
# ---------------------------------------------------------------------------


def test_classify_pure_python_wheel(tmp_path: Path) -> None:
    wheel = _make_wheel(tmp_path)
    assert classify_package_path(wheel) == CLASSIFICATION_PURE_PYTHON


def test_classify_native_wheel(tmp_path: Path) -> None:
    wheel = _make_wheel(tmp_path, native=True)
    assert classify_package_path(wheel) == CLASSIFICATION_NATIVE_EXTENSION


def test_classify_pure_python_folder(tmp_path: Path) -> None:
    folder = _make_folder(tmp_path)
    assert classify_package_path(folder) == CLASSIFICATION_PURE_PYTHON


def test_classify_native_folder(tmp_path: Path) -> None:
    folder = _make_folder(tmp_path, native=True)
    assert classify_package_path(folder) == CLASSIFICATION_NATIVE_EXTENSION


# ---------------------------------------------------------------------------
# Wheel ingestion tests
# ---------------------------------------------------------------------------


def test_ingest_wheel_extracts_to_vendor_and_updates_manifest(tmp_path: Path) -> None:
    project = _project_root(tmp_path)
    wheel = _make_wheel(tmp_path)

    result = ingest_wheel(project_root=str(project), wheel_path=str(wheel))

    assert result.success is True
    assert result.name == "sample_pkg"
    assert result.version == "1.0.0"
    assert result.classification == CLASSIFICATION_PURE_PYTHON
    assert (project / "vendor" / "sample_pkg" / "sample_pkg" / "__init__.py").exists()

    manifest = load_dependency_manifest(str(project))
    entry = manifest.find_by_name("sample_pkg")
    assert entry is not None
    assert entry.status == STATUS_ACTIVE


def test_ingest_wheel_rejects_non_wheel_file(tmp_path: Path) -> None:
    project = _project_root(tmp_path)
    fake = tmp_path / "not_a_wheel.txt"
    fake.write_text("not a wheel")

    result = ingest_wheel(project_root=str(project), wheel_path=str(fake))
    assert result.success is False


# ---------------------------------------------------------------------------
# Zip ingestion tests
# ---------------------------------------------------------------------------


def test_ingest_zip_extracts_and_updates_manifest(tmp_path: Path) -> None:
    project = _project_root(tmp_path)
    zip_file = _make_zip(tmp_path)

    result = ingest_zip(project_root=str(project), zip_path=str(zip_file), name="sample_pkg", version="1.0")

    assert result.success is True
    assert (project / "vendor" / "sample_pkg" / "sample_pkg" / "__init__.py").exists()

    manifest = load_dependency_manifest(str(project))
    assert manifest.find_by_name("sample_pkg") is not None


# ---------------------------------------------------------------------------
# Folder ingestion tests
# ---------------------------------------------------------------------------


def test_ingest_folder_copies_and_updates_manifest(tmp_path: Path) -> None:
    project = _project_root(tmp_path)
    folder = _make_folder(tmp_path)

    result = ingest_folder(project_root=str(project), folder_path=str(folder))

    assert result.success is True
    assert (project / "vendor" / "sample_pkg" / "__init__.py").exists()

    manifest = load_dependency_manifest(str(project))
    assert manifest.find_by_name("sample_pkg") is not None


def test_ingest_folder_rejects_nonexistent_path(tmp_path: Path) -> None:
    project = _project_root(tmp_path)
    result = ingest_folder(project_root=str(project), folder_path=str(tmp_path / "nonexistent"))
    assert result.success is False


# ---------------------------------------------------------------------------
# Removal tests
# ---------------------------------------------------------------------------


def test_remove_vendored_dependency_marks_as_removed(tmp_path: Path) -> None:
    project = _project_root(tmp_path)
    wheel = _make_wheel(tmp_path)
    ingest_wheel(project_root=str(project), wheel_path=str(wheel))

    result = remove_vendored_dependency(project_root=str(project), name="sample_pkg", delete_files=False)

    assert result is True
    manifest = load_dependency_manifest(str(project))
    assert manifest.find_by_name("sample_pkg").status == STATUS_REMOVED
    # Files should still exist since delete_files=False
    assert (project / "vendor" / "sample_pkg").exists()


def test_remove_vendored_dependency_deletes_files_when_requested(tmp_path: Path) -> None:
    project = _project_root(tmp_path)
    wheel = _make_wheel(tmp_path)
    ingest_wheel(project_root=str(project), wheel_path=str(wheel))

    result = remove_vendored_dependency(project_root=str(project), name="sample_pkg", delete_files=True)

    assert result is True
    assert not (project / "vendor" / "sample_pkg").exists()


def test_remove_nonexistent_dependency_returns_false(tmp_path: Path) -> None:
    project = _project_root(tmp_path)
    result = remove_vendored_dependency(project_root=str(project), name="nonexistent")
    assert result is False
