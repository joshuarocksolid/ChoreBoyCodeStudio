"""Runtime capability checks used during editor startup."""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Callable, Optional

from app.bootstrap.paths import (
    PathInput,
    ensure_directory,
    global_logs_dir,
    resolve_global_state_root,
    resolve_temp_root,
)
from app.core import constants
from app.core.models import CapabilityCheckResult, CapabilityProbeReport
from app.python_tools.vendor_runtime import import_python_tooling_modules, initialize_python_tooling_runtime


APP_RUN_PRESENCE_CHECK_ID = "apprun_presence"
PYSIDE2_IMPORT_CHECK_ID = "pyside2_import"
FREECAD_IMPORT_CHECK_ID = "freecad_import"
STATE_ROOT_WRITABLE_CHECK_ID = "state_root_writable"
GLOBAL_LOGS_WRITABLE_CHECK_ID = "global_logs_writable"
TEMP_ROOT_WRITABLE_CHECK_ID = "temp_root_writable"
PYTHON_TOOLING_RUNTIME_CHECK_ID = "python_tooling_runtime"
MODULE_IMPORT_PROBE_TIMEOUT_SECONDS = 10


def run_startup_capability_probe(
    state_root: Optional[PathInput] = None,
    temp_root: Optional[PathInput] = None,
    app_run_path: Optional[PathInput] = None,
) -> CapabilityProbeReport:
    """Run startup capability checks and return structured results."""
    check_runners: list[tuple[str, Callable[[], CapabilityCheckResult]]] = [
        (APP_RUN_PRESENCE_CHECK_ID, lambda: check_apprun_presence(app_run_path=app_run_path)),
        (PYSIDE2_IMPORT_CHECK_ID, check_pyside2_availability),
        (FREECAD_IMPORT_CHECK_ID, check_freecad_availability),
        (STATE_ROOT_WRITABLE_CHECK_ID, lambda: check_writable_state_path(state_root=state_root)),
        (GLOBAL_LOGS_WRITABLE_CHECK_ID, lambda: check_writable_logs_path(state_root=state_root)),
        (TEMP_ROOT_WRITABLE_CHECK_ID, lambda: check_writable_temp_path(temp_root=temp_root)),
        (PYTHON_TOOLING_RUNTIME_CHECK_ID, check_python_tooling_runtime),
    ]
    checks: list[CapabilityCheckResult] = []

    for expected_check_id, runner in check_runners:
        try:
            checks.append(runner())
        except Exception as exc:  # pragma: no cover - defensive guard for startup resilience
            checks.append(
                CapabilityCheckResult(
                    check_id=expected_check_id,
                    is_available=False,
                    message=f"{expected_check_id} check crashed: {exc}",
                    details={"error_type": type(exc).__name__},
                )
            )

    return CapabilityProbeReport(checks=checks)


def run_minimal_startup_capability_probe(
    state_root: Optional[PathInput] = None,
    temp_root: Optional[PathInput] = None,
    app_run_path: Optional[PathInput] = None,
) -> CapabilityProbeReport:
    """Run a lightweight prepaint subset of startup capability checks."""
    check_runners: list[tuple[str, Callable[[], CapabilityCheckResult]]] = [
        (APP_RUN_PRESENCE_CHECK_ID, lambda: check_apprun_presence(app_run_path=app_run_path)),
        (PYSIDE2_IMPORT_CHECK_ID, check_pyside2_availability),
        (STATE_ROOT_WRITABLE_CHECK_ID, lambda: check_writable_state_path(state_root=state_root)),
        (GLOBAL_LOGS_WRITABLE_CHECK_ID, lambda: check_writable_logs_path(state_root=state_root)),
        (TEMP_ROOT_WRITABLE_CHECK_ID, lambda: check_writable_temp_path(temp_root=temp_root)),
    ]
    checks: list[CapabilityCheckResult] = []
    for expected_check_id, runner in check_runners:
        try:
            checks.append(runner())
        except Exception as exc:  # pragma: no cover - defensive guard for startup resilience
            checks.append(
                CapabilityCheckResult(
                    check_id=expected_check_id,
                    is_available=False,
                    message=f"{expected_check_id} check crashed: {exc}",
                    details={"error_type": type(exc).__name__},
                )
            )
    return CapabilityProbeReport(checks=checks)


