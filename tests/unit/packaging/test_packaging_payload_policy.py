"""Unit tests for packaging payload copy vs audit policy."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.packaging.payload_policy import DEFAULT_PACKAGING_PAYLOAD_POLICY
from tests.unit.project.inventory_parity_fixtures import build_fixture_tree

pytestmark = pytest.mark.unit


def test_payload_policy_copy_vs_audit_matrix(tmp_path: Path) -> None:
    build_fixture_tree(tmp_path, "cbcs_metadata")
    (tmp_path / "vendor").mkdir()
    (tmp_path / "vendor" / "pkg.py").write_text("X = 1\n", encoding="utf-8")
    (tmp_path / "vendor" / "native.so").write_bytes(b"\x7fELF")
    project_root = tmp_path
    (project_root / "assets").mkdir()
    (project_root / "assets" / "logo.png").write_bytes(b"png")
    (project_root / "__pycache__").mkdir()
    (project_root / "__pycache__" / "main.pyc").write_bytes(b"\x00")
    (project_root / ".git").mkdir()
    (project_root / ".git" / "config").write_text("[core]\n", encoding="utf-8")

    policy = DEFAULT_PACKAGING_PAYLOAD_POLICY
    payload_files = {
        path.relative_to(project_root).as_posix()
        for path in policy.iter_payload_entries(project_root)
        if path.is_file()
    }
    audit_python = {
        path.relative_to(project_root).as_posix()
        for path in policy.iter_audit_python_files(project_root)
    }

    assert "main.py" in payload_files
    assert "assets/logo.png" in payload_files
    assert "cbcs/package.json" in payload_files
    assert "vendor/pkg.py" in payload_files
    assert "vendor/native.so" in payload_files

    assert "cbcs/runs/run.log" not in payload_files
    assert "cbcs/logs/app.log" not in payload_files
    assert "cbcs/cache/index.sqlite" not in payload_files
    assert ".git/config" not in payload_files
    assert "__pycache__/main.pyc" not in payload_files

    assert audit_python == {"main.py", "pkg/__init__.py", "pkg/module.py"}
    assert "vendor/pkg.py" not in audit_python
    assert "cbcs/package.json" not in audit_python


def test_payload_policy_prunes_excluded_directories_during_walk(tmp_path: Path) -> None:
    build_fixture_tree(tmp_path, "cbcs_metadata")
    policy = DEFAULT_PACKAGING_PAYLOAD_POLICY

    payload_dirs = {
        path.relative_to(tmp_path).as_posix()
        for path in policy.iter_payload_entries(tmp_path)
        if path.is_dir()
    }

    assert "cbcs" in payload_dirs
    assert "cbcs/runs" not in payload_dirs
    assert "cbcs/logs" not in payload_dirs
    assert "cbcs/cache" not in payload_dirs
