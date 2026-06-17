"""Shell-owned project inventory snapshot orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.core import constants
from app.core.models import LoadedProject
from app.project.file_excludes import EffectiveExcludes
from app.project.file_inventory import ProjectInventorySnapshot, build_project_inventory_snapshot
from app.project.import_layout import module_name_for_file, resolve_project_import_layout


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
        self._walk_count = 0

    def rebuild(self, project_root: str, effective_excludes: EffectiveExcludes) -> OwnedProjectInventory:
        """Walk the project once and store the shared snapshot."""
        self._generation += 1
        self._walk_count += 1
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

    def rebuild_from_loaded(
        self,
        loaded_project: LoadedProject,
        effective_excludes: EffectiveExcludes,
    ) -> OwnedProjectInventory:
        """Derive inventory from an already-enumerated project without a second disk walk."""
        self._generation += 1
        snapshot = _snapshot_from_loaded_project(loaded_project)
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
    def walk_count(self) -> int:
        """Number of disk walks performed by :meth:`rebuild`."""
        return self._walk_count

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


def _snapshot_from_loaded_project(loaded_project: LoadedProject) -> ProjectInventorySnapshot:
    root = Path(loaded_project.project_root).expanduser().resolve()
    layout = resolve_project_import_layout(root)
    meta_prefix = f"{constants.PROJECT_META_DIRNAME}/"
    python_paths = tuple(
        sorted(
            str(Path(entry.absolute_path).resolve())
            for entry in loaded_project.entries
            if not entry.is_directory
            and entry.relative_path.endswith(".py")
            and not entry.relative_path.startswith(meta_prefix)
        )
    )
    module_names = tuple(
        sorted(
            {
                name
                for path in python_paths
                if (name := module_name_for_file(layout, Path(path))) is not None
            }
        )
    )
    return ProjectInventorySnapshot(
        project_root=str(root),
        python_file_paths=python_paths,
        module_names=module_names,
    )
