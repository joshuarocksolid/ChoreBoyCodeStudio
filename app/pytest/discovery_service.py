"""Pytest-based test discovery for the test explorer."""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
import subprocess
from typing import cast

from app.pytest.launch_plan import (
    PYTEST_MISSING_MARKER,
    PYTEST_MISSING_MESSAGE,
    build_pytest_command,
    build_pytest_launch_plan,
    build_pytest_subprocess_env,
)
from app.pytest.outcome_types import TestNodeKind, TestOutcome


@dataclass(frozen=True)
class DiscoveredTestNode:
    """One discovered test item in the collection tree."""

    node_id: str  # pytest node ID, e.g. tests/test_foo.py::TestClass::test_method
    name: str  # display name, e.g. test_method
    file_path: str  # absolute path to test file
    line_number: int  # 1-based line number (or 0 if unknown)
    kind: TestNodeKind
    parent_id: str = ""  # node_id of the parent, empty for file nodes


@dataclass
class DiscoveryResult:
    """Result of one test discovery pass."""

    nodes: list[DiscoveredTestNode] = field(default_factory=list)
    error_message: str = ""

    @property
    def succeeded(self) -> bool:
        return not self.error_message

    def file_nodes(self) -> list[DiscoveredTestNode]:
        return [n for n in self.nodes if n.kind == "file"]

    def class_nodes(self) -> list[DiscoveredTestNode]:
        return [n for n in self.nodes if n.kind == "class"]

    def function_nodes(self) -> list[DiscoveredTestNode]:
        return [n for n in self.nodes if n.kind == "function"]


@dataclass(frozen=True)
class DiscoveredTestResult:
    """Per-test execution result."""

    node_id: str
    outcome: TestOutcome
    message: str = ""
    file_path: str = ""
    line_number: int = 0


def discover_tests(project_root: str, *, timeout_seconds: int = 30) -> DiscoveryResult:
    """Discover pytest-compatible tests by running ``pytest --collect-only -q``.

    Collection is parsed from pytest stdout (not a JSON report plugin). Nested
    classes, parametrized node IDs, and AST-backed line numbers are supported;
    a structured ``--collect-only`` JSON path remains deferred until a bundled
    report plugin is available in the vendor tree.
    """
    normalized_root = str(Path(project_root).expanduser().resolve())
    command = _build_collect_command(project_root=normalized_root)

    try:
        result = subprocess.run(
            command,
            cwd=normalized_root,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env=build_pytest_subprocess_env(),
        )
    except subprocess.TimeoutExpired:
        return DiscoveryResult(error_message="Test discovery timed out.")
    except OSError as exc:
        return DiscoveryResult(error_message=f"Test discovery failed: {exc}")

    if result.returncode not in (0, 5):  # 5 = no tests collected
        if PYTEST_MISSING_MARKER in (result.stderr or "") or PYTEST_MISSING_MARKER in (result.stdout or ""):
            return DiscoveryResult(error_message=PYTEST_MISSING_MESSAGE)
        error_msg = (result.stderr or result.stdout or "").strip()
        if not error_msg:
            error_msg = f"pytest exited with code {result.returncode}"
        return DiscoveryResult(error_message=error_msg)

    nodes = _parse_collect_output(result.stdout, project_root=normalized_root)
    return DiscoveryResult(nodes=nodes)


def parse_test_results(output: str) -> list[DiscoveredTestResult]:
    """Parse pytest output into per-test results.

    Supports verbose ``node PASSED`` lines and ``-rA`` summary lines.
    """
    results: list[DiscoveredTestResult] = []
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        summary_outcome = _parse_summary_result_line(stripped)
        if summary_outcome is not None:
            node_id, outcome = summary_outcome
            results.append(DiscoveredTestResult(node_id=node_id, outcome=outcome))
            continue
        verbose_outcome = _parse_verbose_result_line(stripped)
        if verbose_outcome is not None:
            node_id, outcome = verbose_outcome
            results.append(DiscoveredTestResult(node_id=node_id, outcome=outcome))
    return results


def _parse_summary_result_line(stripped: str) -> tuple[str, TestOutcome] | None:
    for prefix, outcome in (
        ("PASSED ", "passed"),
        ("FAILED ", "failed"),
        ("SKIPPED ", "skipped"),
        ("ERROR ", "error"),
    ):
        if stripped.startswith(prefix):
            node_id = stripped[len(prefix) :].split(" - ", 1)[0].strip()
            if node_id:
                return (node_id, cast(TestOutcome, outcome))
    return None