def check_apprun_presence(app_run_path: Optional[PathInput] = None) -> CapabilityCheckResult:
    """Check whether the expected AppRun path exists."""
    configured = Path(app_run_path or constants.APP_RUN_PATH).expanduser()
    target_path = configured.resolve()
    path_exists = target_path.exists()

    if path_exists:
        return CapabilityCheckResult(
            check_id=APP_RUN_PRESENCE_CHECK_ID,
            is_available=True,
            message="AppRun path is available.",
            details={"path": str(target_path)},
        )

    return CapabilityCheckResult(
        check_id=APP_RUN_PRESENCE_CHECK_ID,
        is_available=False,
        message=f"AppRun path not found: {target_path}",
        details={"path": str(target_path)},
    )


def check_pyside2_availability() -> CapabilityCheckResult:
    """Check that PySide2 is importable in the active runtime."""
    return _check_module_import("PySide2", PYSIDE2_IMPORT_CHECK_ID)


def check_freecad_availability() -> CapabilityCheckResult:
    """Check that FreeCAD is importable without mutating editor runtime state."""
    result = _check_module_import_in_subprocess("FreeCAD", FREECAD_IMPORT_CHECK_ID)
    if result.is_available:
        return result

    if "isolated probe launch failed" not in result.message:
        return result

    app_run_path = Path(constants.APP_RUN_PATH).expanduser().resolve()
    if not app_run_path.exists() or not os.access(app_run_path, os.X_OK):
        return result

    fallback = _check_module_import_with_command(
        module_name="FreeCAD",
        check_id=FREECAD_IMPORT_CHECK_ID,
        command=[str(app_run_path), "-c", "import importlib;importlib.import_module('FreeCAD')"],
        probe_name="apprun_subprocess",
    )
    if fallback.is_available:
        return CapabilityCheckResult(
            check_id=FREECAD_IMPORT_CHECK_ID,
            is_available=True,
            message="FreeCAD import succeeded via AppRun probe.",
            details={"module": "FreeCAD", "probe": "apprun_subprocess", "path": str(app_run_path)},
        )
    return CapabilityCheckResult(
        check_id=FREECAD_IMPORT_CHECK_ID,
        is_available=False,
        message=f"{result.message} | AppRun fallback also failed: {fallback.message}",
        details={
            "module": "FreeCAD",
            "primary_probe": result.details.get("probe"),
            "fallback_probe": fallback.details.get("probe"),
            "path": str(app_run_path),
        },
    )


def check_writable_state_path(state_root: Optional[PathInput] = None) -> CapabilityCheckResult:
    """Check that global state root path is writable."""
    directory = resolve_global_state_root(state_root)
    return _check_writable_directory(directory, STATE_ROOT_WRITABLE_CHECK_ID, "Global state root")


def check_writable_logs_path(state_root: Optional[PathInput] = None) -> CapabilityCheckResult:
    """Check that global logs directory is writable."""
    directory = global_logs_dir(state_root)
    return _check_writable_directory(directory, GLOBAL_LOGS_WRITABLE_CHECK_ID, "Global logs directory")


def check_writable_temp_path(temp_root: Optional[PathInput] = None) -> CapabilityCheckResult:
    """Check that app temp directory is writable."""
    directory = resolve_temp_root(temp_root)
    return _check_writable_directory(directory, TEMP_ROOT_WRITABLE_CHECK_ID, "Temp root")


def check_python_tooling_runtime() -> CapabilityCheckResult:
    """Check that vendored Python format/import tooling is importable."""
    runtime_status = initialize_python_tooling_runtime()
    details = {
        "vendor_root": str(runtime_status.vendor_root),
        "black_available": runtime_status.black_available,
        "isort_available": runtime_status.isort_available,
        "tomli_available": runtime_status.tomli_available,
        "black_error": runtime_status.black_error,
        "isort_error": runtime_status.isort_error,
        "tomli_error": runtime_status.tomli_error,
        "black_missing_apis": list(runtime_status.black_missing_apis),
        "isort_missing_apis": list(runtime_status.isort_missing_apis),
    }
    if not runtime_status.is_available:
        return CapabilityCheckResult(
            check_id=PYTHON_TOOLING_RUNTIME_CHECK_ID,
            is_available=False,
            message=runtime_status.message,
            details=details,
        )

    try:
        black_module, isort_module, tomli_module = import_python_tooling_modules()
    except Exception as exc:
        return CapabilityCheckResult(
            check_id=PYTHON_TOOLING_RUNTIME_CHECK_ID,
            is_available=False,
            message=f"Vendored Python format/import tooling is unavailable: {exc}",
            details=details,
        )
    details.update(
        {
            "black_version": getattr(black_module, "__version__", ""),
            "isort_version": getattr(isort_module, "__version__", ""),
            "tomli_version": getattr(tomli_module, "__version__", ""),
        }
    )
    return CapabilityCheckResult(
        check_id=PYTHON_TOOLING_RUNTIME_CHECK_ID,
        is_available=True,
        message="Vendored Python format/import tooling is ready.",
        details=details,
    )


