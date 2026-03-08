"""Project-level pytest runner helpers."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from shutil import which
import subprocess
import time

from app.bootstrap.paths import resolve_app_root
from app.run.problem_parser import ProblemEntry
from app.run.runtime_launch import is_freecad_runtime_executable, resolve_runtime_executable


@dataclass(frozen=True)
class PytestRunResult:
    """Result payload for one pytest invocation."""

    command: list[str]
    project_root: str
    return_code: int
    stdout: str
    stderr: str
    elapsed_ms: float
    failures: list[ProblemEntry]

    @property
    def succeeded(self) -> bool:
        return self.return_code == 0


def run_pytest_project(project_root: str, *, timeout_seconds: int = 300) -> PytestRunResult:
    """Run pytest in project root and parse navigable failures."""
    normalized_root = str(Path(project_root).expanduser().resolve())
    command = _build_pytest_command(project_root=normalized_root, pytest_args=["-q"])
    return _run_pytest_command(normalized_root, command, timeout_seconds=timeout_seconds)


def run_pytest_target(project_root: str, target_path: str, *, timeout_seconds: int = 300) -> PytestRunResult:
    """Run pytest for one target path relative to project root."""
    normalized_root = str(Path(project_root).expanduser().resolve())
    target = Path(target_path).expanduser()
    resolved_target = target if target.is_absolute() else (Path(normalized_root) / target)
    target_arg = str(resolved_target.resolve())
    command = _build_pytest_command(project_root=normalized_root, pytest_args=["-q", target_arg])
    return _run_pytest_command(normalized_root, command, timeout_seconds=timeout_seconds)


def _build_pytest_command(*, project_root: str, pytest_args: list[str]) -> list[str]:
    runtime_executable = _select_pytest_runtime(project_root=project_root)
    normalized_args = [str(arg) for arg in pytest_args]
    if is_freecad_runtime_executable(runtime_executable):
        payload = _build_apprun_pytest_payload(
            pytest_args=normalized_args,
            extra_sys_paths=_candidate_pytest_site_packages(project_root=project_root),
        )
        return [runtime_executable, "-c", payload]
    return [runtime_executable, "-m", "pytest", *normalized_args]


def _select_pytest_runtime(*, project_root: str) -> str:
    attempted: list[str] = []
    for candidate in _candidate_pytest_runtimes(project_root):
        attempted.append(candidate)
        if _runtime_supports_pytest(candidate, project_root=project_root):
            return candidate
    attempted_text = ", ".join(attempted) if attempted else "<none>"
    raise RuntimeError(
        "Pytest is not available in detected runtimes. "
        f"Tried: {attempted_text}. "
        "Install pytest in the project/app virtual environment or runtime."
    )


def _candidate_pytest_runtimes(project_root: str) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()
    raw_candidates = [
        os.environ.get("CBCS_PYTEST_EXECUTABLE"),
        str(Path(project_root).expanduser().resolve() / ".venv" / "bin" / "python"),
        str(resolve_app_root() / ".venv" / "bin" / "python"),
        resolve_runtime_executable(None),
    ]
    for raw_candidate in raw_candidates:
        normalized = _normalize_runtime_candidate(raw_candidate)
        if normalized is None or normalized in seen:
            continue
        seen.add(normalized)
        candidates.append(normalized)
    return candidates


def _candidate_pytest_site_packages(*, project_root: str) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()
    roots = [
        Path(project_root).expanduser().resolve() / ".venv",
        resolve_app_root() / ".venv",
    ]
    for root in roots:
        if not root.exists() or not root.is_dir():
            continue
        for site_packages in sorted(root.glob("lib/python*/site-packages")):
            if not site_packages.is_dir():
                continue
            normalized = str(site_packages)
            if normalized in seen:
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


def _runtime_supports_pytest(runtime_executable: str, *, project_root: str) -> bool:
    command: list[str]
    if is_freecad_runtime_executable(runtime_executable):
        command = [
            runtime_executable,
            "-c",
            _build_apprun_pytest_probe_payload(
                extra_sys_paths=_candidate_pytest_site_packages(project_root=project_root)
            ),
        ]
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


def _build_apprun_pytest_probe_payload(*, extra_sys_paths: list[str]) -> str:
    statements = ["import sys;"]
    for extra_path in extra_sys_paths:
        statements.append(f"sys.path.insert(0, {extra_path!r}) if {extra_path!r} not in sys.path else None;")
    statements.append("import pytest;sys.exit(0)")
    return "".join(statements)


def _build_apprun_pytest_payload(*, pytest_args: list[str], extra_sys_paths: list[str]) -> str:
    statements = ["import sys;"]
    for extra_path in extra_sys_paths:
        statements.append(f"sys.path.insert(0, {extra_path!r}) if {extra_path!r} not in sys.path else None;")
    statements.append("import pytest;")
    statements.append(f"sys.exit(pytest.main({pytest_args!r}))")
    return "".join(statements)


def _run_pytest_command(project_root: str, command: list[str], *, timeout_seconds: int) -> PytestRunResult:
    """Run pytest command and parse results."""
    started_at = time.perf_counter()
    completed = subprocess.run(
        command,
        cwd=project_root,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout_seconds,
    )
    elapsed_ms = (time.perf_counter() - started_at) * 1000.0
    combined_output = f"{completed.stdout}\n{completed.stderr}".strip()
    failures = parse_pytest_failures(combined_output, project_root)
    return PytestRunResult(
        command=command,
        project_root=project_root,
        return_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        elapsed_ms=elapsed_ms,
        failures=failures,
    )


def parse_pytest_failures(output_text: str, project_root: str) -> list[ProblemEntry]:
    """Parse pytest failure lines (`path.py:line: message`) into problem entries."""
    normalized_root = Path(project_root).expanduser().resolve()
    problems: list[ProblemEntry] = []
    seen: set[tuple[str, int, str]] = set()
    for line in output_text.splitlines():
        candidate = line.strip()
        if not candidate:
            continue
        problem = _parse_pytest_failure_line(candidate, normalized_root)
        if problem is None:
            continue
        key = (problem.file_path, problem.line_number, problem.message)
        if key in seen:
            continue
        seen.add(key)
        problems.append(problem)
    return problems


def _parse_pytest_failure_line(line: str, project_root: Path) -> ProblemEntry | None:
    # Typical pytest output line:
    # tests/test_sample.py:10: AssertionError
    path_part, separator, remainder = line.partition(":")
    if not separator:
        return None
    line_part, separator, message_part = remainder.partition(":")
    if not separator:
        return None
    if not path_part.endswith(".py"):
        return None
    try:
        line_number = int(line_part.strip())
    except ValueError:
        return None
    file_path = Path(path_part.strip())
    absolute_path = file_path if file_path.is_absolute() else (project_root / file_path)
    message = message_part.strip() or "pytest failure"
    return ProblemEntry(
        file_path=str(absolute_path.resolve()),
        line_number=line_number,
        context="pytest",
        message=message,
    )
