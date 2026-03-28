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
    black_error: str | None = None
    isort_error: str | None = None
    tomli_error: str | None = None
    black_missing_apis: tuple[str, ...] = ()
    isort_missing_apis: tuple[str, ...] = ()


_REQUIRED_BLACK_APIS: tuple[str, ...] = (
    "Mode",
    "format_file_contents",
    "NothingChanged",
    "InvalidInput",
)
_REQUIRED_ISORT_APIS: tuple[str, ...] = (
    "Config",
    "api",
    "api.sort_code_string",
)


def initialize_python_tooling_runtime(app_root: Path | None = None) -> PythonToolingRuntimeStatus:
    """Ensure the vendor directory is importable and probe required modules."""
    vendor_root = ensure_vendor_path_on_sys_path(app_root)
    black_module, black_error = _import_module("black")
    isort_module, isort_error = _import_module("isort")
    _tomli_module, tomli_error = _import_module("tomli")
    black_missing_apis = (
        _missing_apis(black_module, _REQUIRED_BLACK_APIS)
        if black_module is not None
        else tuple()
    )
    isort_missing_apis = (
        _missing_apis(isort_module, _REQUIRED_ISORT_APIS)
        if isort_module is not None
        else tuple()
    )
    black_available = black_error is None and not black_missing_apis
    isort_available = isort_error is None and not isort_missing_apis
    tomli_available = tomli_error is None
    is_available = black_available and isort_available and tomli_available
    message = _build_status_message(
        is_available=is_available,
        black_error=black_error,
        black_missing_apis=black_missing_apis,
        isort_error=isort_error,
        isort_missing_apis=isort_missing_apis,
        tomli_error=tomli_error,
    )
    return PythonToolingRuntimeStatus(
        is_available=is_available,
        vendor_root=vendor_root,
        black_available=black_available,
        isort_available=isort_available,
        tomli_available=tomli_available,
        message=message,
        black_error=black_error,
        isort_error=isort_error,
        tomli_error=tomli_error,
        black_missing_apis=black_missing_apis,
        isort_missing_apis=isort_missing_apis,
    )


def import_python_tooling_modules(app_root: Path | None = None) -> tuple[Any, Any, Any]:
    """Return imported vendored formatter/import modules."""
    runtime_status = initialize_python_tooling_runtime(app_root)
    if not runtime_status.is_available:
        raise RuntimeError(runtime_status.message)
    black_module = importlib.import_module("black")
    isort_module = importlib.import_module("isort")
    tomli_module = importlib.import_module("tomli")
    return black_module, isort_module, tomli_module


def _import_module(name: str) -> tuple[Any | None, str | None]:
    try:
        return importlib.import_module(name), None
    except Exception as exc:
        return None, str(exc)


def _missing_apis(module: Any, required_paths: tuple[str, ...]) -> tuple[str, ...]:
    missing: list[str] = []
    for api_path in required_paths:
        current = module
        found = True
        for part in api_path.split("."):
            if not hasattr(current, part):
                found = False
                break
            current = getattr(current, part)
        if not found:
            missing.append(api_path)
    return tuple(missing)


def _build_status_message(
    *,
    is_available: bool,
    black_error: str | None,
    black_missing_apis: tuple[str, ...],
    isort_error: str | None,
    isort_missing_apis: tuple[str, ...],
    tomli_error: str | None,
) -> str:
    if is_available:
        return "Python tooling runtime ready."
    issues: list[str] = []
    if black_error is not None:
        issues.append(f"black import failed ({black_error})")
    elif black_missing_apis:
        issues.append(f"black missing APIs ({', '.join(black_missing_apis)})")
    if isort_error is not None:
        issues.append(f"isort import failed ({isort_error})")
    elif isort_missing_apis:
        issues.append(f"isort missing APIs ({', '.join(isort_missing_apis)})")
    if tomli_error is not None:
        issues.append(f"tomli import failed ({tomli_error})")
    if not issues:
        issues.append("required tooling modules are unavailable")
    return "Python tooling runtime unavailable: " + "; ".join(issues)
