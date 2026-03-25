"""Unit tests for test explorer panel model and helper behavior."""
from __future__ import annotations

import pytest

from app.run.test_discovery_service import DiscoveredTestNode, DiscoveryResult
from app.shell.test_explorer_panel import _OUTCOME_ICONS

pytestmark = pytest.mark.unit


def _sample_discovery() -> DiscoveryResult:
    return DiscoveryResult(nodes=[
        DiscoveredTestNode(node_id="tests/test_foo.py", name="test_foo.py", file_path="/p/tests/test_foo.py", line_number=0, kind="file"),
        DiscoveredTestNode(node_id="tests/test_foo.py::test_hello", name="test_hello", file_path="/p/tests/test_foo.py", line_number=5, kind="function", parent_id="tests/test_foo.py"),
        DiscoveredTestNode(node_id="tests/test_foo.py::test_goodbye", name="test_goodbye", file_path="/p/tests/test_foo.py", line_number=10, kind="function", parent_id="tests/test_foo.py"),
    ])


def test_discovery_result_kind_filters() -> None:
    result = _sample_discovery()
    assert len(result.file_nodes()) == 1
    assert len(result.function_nodes()) == 2


def test_outcome_icons_cover_all_states() -> None:
    assert "passed" in _OUTCOME_ICONS
    assert "failed" in _OUTCOME_ICONS
    assert "skipped" in _OUTCOME_ICONS
    assert "error" in _OUTCOME_ICONS
    assert "not_run" in _OUTCOME_ICONS


def test_discovery_result_succeeded_is_true_without_error() -> None:
    result = DiscoveryResult(nodes=[])
    assert result.succeeded is True


def test_discovery_result_succeeded_is_false_with_error() -> None:
    result = DiscoveryResult(error_message="test error")
    assert result.succeeded is False


def test_node_parent_id_links_function_to_file() -> None:
    result = _sample_discovery()
    func = result.function_nodes()[0]
    assert func.parent_id == "tests/test_foo.py"
    assert func.name == "test_hello"
