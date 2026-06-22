"""Unit tests for breakpoint store encapsulation helpers."""

from __future__ import annotations

import pytest

from app.debug.debug_breakpoints import build_breakpoint
from app.shell.breakpoint_store import BreakpointStore

pytestmark = pytest.mark.unit


def test_breakpoint_store_clear_file_and_remap_paths() -> None:
    store = BreakpointStore()
    store.set_line_enabled("/tmp/project/old.py", 2, enabled=True)
    store.set_line_enabled("/tmp/project/old.py", 5, enabled=True)
    store.set_spec(build_breakpoint("/tmp/project/old.py", 2, verified=True))

    store.remap_paths({"/tmp/project/old.py": "/tmp/project/new.py"})

    assert store.lines_for_file("/tmp/project/new.py") == {2, 5}
    assert store.lines_for_file("/tmp/project/old.py") == set()
    assert store.get_spec("/tmp/project/new.py", 2) is not None
    assert store.get_spec("/tmp/project/old.py", 2) is None

    store.clear_file("/tmp/project/new.py")
    assert store.lines_for_file("/tmp/project/new.py") == set()
    assert store.get_spec("/tmp/project/new.py", 2) is None


def test_breakpoint_store_restore_session_breakpoints() -> None:
    store = BreakpointStore()
    ensured: list[tuple[str, int]] = []

    store.restore_session_breakpoints(
        {
            "/tmp/project/a.py": {1, 3},
            "/tmp/project/b.py": {7},
        },
        ensure_spec=lambda path, line: ensured.append((path, line)) or store.ensure_spec(path, line),
    )

    assert store.lines_for_file("/tmp/project/a.py") == {1, 3}
    assert store.lines_for_file("/tmp/project/b.py") == {7}
    assert sorted(ensured) == [("/tmp/project/a.py", 1), ("/tmp/project/a.py", 3), ("/tmp/project/b.py", 7)]
    assert store.get_spec("/tmp/project/a.py", 1) is not None


def test_breakpoint_store_list_all_and_get_spec() -> None:
    store = BreakpointStore()
    spec = build_breakpoint("/tmp/project/main.py", 4, verified=True)
    store.set_spec(spec)
    store.set_line_enabled(spec.file_path, spec.line_number, enabled=True)

    listed = store.list_all()
    assert len(listed) == 1
    assert listed[0].breakpoint_id == spec.breakpoint_id
    assert store.get_spec(spec.file_path, spec.line_number) == spec
    assert store.get_spec(spec.file_path, 99) is None
    assert store.has_any_breakpoints() is True

    store.clear_all()
    assert store.list_all() == []
    assert store.has_any_breakpoints() is False


def test_breakpoint_store_lines_for_file_returns_independent_copy() -> None:
    store = BreakpointStore()
    store.set_line_enabled("/tmp/project/main.py", 4, enabled=True)

    lines = store.lines_for_file("/tmp/project/main.py")
    lines.add(99)

    assert store.lines_for_file("/tmp/project/main.py") == {4}


def test_breakpoint_store_lines_snapshot_returns_independent_copy() -> None:
    store = BreakpointStore()
    store.set_line_enabled("/tmp/project/main.py", 2, enabled=True)

    snapshot = store.lines_snapshot()
    snapshot["/tmp/project/main.py"].add(99)
    snapshot["/tmp/project/other.py"] = {7}

    assert store.lines_for_file("/tmp/project/main.py") == {2}
    assert store.lines_for_file("/tmp/project/other.py") == set()


def test_breakpoint_store_restore_session_breakpoints_isolates_caller_mutation() -> None:
    store = BreakpointStore()
    caller_lines = {1, 3}
    caller_dict = {"/tmp/project/a.py": caller_lines}

    store.restore_session_breakpoints(
        caller_dict,
        ensure_spec=store.ensure_spec,
    )

    caller_lines.add(99)
    caller_dict["/tmp/project/b.py"] = {7}

    assert store.lines_for_file("/tmp/project/a.py") == {1, 3}
    assert store.lines_for_file("/tmp/project/b.py") == set()


def test_breakpoint_store_enabled_lines_have_matching_specs() -> None:
    store = BreakpointStore()
    store.set_line_enabled("/tmp/project/main.py", 5, enabled=True)

    assert store.get_spec("/tmp/project/main.py", 5) is not None

    store.set_line_enabled("/tmp/project/main.py", 5, enabled=False)

    assert store.get_spec("/tmp/project/main.py", 5) is None
    assert store.lines_for_file("/tmp/project/main.py") == set()
    assert store.has_any_breakpoints() is False


def test_breakpoint_store_remove_line_clears_gutter_and_spec() -> None:
    store = BreakpointStore()
    store.set_line_enabled("/tmp/project/main.py", 8, enabled=True)
    store.set_line_enabled("/tmp/project/main.py", 11, enabled=True)

    store.remove_line("/tmp/project/main.py", 8)

    assert store.lines_for_file("/tmp/project/main.py") == {11}
    assert store.get_spec("/tmp/project/main.py", 8) is None
    assert store.get_spec("/tmp/project/main.py", 11) is not None
