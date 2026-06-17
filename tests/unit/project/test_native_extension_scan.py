"""Unit tests for shared native-extension scan primitives."""

from __future__ import annotations

from pathlib import Path
import zipfile

import pytest

from app.project.native_extension_scan import (
    import_resolves_to_native,
    is_native_artifact_path,
    iter_native_artifacts_in_tree,
    scan_archive_namelist,
    tree_contains_native_artifacts,
)
from app.project.dependency_classifier import has_compiled_extension_candidate

pytestmark = pytest.mark.unit


def test_is_native_artifact_path_recognizes_compiled_suffixes(tmp_path: Path) -> None:
    so_file = tmp_path / "module.so"
    so_file.write_bytes(b"")
    pyd_file = tmp_path / "module.PYD"
    pyd_file.write_bytes(b"")
    py_file = tmp_path / "module.py"
    py_file.write_text("", encoding="utf-8")

    assert is_native_artifact_path(so_file) is True
    assert is_native_artifact_path(pyd_file) is True
    assert is_native_artifact_path(py_file) is False


def test_tree_contains_native_artifacts_and_iter_paths(tmp_path: Path) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "_core.so").write_bytes(b"")
    (tmp_path / "readme.txt").write_text("x", encoding="utf-8")

    assert tree_contains_native_artifacts(tmp_path) is True
    assert list(iter_native_artifacts_in_tree(tmp_path)) == [tmp_path / "pkg" / "_core.so"]


def test_scan_archive_namelist_detects_native_members(tmp_path: Path) -> None:
    wheel_path = tmp_path / "sample.whl"
    with zipfile.ZipFile(str(wheel_path), "w") as zf:
        zf.writestr("sample/__init__.py", "")
        zf.writestr("sample/_native.so", b"")

    with zipfile.ZipFile(str(wheel_path), "r") as zf:
        assert scan_archive_namelist(zf.namelist()) is True


def test_import_resolves_to_native_matches_classifier_helper(tmp_path: Path) -> None:
    (tmp_path / "fastlib.cpython-39-x86_64-linux-gnu.so").write_bytes(b"")
    package_dir = tmp_path / "fastlib"
    package_dir.mkdir()
    (package_dir / "_internal.so").write_bytes(b"")

    assert import_resolves_to_native(tmp_path, "fastlib") is True
    assert has_compiled_extension_candidate(tmp_path, "fastlib") is True
    assert import_resolves_to_native(tmp_path, "puremod") is False
