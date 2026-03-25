"""Vendored runtime bootstrap for Python formatting/import tooling."""

from __future__ import annotations

from dataclasses import dataclass
import importlib
from pathlib import Path
from typing import Any

from app.bootstrap.vendor_paths import ensure_vendor_path_on_sys_path


@dataclass(frozen=True)
class PythonToolingRuntimeStatus:
    """Availability information for vendored Python tooling."""

    is_available: bool
    vendor_root: Path
    black_available: bool
    isort_available: bool
    tomli_available: bool
    message: str


def initialize_python_tooling_runtime(app_root: Path | None = None) -> PythonToolingRuntimeStatus:
    """Ensure the vendor directory is importable and probe required modules."""
    vendor_root = ensure_vendor_path_on_sys_path(app_root)
    black_available = _module_available("black")
    isort_available = _module_available("isort")
    tomli_available = _module_available("tomli")
    is_available = black_available and isort_available and tomli_available
    message = "Python tooling runtime ready."
    if not is_available:
        missing = []
        if not black_available:
            missing.append("black")
        if not isort_available:
            missing.append("isort")
        if not tomli_available:
            missing.append("tomli")
        message = f"Missing vendored Python tooling modules: {', '.join(missing)}"
    return PythonToolingRuntimeStatus(
        is_available=is_available,
        vendor_root=vendor_root,
        black_available=black_available,
        isort_available=isort_available,
        tomli_available=tomli_available,
        message=message,
    )


def import_python_tooling_modules(app_root: Path | None = None) -> tuple[Any, Any, Any]:
    """Return imported vendored formatter/import modules."""
    initialize_python_tooling_runtime(app_root)
    black_module = importlib.import_module("black")
    isort_module = importlib.import_module("isort")
    tomli_module = importlib.import_module("tomli")
    return black_module, isort_module, tomli_module


def _module_available(name: str) -> bool:
    try:
        importlib.import_module(name)
    except Exception:
        return False
    return True
