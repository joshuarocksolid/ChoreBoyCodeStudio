"""Runtime-parity tests for tree-sitter startup under FreeCAD AppRun."""

from __future__ import annotations

from pathlib import Path
import os
import sysconfig

import pytest

from app.core import constants
import app.treesitter.loader as loader

pytestmark = pytest.mark.runtime_parity

REPO_ROOT = Path(__file__).resolve().parents[3]


def _require_apprun() -> None:
    app_run = Path(constants.APP_RUN_PATH)
    if not app_run.exists():
        pytest.skip(f"AppRun not available at {app_run}; skipping tree-sitter runtime parity tests.")
    if not os.access(str(app_run), os.X_OK):
        pytest.skip(f"AppRun exists but is not executable at {app_run}; skipping tree-sitter runtime parity tests.")


def _require_runtime_matching_bundle() -> Path:
    soabi = sysconfig.get_config_var("SOABI")
    if not isinstance(soabi, str) or not soabi.strip():
        pytest.skip("Current runtime does not report SOABI; skipping tree-sitter runtime parity tests.")
    expected_binding = REPO_ROOT / "vendor" / "tree_sitter" / f"_binding.{soabi}.so"
    if not expected_binding.is_file():
        pytest.skip(
            "Tree-sitter runtime parity requires a vendor bundle built for "
            f"SOABI {soabi}; expected {expected_binding}."
        )
    return expected_binding


def _reset_loader_state() -> None:
    loader._RUNTIME_INITIALIZED = False
    loader._RUNTIME_STATUS = loader.TreeSitterRuntimeStatus(False, "not_initialized")
    loader._RUNTIME_TRACEBACK = None
    loader._TREE_SITTER_MODULE = None
    loader._LANGUAGE_MODULES = {}


def test_tree_sitter_runtime_initializes_with_exact_vendor_bundle() -> None:
    _require_apprun()
    _require_runtime_matching_bundle()
    _reset_loader_state()

    status = loader.initialize_tree_sitter_runtime(app_root=REPO_ROOT)

    assert status.is_available is True, (
        f"{status.message}\n{loader.runtime_traceback() or ''}"
    )
    assert "python" in status.available_language_keys
    assert status.missing_default_language_keys == ()
