"""Project tree model helpers for shell-side file browsing."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.core.models import ProjectFileEntry


@dataclass
class ProjectTreeNode:
    """Node in a hierarchical project tree representation."""

    name: str
    relative_path: str
    absolute_path: str
    is_directory: bool
    children: list["ProjectTreeNode"] = field(default_factory=list)

    def sorted_children(self) -> list["ProjectTreeNode"]:
        """Return children sorted with directories first, then lexical name."""
        return sorted(
            self.children,
            key=lambda node: (not node.is_directory, node.name.lower()),
        )


def build_project_tree(entries: list[ProjectFileEntry]) -> list[ProjectTreeNode]:
    """Build a deterministic hierarchical tree from flat project entries."""
    nodes_by_relative_path: dict[str, ProjectTreeNode] = {}

    for entry in entries:
        nodes_by_relative_path[entry.relative_path] = ProjectTreeNode(
            name=Path(entry.relative_path).name,
            relative_path=entry.relative_path,
            absolute_path=entry.absolute_path,
            is_directory=entry.is_directory,
        )

    _ensure_parent_directories(nodes_by_relative_path)

    root_nodes: list[ProjectTreeNode] = []
    for relative_path, node in sorted(nodes_by_relative_path.items(), key=lambda item: (item[0].count("/"), item[0])):
        parent_relative_path = _parent_relative_path(relative_path)
        if parent_relative_path is None:
            root_nodes.append(node)
            continue

        parent_node = nodes_by_relative_path[parent_relative_path]
        parent_node.children.append(node)

    return _sort_tree(root_nodes)


def _ensure_parent_directories(nodes_by_relative_path: dict[str, ProjectTreeNode]) -> None:
    for relative_path in list(nodes_by_relative_path.keys()):
        path_parts = relative_path.split("/")
        for depth in range(1, len(path_parts)):
            parent_relative_path = "/".join(path_parts[:depth])
            if parent_relative_path in nodes_by_relative_path:
                continue
            nodes_by_relative_path[parent_relative_path] = ProjectTreeNode(
                name=path_parts[depth - 1],
                relative_path=parent_relative_path,
                absolute_path="",
                is_directory=True,
            )


def _parent_relative_path(relative_path: str) -> str | None:
    if "/" not in relative_path:
        return None
    return relative_path.rsplit("/", 1)[0]


def _sort_tree(nodes: list[ProjectTreeNode]) -> list[ProjectTreeNode]:
    sorted_nodes = sorted(nodes, key=lambda node: (not node.is_directory, node.name.lower()))
    for node in sorted_nodes:
        node.children = _sort_tree(node.children)
    return sorted_nodes
