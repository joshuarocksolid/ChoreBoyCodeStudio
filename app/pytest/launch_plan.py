"""Shared pytest subprocess launch contract for discovery and runner services."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from shutil import which

from app.bootstrap.paths import project_manifest_path
from app.bootstrap.vendor_paths import resolve_vendor_root
from app.project.import_layout import resolve_project_import_layout
from app.project.project_manifest import load_project_manifest
from app.run.runtime_launch import (
    build_runpy_bootstrap_payload,
    is_freecad_runtime_executable,
    resolve_runtime_executable,
)

_IMPORT_MODE_ARG = "--import-mode=importlib"
_PYTEST_CACHE_PROVIDER_DISABLE_ARGS = ["-p", "no:cacheprovider"]
_RUN_TESTS_FILENAME = "run_tests.py"


PYTEST_MISSING_MARKER = "cbcs:test_explorer:pytest_missing"
PYTEST_MISSING_MESSAGE = (
    "pytest is not bundled with this Code Studio install. "
    "Reinstall the editor or restore the bundled vendor/ directory."
)


@dataclass(frozen=True)
class PytestLaunchPlan:
    """Resolved runtime and bootstrap contract for one pytest invocation."""

    project_root: str
    runtime_executable: str
    run_tests_script: Path | None
    use_apprun_inline_payload: bool


def _pytest_path_entries(project_root: str) -> tuple[str, ...]:
    root = Path(project_root).expanduser().resolve()
    metadata = None
    manifest_path = project_manifest_path(root)
    if manifest_path.is_file():
        try:
            metadata = load_project_manifest(manifest_path)
        except Exception:
            metadata = None
    layout = resolve_project_import_layout(root, metadata)
    return layout.runtime_sys_path_entries


def build_pytest_launch_plan(project_root: str) -> PytestLaunchPlan:
    """Resolve the pytest launch contract shared by discovery and runner."""

    normalized_root = str(Path(project_root).expanduser().resolve())
    runtime_executable = _select_pytest_runtime(project_root=normalized_root)
    run_tests_script = _project_run_tests_script(normalized_root)
    return PytestLaunchPlan(
        project_root=normalized_root,
        runtime_executable=runtime_executable,
        run_tests_script=run_tests_script,
        use_apprun_inline_payload=is_freecad_runtime_executable(runtime_executable),
    )


def build_pytest_command(plan: PytestLaunchPlan, pytest_args: list[str]) -> list[str]:
    """Build argv for one pytest subprocess using the shared launch plan."""

    normalized_args = _normalized_pytest_args(pytest_args)
    if plan.run_tests_script is not None:
        if plan.use_apprun_inline_payload:
            payload = build_runpy_bootstrap_payload(
                script_path=str(plan.run_tests_script),
                path_entries=_pytest_path_entries(plan.project_root),
                argv=[str(plan.run_tests_script), *normalized_args],
            )
            return [plan.runtime_executable, "-c", payload]
        return [plan.runtime_executable, str(plan.run_tests_script), *normalized_args]
    if plan.use_apprun_inline_payload:
        return [plan.runtime_executable, "-c", build_apprun_pytest_payload(normalized_args)]
    return [plan.runtime_executable, "-m", "pytest", *normalized_args]


def build_apprun_pytest_payload(pytest_args: list[str]) -> str:
    """Build inline AppRun payload that imports vendor pytest before running."""

    vendor_root = str(resolve_vendor_root())
    lines = [
        "import sys",
        f"sys.path.insert(0, {vendor_root!r})",
        "try:",
        "    import pytest",
        "except ModuleNotFoundError:",
        f"    sys.stderr.write({PYTEST_MISSING_MARKER!r} + '\\n')",
        "    sys.exit(2)",
        f"sys.exit(pytest.main({pytest_args!r}))",
    ]
    return "\n".join(lines)


def build_apprun_pytest_probe_payload() -> str:
    vendor_root = str(resolve_vendor_root())
    lines = [
        "import sys",
        f"sys.path.insert(0, {vendor_root!r})",
        "try:",
        "    import pytest",
        "except ModuleNotFoundError:",
        f"    sys.stderr.write({PYTEST_MISSING_MARKER!r} + '\\n')",
        "    sys.exit(2)",
        "sys.exit(0)",
    ]
    return "\n".join(lines)


def _select_pytest_runtime(*, project_root: str) -> str:
    attempted: list[str] = []
    for candidate in _candidate_pytest_runtimes(project_root):
        attempted.append(candidate)
        if _runtime_supports_pytest(candidate):
            return candidate
    attempted_text = ", ".join(attempted) if attempted else "<none>"
    raise RuntimeError(
        "Pytest is not available in detected runtimes. "
        f"Tried: {attempted_text}. "
        "Install pytest in the configured runtime or set CBCS_PYTEST_EXECUTABLE."
    )


def _candidate_pytest_runtimes(project_root: str) -> list[str]:
    _ = project_root
    candidates: list[str] = []
    seen: set[str] = set()
    raw_candidates = [
        os.environ.get("CBCS_PYTEST_EXECUTABLE"),
        resolve_runtime_executable(None),
    ]
    for raw_candidate in raw_candidates:
        normalized = _normalize_runtime_candidate(raw_candidate)
        if normalized is None or normalized in seen:
            continue
        seen.add(normalized)
        candidates.append(normalized)
    return candidates


def _normalize_runtime_candidate(candidate: str | None) -> str | None:
    if not candidate or not candidate.strip():
        return None
    trimmed = candidate.strip()
    if "/" not in trimmed:
        resolved_binary = which(trimmed)
        if resolved_binary is None:
            return None
        return str(Path(resolved_binary).resolve())
    path = Path(trimmed).expanduser()
    if not path.exists() or not path.is_file():
        return None
    if not path.is_absolute():
        path = (Path.cwd() / path).absolute()
    return str(path)


def _runtime_supports_pytest(runtime_executable: str) -> bool:
    import subprocess

    if is_freecad_runtime_executable(runtime_executable):
        command = [runtime_executable, "-c", build_apprun_pytest_probe_payload()]
    else:
        command = [runtime_executable, "-c", "import pytest"]
    try:
        completed = subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
            timeout=8,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def _normalized_pytest_args(pytest_args: list[str]) -> list[str]:
    normalized_args = [str(arg) for arg in pytest_args]
    if _IMPORT_MODE_ARG not in normalized_args:
        insert_at = len(normalized_args)
        for index, arg in enumerate(normalized_args):
            if not arg.startswith("-"):
                insert_at = index
                break
        normalized_args.insert(insert_at, _IMPORT_MODE_ARG)
    if not _has_cache_provider_override(normalized_args):
        insert_at = len(normalized_args)
        for index, arg in enumerate(normalized_args):
            if not arg.startswith("-"):
                insert_at = index
                break
        normalized_args[insert_at:insert_at] = list(_PYTEST_CACHE_PROVIDER_DISABLE_ARGS)
    return normalized_args


def _has_cache_provider_override(pytest_args: list[str]) -> bool:
    for index, arg in enumerate(pytest_args):
        if arg == "-p" and index + 1 < len(pytest_args) and pytest_args[index + 1] == "no:cacheprovider":
            return True
    return False


def _project_run_tests_script(project_root: str) -> Path | None:
    candidate = Path(project_root).expanduser().resolve() / _RUN_TESTS_FILENAME
    if candidate.exists() and candidate.is_file():
        return candidate
    return None


def build_pytest_subprocess_env() -> dict[str, str]:
    """Return environment overrides shared by discovery and runner subprocesses."""
    env = os.environ.copy()
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    return env
