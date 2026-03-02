"""Discover importable top-level modules from the target runtime via subprocess probe."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.bootstrap.paths import PathInput, ensure_directory, global_cache_dir
from app.core import constants

RUNTIME_MODULES_CACHE_FILENAME = "runtime_modules.json"
PROBE_TIMEOUT_SECONDS = 30

PROBE_SCRIPT = (
    "import sys, json, pkgutil;"
    "mods = set(sys.builtin_module_names);"
    "[mods.add(name) for _, name, _ in pkgutil.iter_modules()];"
    "print(json.dumps(sorted(mods)))"
)


@dataclass(frozen=True)
class RuntimeModuleProbeResult:
    """Structured result from probing runtime for importable modules."""

    modules: frozenset[str]
    runtime_path: str
    python_version: str
    probed_at: str
    success: bool
    error_message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_path": self.runtime_path,
            "python_version": self.python_version,
            "probed_at": self.probed_at,
            "modules": sorted(self.modules),
        }


def probe_runtime_modules(runtime_path: str) -> RuntimeModuleProbeResult:
    """Run a subprocess under *runtime_path* to enumerate importable modules."""
    now = datetime.now(timezone.utc).isoformat()

    version_script = "import sys; print('{}.{}.{}'.format(*sys.version_info[:3]))"
    try:
        version_proc = subprocess.run(
            [runtime_path, "-c", version_script],
            capture_output=True,
            text=True,
            check=False,
            timeout=PROBE_TIMEOUT_SECONDS,
        )
        python_version = version_proc.stdout.strip() if version_proc.returncode == 0 else "unknown"
    except (OSError, subprocess.TimeoutExpired):
        python_version = "unknown"

    try:
        completed = subprocess.run(
            [runtime_path, "-c", PROBE_SCRIPT],
            capture_output=True,
            text=True,
            check=False,
            timeout=PROBE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return RuntimeModuleProbeResult(
            modules=frozenset(),
            runtime_path=runtime_path,
            python_version=python_version,
            probed_at=now,
            success=False,
            error_message=f"Probe timed out after {PROBE_TIMEOUT_SECONDS}s",
        )
    except OSError as exc:
        return RuntimeModuleProbeResult(
            modules=frozenset(),
            runtime_path=runtime_path,
            python_version=python_version,
            probed_at=now,
            success=False,
            error_message=f"Failed to launch probe: {exc}",
        )

    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip()
        return RuntimeModuleProbeResult(
            modules=frozenset(),
            runtime_path=runtime_path,
            python_version=python_version,
            probed_at=now,
            success=False,
            error_message=f"Probe exited with code {completed.returncode}: {stderr}",
        )

    try:
        module_list = json.loads(completed.stdout.strip())
    except (json.JSONDecodeError, ValueError) as exc:
        return RuntimeModuleProbeResult(
            modules=frozenset(),
            runtime_path=runtime_path,
            python_version=python_version,
            probed_at=now,
            success=False,
            error_message=f"Failed to parse probe output: {exc}",
        )

    return RuntimeModuleProbeResult(
        modules=frozenset(module_list),
        runtime_path=runtime_path,
        python_version=python_version,
        probed_at=now,
        success=True,
    )


def _cache_path(state_root: Optional[PathInput] = None) -> Path:
    return global_cache_dir(state_root) / RUNTIME_MODULES_CACHE_FILENAME


def save_runtime_modules_cache(
    result: RuntimeModuleProbeResult,
    state_root: Optional[PathInput] = None,
) -> Path:
    """Persist probe result to the global cache directory.  Returns cache path."""
    path = _cache_path(state_root)
    ensure_directory(path.parent)
    path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
    return path


def load_cached_runtime_modules(
    state_root: Optional[PathInput] = None,
) -> frozenset[str] | None:
    """Load cached module set from disk.  Returns *None* when cache is missing or corrupt."""
    path = _cache_path(state_root)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return frozenset(data["modules"])
    except (json.JSONDecodeError, KeyError, TypeError, OSError):
        return None


def resolve_probe_runtime_path() -> str:
    """Pick the runtime executable to probe: AppRun if present, else sys.executable."""
    default_runtime = Path(constants.APP_RUN_PATH)
    if default_runtime.exists():
        return str(default_runtime.resolve())
    return sys.executable


def probe_and_cache_runtime_modules(
    runtime_path: str | None = None,
    state_root: Optional[PathInput] = None,
) -> frozenset[str]:
    """Probe the runtime, cache the result, and return the module set.

    Falls back to cached data or an empty set on failure.
    """
    effective_runtime = runtime_path or resolve_probe_runtime_path()
    result = probe_runtime_modules(effective_runtime)
    if result.success:
        save_runtime_modules_cache(result, state_root)
        return result.modules
    cached = load_cached_runtime_modules(state_root)
    if cached is not None:
        return cached
    return result.modules