def _parse_verbose_result_line(stripped: str) -> tuple[str, TestOutcome] | None:
    for suffix, outcome in (
        (" PASSED", "passed"),
        (" FAILED", "failed"),
        (" SKIPPED", "skipped"),
        (" ERROR", "error"),
    ):
        if suffix in stripped:
            node_id = stripped.rsplit(suffix, 1)[0].strip()
            if node_id and "::" in node_id:
                return (node_id, cast(TestOutcome, outcome))
    return None


def _build_collect_command(*, project_root: str) -> list[str]:
    plan = build_pytest_launch_plan(project_root)
    return build_pytest_command(plan, ["--collect-only", "-q"])


def _parse_collect_output(stdout: str, *, project_root: str) -> list[DiscoveredTestNode]:
    """Parse ``pytest --collect-only -q`` output into TestNode objects."""
    root = Path(project_root)
    nodes: list[DiscoveredTestNode] = []
    seen_files: set[str] = set()
    seen_node_ids: set[str] = set()

    for line in stdout.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("=") or stripped.startswith("-"):
            continue

        node_id = _extract_node_id_from_collect_line(stripped)
        if node_id is None:
            continue

        parts = node_id.split("::")
        if len(parts) < 2:
            continue

        file_rel = parts[0]
        file_path = str((root / file_rel).resolve())

        if file_rel not in seen_files:
            seen_files.add(file_rel)
            nodes.append(DiscoveredTestNode(
                node_id=file_rel,
                name=Path(file_rel).name,
                file_path=file_path,
                line_number=0,
                kind="file",
            ))

        parent_id = file_rel
        for index, segment in enumerate(parts[1:-1], start=1):
            class_id = "::".join(parts[: index + 1])
            if class_id not in seen_node_ids:
                seen_node_ids.add(class_id)
                nodes.append(DiscoveredTestNode(
                    node_id=class_id,
                    name=segment,
                    file_path=file_path,
                    line_number=0,
                    kind="class",
                    parent_id=parent_id,
                ))
            parent_id = class_id

        if node_id not in seen_node_ids:
            seen_node_ids.add(node_id)
            nodes.append(DiscoveredTestNode(
                node_id=node_id,
                name=parts[-1],
                file_path=file_path,
                line_number=0,
                kind="function",
                parent_id=parent_id,
            ))

    return _apply_line_numbers(nodes)


def _extract_node_id_from_collect_line(stripped: str) -> str | None:
    if "::" not in stripped:
        return None
    token = stripped.split(" ")[0] if " <" in stripped else stripped
    return token if "::" in token else None


def _apply_line_numbers(nodes: list[DiscoveredTestNode]) -> list[DiscoveredTestNode]:
    line_cache: dict[tuple[str, tuple[str, ...], str], int] = {}
    updated: list[DiscoveredTestNode] = []
    for node in nodes:
        if node.kind != "function" or node.line_number != 0:
            updated.append(node)
            continue
        class_segments, func_name = _function_lookup_key(node.node_id)
        cache_key = (node.file_path, class_segments, func_name)
        if cache_key not in line_cache:
            line_cache[cache_key] = _resolve_function_line_number(
                Path(node.file_path),
                class_segments=class_segments,
                func_name=func_name,
            )
        line_number = line_cache[cache_key]
        if line_number == node.line_number:
            updated.append(node)
        else:
            updated.append(DiscoveredTestNode(
                node_id=node.node_id,
                name=node.name,
                file_path=node.file_path,
                line_number=line_number,
                kind=node.kind,
                parent_id=node.parent_id,
            ))
    return updated


def _function_lookup_key(node_id: str) -> tuple[tuple[str, ...], str]:
    parts = node_id.split("::")
    func_segment = parts[-1]
    func_name = _base_test_name(func_segment)
    class_segments = tuple(parts[1:-1])
    return class_segments, func_name


def _base_test_name(name: str) -> str:
    bracket_index = name.find("[")
    if bracket_index >= 0:
        return name[:bracket_index]
    return name


def _resolve_function_line_number(
    file_path: Path,
    *,
    class_segments: tuple[str, ...],
    func_name: str,
) -> int:
    if not file_path.is_file():
        return 0
    try:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(file_path))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return 0

    scope: ast.AST = tree
    for class_name in class_segments:
        matched_class = _find_class_in_scope(scope, class_name)
        if matched_class is None:
            return 0
        scope = matched_class

    matched_function = _find_test_function_in_scope(scope, func_name)
    if matched_function is None:
        return 0
    return int(matched_function.lineno)


def _find_class_in_scope(scope: ast.AST, class_name: str) -> ast.ClassDef | None:
    body = getattr(scope, "body", None)
    if not isinstance(body, list):
        return None
    for node in body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return node
    return None


def _find_test_function_in_scope(scope: ast.AST, func_name: str) -> ast.AST | None:
    body = getattr(scope, "body", None)
    if not isinstance(body, list):
        return None
    for node in body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
            return node
    return None
