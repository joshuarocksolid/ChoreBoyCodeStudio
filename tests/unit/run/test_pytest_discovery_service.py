"""Unit tests for test discovery service."""
from __future__ import annotations

import pytest

from app.pytest.launch_plan import PYTEST_MISSING_MARKER, build_apprun_pytest_payload
from app.pytest.discovery_service import (
    PYTEST_MISSING_MESSAGE,
    DiscoveredTestNode,
    DiscoveredTestResult,
    DiscoveryResult,
    _build_collect_command,
    _parse_collect_output,
    discover_tests,
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


def test_parse_collect_output_handles_nested_classes_and_parametrized_tests(tmp_path) -> None:
    output = """\
tests/test_nested.py::TestOuter::TestInner::test_deep
tests/test_params.py::test_values[1-2]
tests/test_params.py::test_values[3-4]
"""
    nodes = _parse_collect_output(output, project_root=str(tmp_path))

    class_nodes = [n for n in nodes if n.kind == "class"]
    func_nodes = [n for n in nodes if n.kind == "function"]

    assert {node.node_id for node in class_nodes} == {
        "tests/test_nested.py::TestOuter",
        "tests/test_nested.py::TestOuter::TestInner",
    }
    assert any(node.node_id == "tests/test_nested.py::TestOuter::TestInner::test_deep" for node in func_nodes)
    assert any(node.node_id == "tests/test_params.py::test_values[1-2]" for node in func_nodes)
    assert any(node.node_id == "tests/test_params.py::test_values[3-4]" for node in func_nodes)


def test_parse_collect_output_populates_function_line_numbers(tmp_path) -> None:
    test_file = tmp_path / "tests" / "test_sample.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text(
        """\
class TestCase:
    def test_method(self):
        assert True

def test_top_level():
    assert True
""",
        encoding="utf-8",
    )
    output = """\
tests/test_sample.py::TestCase::test_method
tests/test_sample.py::test_top_level
"""
    nodes = _parse_collect_output(output, project_root=str(tmp_path))
    function_nodes = {node.node_id: node.line_number for node in nodes if node.kind == "function"}

    assert function_nodes["tests/test_sample.py::TestCase::test_method"] == 2
    assert function_nodes["tests/test_sample.py::test_top_level"] == 5


def test_parse_test_results_handles_parametrized_node_ids_in_summary_output() -> None:
    output = (
        "FAILED tests/test_foo.py::test_values[1-2] - AssertionError\n"
        "PASSED tests/test_foo.py::test_values[3-4]\n"
    )
    results = parse_test_results(output)
    assert len(results) == 2
    assert results[0].node_id == "tests/test_foo.py::test_values[1-2]"
    assert results[1].node_id == "tests/test_foo.py::test_values[3-4]"


def test_discover_tests_uses_offscreen_qt_platform(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    captured_env: dict[str, str] | None = None

    monkeypatch.setattr(
        "app.pytest.discovery_service._build_collect_command",
        lambda *, project_root: ["/bin/sh", "-c", ":"],
    )

    def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal captured_env
        captured_env = kwargs.get("env")
        class _FakeCompleted:
            returncode = 0
            stdout = ""
            stderr = ""

        return _FakeCompleted()

    monkeypatch.delenv("QT_QPA_PLATFORM", raising=False)
    monkeypatch.setattr("app.pytest.discovery_service.subprocess.run", fake_run)

    discover_tests(str(tmp_path))

    assert captured_env is not None
    assert captured_env["QT_QPA_PLATFORM"] == "offscreen"


def test_build_collect_command_resolves_default_runtime_when_given_project_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.pytest.launch_plan import PytestLaunchPlan

    monkeypatch.setattr(
        "app.pytest.discovery_service.build_pytest_launch_plan",
        lambda project_root: PytestLaunchPlan(
            project_root=project_root,
            runtime_executable="/usr/bin/python3",
            run_tests_script=None,
            use_apprun_inline_payload=False,
        ),
    )

    command = _build_collect_command(project_root="/tmp/project")

    assert command[:3] == ["/usr/bin/python3", "-m", "pytest"]


# ---------------------------------------------------------------------------
# Test result parsing
# ---------------------------------------------------------------------------


def test_parse_test_results_from_summary_output() -> None:
    output = "FAILED tests/test_foo.py::test_fail - AssertionError\nPASSED tests/test_foo.py::test_pass\n"
    results = parse_test_results(output)
    assert len(results) == 2
    assert results[0].outcome == "failed"
    assert results[1].outcome == "passed"


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


# ---------------------------------------------------------------------------
# AppRun payload contract: editor vendor/ must be injected before pytest import
# ---------------------------------------------------------------------------


def test_apprun_payload_inserts_editor_vendor_before_pytest_import(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The AppRun -c payload must prepend the editor's vendor/ to sys.path
    before importing pytest, otherwise ChoreBoy (no system pytest) will raise
    ModuleNotFoundError and the Test Explorer fails."""
    monkeypatch.setattr(
        "app.pytest.launch_plan.resolve_vendor_root",
        lambda: "/opt/cbcs/vendor",
    )

    payload = build_apprun_pytest_payload(["--collect-only", "-q"])

    insert_pos = payload.find("sys.path.insert(0, '/opt/cbcs/vendor')")
    import_pos = payload.find("import pytest")
    main_pos = payload.find("pytest.main([")

    assert insert_pos != -1, "vendor/ path was not inserted into sys.path"
    assert import_pos != -1, "pytest is never imported"
    assert insert_pos < import_pos < main_pos, (
        "vendor/ must be on sys.path before `import pytest`, and import must "
        "precede pytest.main()."
    )


def test_apprun_payload_emits_marker_when_pytest_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If pytest still isn't importable, the payload must emit the
    PYTEST_MISSING_MARKER on stderr so the discovery error path can render
    a friendly message to the user."""
    monkeypatch.setattr(
        "app.pytest.launch_plan.resolve_vendor_root",
        lambda: "/opt/cbcs/vendor",
    )

    payload = build_apprun_pytest_payload(["--collect-only", "-q"])

    assert "except ModuleNotFoundError" in payload
    assert PYTEST_MISSING_MARKER in payload


def test_discover_tests_maps_pytest_missing_marker_to_friendly_message(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """When the AppRun subprocess emits the marker on stderr, the discovery
    result should surface the friendly message instead of leaking the raw
    marker token to the Test Explorer."""
    monkeypatch.setattr(
        "app.pytest.discovery_service._build_collect_command",
        lambda *, project_root: ["/bin/sh", "-c", ":"],
    )

    class _FakeCompleted:
        returncode = 2
        stdout = ""
        stderr = PYTEST_MISSING_MARKER + "\n"

    monkeypatch.setattr(
        "app.pytest.discovery_service.subprocess.run",
        lambda *args, **kwargs: _FakeCompleted(),
    )

    result = discover_tests(str(tmp_path))

    assert not result.succeeded
    assert result.error_message == PYTEST_MISSING_MESSAGE
    assert PYTEST_MISSING_MARKER not in result.error_message
