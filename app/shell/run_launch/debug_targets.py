"""Debug target memory for rerun-last-debug-target."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Union


@dataclass(frozen=True)
class ProjectTarget:
    """Last debug target: project default or active named configuration."""

    kind: str = "project"


@dataclass(frozen=True)
class ActiveFileTarget:
    """Last debug target: active editor Python file."""

    file_path: str
    kind: str = "active_file"


@dataclass(frozen=True)
class CurrentTestTarget:
    """Last debug target: pytest run for the current file."""

    target_path: str
    kind: str = "current_test"


@dataclass(frozen=True)
class TestNodeTarget:
    """Last debug target: a single pytest node."""

    node_id: str
    kind: str = "test_node"


DebugTarget = Union[ProjectTarget, ActiveFileTarget, CurrentTestTarget, TestNodeTarget]


def debug_target_from_mapping(payload: Mapping[str, object]) -> DebugTarget | None:
    """Parse a legacy debug-target dict into a typed :class:`DebugTarget`."""

    kind = str(payload.get("kind", "")).strip()
    if kind == "project":
        return ProjectTarget()
    if kind == "active_file":
        file_path = str(payload.get("file_path", "")).strip()
        if not file_path:
            return None
        return ActiveFileTarget(file_path=file_path)
    if kind == "current_test":
        target_path = str(payload.get("target_path", "")).strip()
        if not target_path:
            return None
        return CurrentTestTarget(target_path=target_path)
    if kind == "test_node":
        node_id = str(payload.get("node_id", "")).strip()
        if not node_id:
            return None
        return TestNodeTarget(node_id=node_id)
    return None
