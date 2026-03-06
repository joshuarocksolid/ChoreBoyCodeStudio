"""Project-level pytest runner helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
import sys
import time

from app.run.problem_parser import ProblemEntry


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
    command = [sys.executable, "-m", "pytest", "-q"]
    return _run_pytest_command(normalized_root, command, timeout_seconds=timeout_seconds)


def run_pytest_target(project_root: str, target_path: str, *, timeout_seconds: int = 300) -> PytestRunResult:
    """Run pytest for one target path relative to project root."""
    normalized_root = str(Path(project_root).expanduser().resolve())
    target = Path(target_path).expanduser()
    resolved_target = target if target.is_absolute() else (Path(normalized_root) / target)
    target_arg = str(resolved_target.resolve())
    command = [sys.executable, "-m", "pytest", "-q", target_arg]
    return _run_pytest_command(normalized_root, command, timeout_seconds=timeout_seconds)


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
