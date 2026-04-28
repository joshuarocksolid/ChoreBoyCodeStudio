"""Pytest-based test discovery for the test explorer."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import subprocess
from typing import Optional

from app.bootstrap.vendor_paths import resolve_vendor_root
from app.run.runtime_launch import resolve_runtime_executable, is_freecad_runtime_executable, build_runpy_bootstrap_payload


PYTEST_MISSING_MARKER = "cbcs:test_explorer:pytest_missing"
PYTEST_MISSING_MESSAGE = (
    "pytest is not bundled with this Code Studio install. "
    "Reinstall the editor or restore the bundled vendor/ directory."
)


@dataclass(frozen=True)
class DiscoveredTestNode:
    """One discovered test item in the collection tree."""

    node_id: str  # pytest node ID, e.g. tests/test_foo.py::TestClass::test_method
    name: str  # display name, e.g. test_method
    file_path: str  # absolute path to test file
    line_number: int  # 0-based line number (or 0 if unknown)
    kind: str  # "file", "class", "function"
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
    outcome: str  # "passed", "failed", "skipped", "error"
    message: str = ""
    file_path: str = ""
    line_number: int = 0


def discover_tests(project_root: str, *, timeout_seconds: int = 30) -> DiscoveryResult:
    """Discover pytest-compatible tests by running ``pytest --collect-only -q``."""
    normalized_root = str(Path(project_root).expanduser().resolve())
    command = _build_collect_command(project_root=normalized_root)

    try:
        result = subprocess.run(
            command,
            cwd=normalized_root,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env=_discovery_env(),
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

    This is a simple line-based parser for ``-v`` output format.
    """
    results: list[DiscoveredTestResult] = []
    for line in output.splitlines():
        stripped = line.strip()
        if " PASSED" in stripped:
            node_id = stripped.split(" PASSED")[0].strip()
            results.append(DiscoveredTestResult(node_id=node_id, outcome="passed"))
        elif " FAILED" in stripped:
            node_id = stripped.split(" FAILED")[0].strip()
            results.append(DiscoveredTestResult(node_id=node_id, outcome="failed"))
        elif " SKIPPED" in stripped:
            node_id = stripped.split(" SKIPPED")[0].strip()
            results.append(DiscoveredTestResult(node_id=node_id, outcome="skipped"))
        elif " ERROR" in stripped:
            node_id = stripped.split(" ERROR")[0].strip()
            results.append(DiscoveredTestResult(node_id=node_id, outcome="error"))
    return results


def _build_collect_command(*, project_root: str) -> list[str]:
    runtime_executable = resolve_runtime_executable(None)
    args = ["--collect-only", "-q", "--import-mode=importlib"]

    if is_freecad_runtime_executable(runtime_executable):
        payload = _build_apprun_pytest_payload(args)
        return [runtime_executable, "-c", payload]
    return [runtime_executable, "-m", "pytest"] + args


def _build_apprun_pytest_payload(pytest_args: list[str]) -> str:
    args_repr = repr(pytest_args)
    vendor_root = str(resolve_vendor_root())
    lines = [
        "import sys",
        f"sys.path.insert(0, {vendor_root!r})",
        "try:",
        "    import pytest",
        "except ModuleNotFoundError:",
        f"    sys.stderr.write({PYTEST_MISSING_MARKER!r} + '\\n')",
        "    sys.exit(2)",
        f"sys.exit(pytest.main({args_repr}))",
    ]
    return "\n".join(lines)


def _parse_collect_output(stdout: str, *, project_root: str) -> list[DiscoveredTestNode]:
    """Parse ``pytest --collect-only -q`` output into TestNode objects."""
    root = Path(project_root)
    nodes: list[DiscoveredTestNode] = []
    seen_files: set[str] = set()

    for line in stdout.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("=") or stripped.startswith("-"):
            continue
        if "::" not in stripped:
            continue

        # Remove trailing markers like " <Module ...>" or " <Function ...>"
        node_id = stripped.split(" ")[0] if " <" in stripped else stripped

        parts = node_id.split("::")
        if len(parts) < 2:
            continue

        file_rel = parts[0]
        file_path = str((root / file_rel).resolve())

        # Add file node if new
        if file_rel not in seen_files:
            seen_files.add(file_rel)
            nodes.append(DiscoveredTestNode(
                node_id=file_rel,
                name=Path(file_rel).name,
                file_path=file_path,
                line_number=0,
                kind="file",
            ))

        if len(parts) == 2:
            # Direct function: file::test_func
            nodes.append(DiscoveredTestNode(
                node_id=node_id,
                name=parts[1],
                file_path=file_path,
                line_number=0,
                kind="function",
                parent_id=file_rel,
            ))
        elif len(parts) == 3:
            # Class method: file::TestClass::test_method
            class_id = f"{file_rel}::{parts[1]}"
            class_name = parts[1]
            # Add class node if not yet seen
            if not any(n.node_id == class_id for n in nodes):
                nodes.append(DiscoveredTestNode(
                    node_id=class_id,
                    name=class_name,
                    file_path=file_path,
                    line_number=0,
                    kind="class",
                    parent_id=file_rel,
                ))
            nodes.append(DiscoveredTestNode(
                node_id=node_id,
                name=parts[2],
                file_path=file_path,
                line_number=0,
                kind="function",
                parent_id=class_id,
            ))

    return nodes


def _discovery_env():
    """Build environment for test discovery subprocess."""
    import os
    env = os.environ.copy()
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    return env
