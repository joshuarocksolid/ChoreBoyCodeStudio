"""Project tree model helpers for shell-side file browsing."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Collection

from app.core.models import ProjectFileEntry
from app.editors.generated_banner import generated_sibling


@dataclass
class ProjectTreeNode:
    """Node in a hierarchical project tree representation."""

    name: str
    relative_path: str
    absolute_path: str
    is_directory: bool
    children: list["ProjectTreeNode"] = field(default_factory=list)

    def sorted_children(self) -> list["ProjectTreeNode"]:
        """Directories first. A generated file sits immediately after its source."""
        return _sort_nodes(self.children)


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


def _sort_nodes(nodes: list[ProjectTreeNode]) -> list[ProjectTreeNode]:
    names = {node.name for node in nodes}
    return sorted(nodes, key=lambda node: _node_sort_key(node, names))


def _node_sort_key(node: ProjectTreeNode, sibling_names: Collection[str]) -> tuple[int, str, int, str]:
    if node.is_directory:
        return (0, node.name.lower(), 0, "")
    source = generated_sibling(node.name, sibling_names)
    if source is None:
        return (1, node.name.lower(), 0, "")
    return (1, source.lower(), 1, node.name.lower())


def _sort_tree(nodes: list[ProjectTreeNode]) -> list[ProjectTreeNode]:
    sorted_nodes = _sort_nodes(nodes)
    for node in sorted_nodes:
        node.children = _sort_tree(node.children)
    return sorted_nodes
