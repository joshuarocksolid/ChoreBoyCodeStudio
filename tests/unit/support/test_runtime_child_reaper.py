"""Unit tests for runtime child reaper helpers."""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from testing.runtime_child_reaper import (
    invalidate_proc_cache,
    leaked_runtime_child_pids,
    reap_leaked_runtime_children,
)

pytestmark = pytest.mark.unit


def test_reap_leaked_runtime_children_no_op_when_no_targets() -> None:
    reap_leaked_runtime_children()


def test_leaked_runtime_child_pids_uses_cached_children_map() -> None:
    invalidate_proc_cache()
    build_calls: list[bool] = []

    def _counting_build() -> dict[int, list[int]]:
        build_calls.append(True)
        return {1000: [1001], 1001: [1002]}

    with patch("testing.runtime_child_reaper._build_children_map", side_effect=_counting_build):
        with patch(
            "testing.runtime_child_reaper.read_proc_cmdline",
            side_effect=lambda pid: "run_runner.py" if pid == 1002 else "",
        ):
            with patch("testing.runtime_child_reaper.os.getpid", return_value=1000):
                assert leaked_runtime_child_pids() == [1002]
                assert leaked_runtime_child_pids() == [1002]
    assert len(build_calls) == 1


def test_reap_invalidates_cache_after_targets_found() -> None:
    invalidate_proc_cache()
    build_calls: list[bool] = []

    def _counting_build() -> dict[int, list[int]]:
        build_calls.append(True)
        return {2000: [2001]}

    with patch("testing.runtime_child_reaper._build_children_map", side_effect=_counting_build):
        with patch(
            "testing.runtime_child_reaper.leaked_runtime_child_pids",
            side_effect=[[2001], []],
        ):
            with patch("testing.runtime_child_reaper.pid_alive", return_value=False):
                reap_leaked_runtime_children()
                time.sleep(0.01)
                leaked_runtime_child_pids()
    assert len(build_calls) >= 1