def _check_module_import(module_name: str, check_id: str) -> CapabilityCheckResult:
    try:
        importlib.import_module(module_name)
    except Exception as exc:
        return CapabilityCheckResult(
            check_id=check_id,
            is_available=False,
            message=f"Failed to import {module_name}: {exc}",
            details={"module": module_name},
        )

    return CapabilityCheckResult(
        check_id=check_id,
        is_available=True,
        message=f"{module_name} import succeeded.",
        details={"module": module_name},
    )


def _check_module_import_in_subprocess(module_name: str, check_id: str) -> CapabilityCheckResult:
    """Probe module import in a child interpreter to isolate side effects/crashes."""
    probe_script = (
        "import importlib;"
        f"importlib.import_module({module_name!r})"
    )
    return _check_module_import_with_command(
        module_name=module_name,
        check_id=check_id,
        command=[sys.executable, "-c", probe_script],
        probe_name="subprocess",
    )


def _check_module_import_with_command(
    *,
    module_name: str,
    check_id: str,
    command: list[str],
    probe_name: str,
) -> CapabilityCheckResult:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=MODULE_IMPORT_PROBE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return CapabilityCheckResult(
            check_id=check_id,
            is_available=False,
            message=(
                f"Failed to import {module_name}: isolated probe timed out "
                f"after {MODULE_IMPORT_PROBE_TIMEOUT_SECONDS}s"
            ),
            details={
                "module": module_name,
                "probe": probe_name,
                "timeout_seconds": MODULE_IMPORT_PROBE_TIMEOUT_SECONDS,
            },
        )
    except OSError as exc:
        return CapabilityCheckResult(
            check_id=check_id,
            is_available=False,
            message=f"Failed to import {module_name}: isolated probe launch failed ({exc})",
            details={"module": module_name, "probe": probe_name},
        )

    if completed.returncode == 0:
        return CapabilityCheckResult(
            check_id=check_id,
            is_available=True,
            message=f"{module_name} import succeeded.",
            details={"module": module_name, "probe": probe_name},
        )

    stderr = (completed.stderr or "").strip()
    stdout = (completed.stdout or "").strip()
    if completed.returncode < 0:
        reason = f"terminated by signal {-completed.returncode}"
    elif stderr:
        reason = stderr
    elif stdout:
        reason = stdout
    else:
        reason = f"exit code {completed.returncode}"

    return CapabilityCheckResult(
        check_id=check_id,
        is_available=False,
        message=f"Failed to import {module_name}: {reason}",
        details={"module": module_name, "probe": probe_name, "return_code": completed.returncode},
    )


def _check_writable_directory(directory: Path, check_id: str, label: str) -> CapabilityCheckResult:
    try:
        _verify_writable_directory(directory)
    except Exception as exc:
        return CapabilityCheckResult(
            check_id=check_id,
            is_available=False,
            message=f"{label} is not writable: {exc}",
            details={"path": str(directory.resolve())},
        )

    return CapabilityCheckResult(
        check_id=check_id,
        is_available=True,
        message=f"{label} is writable.",
        details={"path": str(directory.resolve())},
    )


def _verify_writable_directory(directory: Path) -> None:
    """Create directory and verify write permissions with a probe file."""
    ensured_dir = ensure_directory(directory)
    probe_file = ensured_dir / f".capability_probe_{uuid.uuid4().hex}.tmp"
    probe_file.write_text("ok", encoding="utf-8")
    probe_file.unlink()
