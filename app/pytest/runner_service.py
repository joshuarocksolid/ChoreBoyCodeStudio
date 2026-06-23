"""Project-level pytest runner helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import ast
import subprocess
import time

from app.pytest.launch_plan import (
    build_pytest_command as _build_pytest_command_from_plan,
    build_pytest_launch_plan,
    build_pytest_subprocess_env,
)
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
    command = _build_pytest_command(project_root=normalized_root, pytest_args=["-q", "-rA"])
    return _run_pytest_command(normalized_root, command, timeout_seconds=timeout_seconds)


def run_pytest_node(project_root: str, node_id: str, *, timeout_seconds: int = 300) -> PytestRunResult:
    """Run pytest for a specific node ID (e.g. tests/test_foo.py::test_bar)."""
    normalized_root = str(Path(project_root).expanduser().resolve())
    command = _build_pytest_command(project_root=normalized_root, pytest_args=["-v", node_id])
    return _run_pytest_command(normalized_root, command, timeout_seconds=timeout_seconds)


def run_pytest_failed(project_root: str, failed_node_ids: list[str], *, timeout_seconds: int = 300) -> PytestRunResult:
    """Re-run only the specified failed test node IDs."""
    normalized_root = str(Path(project_root).expanduser().resolve())
    command = _build_pytest_command(project_root=normalized_root, pytest_args=["-v"] + failed_node_ids)
    return _run_pytest_command(normalized_root, command, timeout_seconds=timeout_seconds)


def identify_test_at_cursor(source_text: str, cursor_line: int) -> str | None:
    """Identify the enclosing pytest test at the given line (1-based).

    Returns a pytest node suffix (``test_foo`` or ``TestClass::test_foo``) or None.
    """
    try:
        tree = ast.parse(source_text)
    except SyntaxError:
        return None

    visitor = _TestAtCursorVisitor(cursor_line)
    visitor.visit(tree)
    return visitor.best_match


def _is_pytest_collectible_test(name: str) -> bool:
    return name.startswith("test_") or name.endswith("_test")


class _TestAtCursorVisitor(ast.NodeVisitor):
    def __init__(self, cursor_line: int) -> None:
        self._cursor_line = cursor_line
        self._class_stack: list[str] = []
        self.best_match: str | None = None
        self._best_start = -1

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._class_stack.append(node.name)
        self.generic_visit(node)
        self._class_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._consider_test(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._consider_test(node)
        self.generic_visit(node)

    def _consider_test(self, node: ast.AST) -> None:
        assert isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        if not _is_pytest_collectible_test(node.name):
            return
        end_line = getattr(node, "end_lineno", None) or node.lineno + 100
        if node.lineno <= self._cursor_line <= end_line and node.lineno > self._best_start:
            if self._class_stack:
                self.best_match = f"{'::'.join(self._class_stack)}::{node.name}"
            else:
                self.best_match = node.name
            self._best_start = node.lineno


def run_pytest_target(project_root: str, target_path: str, *, timeout_seconds: int = 300) -> PytestRunResult:
    """Run pytest for one target path relative to project root."""
    normalized_root = str(Path(project_root).expanduser().resolve())
    target = Path(target_path).expanduser()
    resolved_target = target if target.is_absolute() else (Path(normalized_root) / target)
    target_arg = str(resolved_target.resolve())
    command = _build_pytest_command(project_root=normalized_root, pytest_args=["-q", "-rA", target_arg])
    return _run_pytest_command(normalized_root, command, timeout_seconds=timeout_seconds)


def run_pytest_args(project_root: str, pytest_args: list[str], *, timeout_seconds: int = 300) -> PytestRunResult:
    """Run pytest with explicit argument list."""
    normalized_root = str(Path(project_root).expanduser().resolve())
    command = _build_pytest_command(project_root=normalized_root, pytest_args=pytest_args)
    return _run_pytest_command(normalized_root, command, timeout_seconds=timeout_seconds)


def _build_pytest_command(*, project_root: str, pytest_args: list[str]) -> list[str]:
    plan = build_pytest_launch_plan(project_root)
    return _build_pytest_command_from_plan(plan, pytest_args)


def _run_pytest_command(project_root: str, command: list[str], *, timeout_seconds: int) -> PytestRunResult:
    """Run pytest command and parse results."""
    started_at = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            cwd=project_root,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout_seconds,
            env=build_pytest_subprocess_env(),
        )
    except subprocess.TimeoutExpired as exc:
        elapsed_ms = (time.perf_counter() - started_at) * 1000.0
        stdout = exc.stdout if isinstance(exc.stdout, str) else (exc.stdout or b"").decode("utf-8", errors="replace")
        stderr = exc.stderr if isinstance(exc.stderr, str) else (exc.stderr or b"").decode("utf-8", errors="replace")
        combined_output = f"{stdout}\n{stderr}".strip()
        failures = parse_pytest_failures(combined_output, project_root)
        return PytestRunResult(
            command=command,
            project_root=project_root,
            return_code=-1,
            stdout=stdout,
            stderr=stderr or f"pytest timed out after {timeout_seconds}s",
            elapsed_ms=elapsed_ms,
            failures=failures,
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
