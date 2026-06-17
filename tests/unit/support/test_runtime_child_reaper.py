"""Unit tests for runtime child reaper helpers."""

from __future__ import annotations

import pytest

from testing.runtime_child_reaper import reap_leaked_runtime_children

pytestmark = pytest.mark.unit


def test_reap_leaked_runtime_children_no_op_when_no_targets() -> None:
    reap_leaked_runtime_children()
