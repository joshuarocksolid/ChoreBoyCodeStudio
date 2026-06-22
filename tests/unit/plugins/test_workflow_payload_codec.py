"""Unit tests for workflow payload codec roundtrips."""

from __future__ import annotations

import pytest

from app.plugins.workflow_payload_codec import (
    parse_pytest_run_result,
    serialize_pytest_run_result,
)
from app.pytest.runner_service import PytestRunResult
from app.run.problem_parser import ProblemEntry

pytestmark = pytest.mark.unit


def test_pytest_run_result_roundtrip_preserves_failure_entries() -> None:
    original = PytestRunResult(
        command=["/opt/freecad/AppRun", "-c", "pytest", "-v"],
        project_root="/tmp/project",
        return_code=1,
        stdout="collected 1 item\n",
        stderr="",
        elapsed_ms=12.5,
        failures=[
            ProblemEntry(
                file_path="tests/test_demo.py",
                line_number=4,
                context="pytest",
                message="assert False",
            )
        ],
    )

    payload = serialize_pytest_run_result(original)
    restored = parse_pytest_run_result(payload)

    assert restored.command == original.command
    assert restored.project_root == original.project_root
    assert restored.return_code == original.return_code
    assert restored.stdout == original.stdout
    assert restored.stderr == original.stderr
    assert restored.elapsed_ms == original.elapsed_ms
    assert len(restored.failures) == 1
    assert restored.failures[0].file_path == "tests/test_demo.py"
    assert restored.failures[0].line_number == 4
    assert restored.failures[0].message == "assert False"
