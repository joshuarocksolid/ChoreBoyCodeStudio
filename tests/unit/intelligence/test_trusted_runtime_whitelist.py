"""Unit tests for shared trusted runtime whitelist policy."""

from __future__ import annotations

import importlib

import pytest

from app.intelligence.trusted_runtime_whitelist import is_whitelisted_target_path

pytestmark = pytest.mark.unit


def test_is_whitelisted_target_path_accepts_trusted_modules() -> None:
    assert is_whitelisted_target_path("PySide2.QtCore")
    assert is_whitelisted_target_path("FreeCAD")
    assert is_whitelisted_target_path("FreeCADGui")
    assert not is_whitelisted_target_path("os.path")


def test_runtime_introspection_imports_without_runner_cycle() -> None:
    importlib.import_module("app.intelligence.runtime_introspection")
    importlib.import_module("app.runner.repl_completion")
