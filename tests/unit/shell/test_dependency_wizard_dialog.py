"""Unit tests for Add Dependency wizard dialog."""
from __future__ import annotations

from pathlib import Path
import zipfile

import pytest

from app.project.dependency_manifest import (
    CLASSIFICATION_NATIVE_EXTENSION,
    CLASSIFICATION_PURE_PYTHON,
    load_dependency_manifest,
)
from app.project.dependency_ingest import classify_package_path

pytestmark = pytest.mark.unit


def _make_wheel(tmp_path: Path, name: str = "sample_pkg", native: bool = False) -> Path:
    wheel_name = f"{name}-1.0.0-py3-none-any.whl"
    wheel_path = tmp_path / wheel_name
    with zipfile.ZipFile(str(wheel_path), "w") as zf:
        zf.writestr(f"{name}/__init__.py", "# sample\n")
        if native:
            zf.writestr(f"{name}/_ext.so", b"fake")
    return wheel_path


def test_classify_pure_python_wheel(tmp_path: Path) -> None:
    wheel = _make_wheel(tmp_path)
    assert classify_package_path(wheel) == CLASSIFICATION_PURE_PYTHON


def test_classify_native_extension_wheel(tmp_path: Path) -> None:
    wheel = _make_wheel(tmp_path, native=True)
    assert classify_package_path(wheel) == CLASSIFICATION_NATIVE_EXTENSION


def test_wizard_ingest_result_fields() -> None:
    """IngestResult dataclass carries expected fields."""
    from app.project.dependency_ingest import IngestResult

    result = IngestResult(
        success=True,
        name="test_pkg",
        version="1.0",
        classification=CLASSIFICATION_PURE_PYTHON,
        vendor_path="vendor/test_pkg",
        message="OK",
    )
    assert result.success is True
    assert result.name == "test_pkg"
