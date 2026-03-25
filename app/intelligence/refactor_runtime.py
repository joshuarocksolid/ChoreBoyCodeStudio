"""Runtime bootstrap for vendored Rope refactoring support."""
from __future__ import annotations

from dataclasses import dataclass

from app.bootstrap.vendor_paths import ensure_vendor_path_on_sys_path


@dataclass(frozen=True)
class RefactorRuntimeStatus:
    """Availability details for the Rope runtime."""

    is_available: bool
    message: str
    rope_version: str = ""


_RUNTIME_INITIALIZED = False
_RUNTIME_STATUS = RefactorRuntimeStatus(False, "not_initialized")


def runtime_status() -> RefactorRuntimeStatus:
    """Return the latest Rope runtime status."""
    return _RUNTIME_STATUS


def initialize_refactor_runtime() -> RefactorRuntimeStatus:
    """Ensure vendored Rope is importable."""
    global _RUNTIME_INITIALIZED, _RUNTIME_STATUS
    if _RUNTIME_INITIALIZED:
        return _RUNTIME_STATUS

    try:
        ensure_vendor_path_on_sys_path()
        import rope

        _RUNTIME_STATUS = RefactorRuntimeStatus(
            is_available=True,
            message="ready",
            rope_version=str(getattr(rope, "VERSION", "")),
        )
    except Exception as exc:  # pragma: no cover - defensive runtime guard
        _RUNTIME_STATUS = RefactorRuntimeStatus(False, f"{exc.__class__.__name__}: {exc}")
    _RUNTIME_INITIALIZED = True
    return _RUNTIME_STATUS
