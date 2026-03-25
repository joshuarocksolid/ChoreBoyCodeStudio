"""Unit tests for test discovery service."""
from __future__ import annotations

import pytest

from app.run.test_discovery_service import (
    DiscoveredTestNode,
    DiscoveredTestResult,
    DiscoveryResult,
    _parse_collect_output,
    parse_test_results,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Collection output parsing
# ---------------------------------------------------------------------------

_SAMPLE_COLLECT_OUTPUT = """\
tests/test_basics.py::test_hello
tests/test_basics.py::test_goodbye
tests/test_math.py::TestCalculator::test_add
tests/test_math.py::TestCalculator::test_multiply

4 tests collected in 0.05s
"""


def test_parse_collect_output_builds_file_class_function_hierarchy(tmp_path) -> None:
    nodes = _parse_collect_output(_SAMPLE_COLLECT_OUTPUT, project_root=str(tmp_path))

    file_nodes = [n for n in nodes if n.kind == "file"]
    class_nodes = [n for n in nodes if n.kind == "class"]
    func_nodes = [n for n in nodes if n.kind == "function"]

    assert len(file_nodes) == 2
    assert file_nodes[0].name == "test_basics.py"
    assert file_nodes[1].name == "test_math.py"

    assert len(class_nodes) == 1
    assert class_nodes[0].name == "TestCalculator"
    assert class_nodes[0].parent_id == "tests/test_math.py"

    assert len(func_nodes) == 4
    # Direct functions
    assert func_nodes[0].name == "test_hello"
    assert func_nodes[0].parent_id == "tests/test_basics.py"
    # Class method
    assert func_nodes[2].name == "test_add"
    assert func_nodes[2].parent_id == "tests/test_math.py::TestCalculator"


def test_parse_collect_output_handles_empty_output(tmp_path) -> None:
    nodes = _parse_collect_output("", project_root=str(tmp_path))
    assert nodes == []


def test_parse_collect_output_ignores_separator_lines(tmp_path) -> None:
    output = """\
==================== test session starts ====================
tests/test_foo.py::test_bar

1 test collected
"""
    nodes = _parse_collect_output(output, project_root=str(tmp_path))
    func_nodes = [n for n in nodes if n.kind == "function"]
    assert len(func_nodes) == 1
    assert func_nodes[0].name == "test_bar"


# ---------------------------------------------------------------------------
# Test result parsing
# ---------------------------------------------------------------------------


def test_parse_test_results_from_verbose_output() -> None:
    output = """\
tests/test_foo.py::test_pass PASSED
tests/test_foo.py::test_fail FAILED
tests/test_foo.py::test_skip SKIPPED
tests/test_foo.py::test_err ERROR
"""
    results = parse_test_results(output)
    assert len(results) == 4
    assert results[0].outcome == "passed"
    assert results[1].outcome == "failed"
    assert results[2].outcome == "skipped"
    assert results[3].outcome == "error"


def test_parse_test_results_empty_output() -> None:
    results = parse_test_results("")
    assert results == []


# ---------------------------------------------------------------------------
# TestCollectionResult helpers
# ---------------------------------------------------------------------------


def test_collection_result_kind_filters() -> None:
    result = DiscoveryResult(nodes=[
        DiscoveredTestNode(node_id="f1", name="test_a.py", file_path="/f1", line_number=0, kind="file"),
        DiscoveredTestNode(node_id="f1::C", name="C", file_path="/f1", line_number=0, kind="class", parent_id="f1"),
        DiscoveredTestNode(node_id="f1::C::t", name="t", file_path="/f1", line_number=0, kind="function", parent_id="f1::C"),
    ])
    assert len(result.file_nodes()) == 1
    assert len(result.class_nodes()) == 1
    assert len(result.function_nodes()) == 1


def test_collection_result_succeeded_flag() -> None:
    assert DiscoveryResult().succeeded is True
    assert DiscoveryResult(error_message="fail").succeeded is False
