"""Runtime bootstrap for vendored Jedi/parso packages."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.bootstrap.paths import PathInput, ensure_directory, global_cache_dir
from app.bootstrap.vendor_paths import ensure_vendor_path_on_sys_path


@dataclass(frozen=True)
class JediRuntimeStatus:
    """Availability details for the Jedi runtime."""

    is_available: bool
    message: str
    cache_directory: str = ""
    jedi_version: str = ""
    parso_version: str = ""


_RUNTIME_INITIALIZED = False
_RUNTIME_STATUS = JediRuntimeStatus(False, "not_initialized")


def runtime_status() -> JediRuntimeStatus:
    """Return the latest Jedi runtime status."""
    return _RUNTIME_STATUS


def initialize_jedi_runtime(state_root: Optional[PathInput] = None) -> JediRuntimeStatus:
    """Ensure vendored Jedi/parso are importable and use a visible cache path."""
    global _RUNTIME_INITIALIZED, _RUNTIME_STATUS
    if _RUNTIME_INITIALIZED:
        return _RUNTIME_STATUS

    try:
        ensure_vendor_path_on_sys_path()
        import jedi
        import parso

        script_api = getattr(jedi, "Script", None)
        if not callable(script_api):
            raise AttributeError("module 'jedi' is missing required callable 'Script'")

        cache_directory = ensure_directory(global_cache_dir(state_root) / "jedi")
        settings_obj = getattr(jedi, "settings", None)
        if settings_obj is not None and hasattr(settings_obj, "cache_directory"):
            settings_obj.cache_directory = str(cache_directory)

        _RUNTIME_STATUS = JediRuntimeStatus(
            is_available=True,
            message="ready",
            cache_directory=str(cache_directory),
            jedi_version=str(getattr(jedi, "__version__", "")),
            parso_version=str(getattr(parso, "__version__", "")),
        )
    except Exception as exc:  # pragma: no cover - defensive runtime guard
        _RUNTIME_STATUS = JediRuntimeStatus(False, f"{exc.__class__.__name__}: {exc}")
    _RUNTIME_INITIALIZED = True
    return _RUNTIME_STATUS
