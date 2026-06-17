"""Shell-owned project inventory snapshot orchestration."""

from __future__ import annotations

from dataclasses import dataclass

from app.project.file_excludes import EffectiveExcludes
from app.project.file_inventory import ProjectInventorySnapshot, build_project_inventory_snapshot


@dataclass(frozen=True)
class OwnedProjectInventory:
    """One project-generation inventory product shared across intelligence consumers."""

    generation: int
    excludes: EffectiveExcludes
    snapshot: ProjectInventorySnapshot


class ProjectInventoryOrchestrator:
    """Build and cache one :class:`ProjectInventorySnapshot` per project generation."""

    def __init__(self) -> None:
        self._generation = 0
        self._owned: OwnedProjectInventory | None = None
        self._tree_structure_signature: tuple[str, ...] | None = None

    def rebuild(self, project_root: str, effective_excludes: EffectiveExcludes) -> OwnedProjectInventory:
        """Walk the project once and store the shared snapshot."""
        self._generation += 1
        snapshot = build_project_inventory_snapshot(
            project_root,
            exclude_patterns=effective_excludes.as_list(),
        )
        self._owned = OwnedProjectInventory(
            generation=self._generation,
            excludes=effective_excludes,
            snapshot=snapshot,
        )
        return self._owned

    def clear(self) -> None:
        self._generation += 1
        self._owned = None
        self._tree_structure_signature = None

    def set_tree_structure_signature(self, signature: tuple[str, ...]) -> None:
        """Record the filtered project-tree signature from the latest load/rescan."""
        self._tree_structure_signature = tuple(signature)

    def tree_structure_signature(self) -> tuple[str, ...] | None:
        return self._tree_structure_signature

    @property
    def generation(self) -> int:
        return self._generation

    @property
    def owned(self) -> OwnedProjectInventory | None:
        return self._owned

    @property
    def snapshot(self) -> ProjectInventorySnapshot | None:
        if self._owned is None:
            return None
        return self._owned.snapshot

    def python_paths_fingerprint(self) -> tuple[str, ...] | None:
        if self._owned is None:
            return None
        return self._owned.snapshot.python_file_paths
