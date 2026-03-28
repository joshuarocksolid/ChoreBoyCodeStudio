"""Unit tests for workflow adapter pytest request plumbing."""

from __future__ import annotations

import pytest

from app.plugins.workflow_adapters import run_pytest_with_workflow

pytestmark = pytest.mark.unit


class _FakeBroker:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def run_job(self, **kwargs):  # type: ignore[no-untyped-def]
        self.calls.append(dict(kwargs))
        return (
            type("Descriptor", (), {"title": "Builtin Pytest"})(),
            {
                "command": ["/opt/freecad/AppRun", "-c", "pytest"],
                "project_root": "/tmp/project",
                "return_code": 0,
                "stdout": "",
                "stderr": "",
                "elapsed_ms": 2.0,
                "failures": [],
            },
        )


def test_run_pytest_with_workflow_passes_target_node_and_filtered_pytest_args() -> None:
    broker = _FakeBroker()

    descriptor, result = run_pytest_with_workflow(
        broker,  # type: ignore[arg-type]
        project_root="/tmp/project",
        target_node_id="tests/test_demo.py::test_ok",
        pytest_args=["-k", "", "smoke", 123],  # type: ignore[list-item]
        timeout_seconds=45,
    )

    assert descriptor.title == "Builtin Pytest"
    assert result.return_code == 0
    assert len(broker.calls) == 1
    request = broker.calls[0]["request"]
    assert isinstance(request, dict)
    assert request["project_root"] == "/tmp/project"
    assert request["target_node_id"] == "tests/test_demo.py::test_ok"
    assert request["pytest_args"] == ["-k", "smoke", "123"]
    assert request["timeout_seconds"] == 45
