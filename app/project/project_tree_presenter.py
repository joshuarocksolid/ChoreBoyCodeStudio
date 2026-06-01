"""View-model helpers for rendering project tree nodes."""

from __future__ import annotations

from dataclasses import dataclass

from app.project.project_tree import ProjectTreeNode


@dataclass(frozen=True)
class ProjectTreeDisplayNode:
    """UI-oriented tree node payload."""

    name: str
    display_label: str
    relative_path: str
    absolute_path: str
    is_directory: bool
    children: list["ProjectTreeDisplayNode"]


def build_project_tree_display(
    nodes: list[ProjectTreeNode],
    *,
    source_roots: tuple[str, ...] = (),
) -> list[ProjectTreeDisplayNode]:
    """Build display nodes from project tree nodes."""
    configured_roots = {entry.strip().replace("\\", "/").strip("/") for entry in source_roots if entry.strip()}
    return [_to_display_node(node, configured_roots) for node in nodes]


def _to_display_node(node: ProjectTreeNode, source_roots: set[str]) -> ProjectTreeDisplayNode:
    label = f"{node.name}/" if node.is_directory else node.name
    relative = node.relative_path.replace("\\", "/").strip("/")
    if node.is_directory and relative in source_roots:
        label = f"{label} [source root]"
    return ProjectTreeDisplayNode(
        name=node.name,
        display_label=label,
        relative_path=node.relative_path,
        absolute_path=node.absolute_path,
        is_directory=node.is_directory,
        children=[_to_display_node(child, source_roots) for child in node.children],
    )
