"""Project-layer filesystem import resolution."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from app.core.models import ProjectMetadata
from app.project.import_layout import (
    ProjectImportLayout,
    resolve_import_at_base,
    resolve_project_import_layout,
)
from app.project.runtime_import_probe import is_runtime_module_importable


@dataclass(frozen=True)
class ImportResolution:
    module_name: str
    is_resolved: bool
    resolved_path: str | None


def resolve_project_import(
    project_root: str,
    module_name: str,
    known_runtime_modules: frozenset[str] | None = None,
    allow_runtime_import_probe: bool = False,
    *,
    metadata: ProjectMetadata | None = None,
    layout: ProjectImportLayout | None = None,
) -> ImportResolution:
    """Resolve absolute module import against project files and runtime modules."""
    top_level = module_name.split(".")[0]
    if known_runtime_modules and top_level in known_runtime_modules:
        return ImportResolution(module_name=module_name, is_resolved=True, resolved_path=None)

    resolved_layout = layout or resolve_project_import_layout(project_root, metadata)
    for base in resolved_layout.import_search_bases:
        resolved_path = resolve_import_at_base(base, module_name)
        if resolved_path is not None:
            return ImportResolution(
                module_name=module_name,
                is_resolved=True,
                resolved_path=resolved_path,
            )

    if allow_runtime_import_probe and is_runtime_module_importable(top_level):
        return ImportResolution(module_name=module_name, is_resolved=True, resolved_path=None)
    return ImportResolution(module_name=module_name, is_resolved=False, resolved_path=None)


def resolve_module_binding(
    project_root: str,
    *,
    bindings: Mapping[str, str],
    binding_name: str,
    known_runtime_modules: frozenset[str] | None = None,
    allow_runtime_import_probe: bool = False,
    metadata: ProjectMetadata | None = None,
    layout: ProjectImportLayout | None = None,
) -> ImportResolution:
    """Resolve a local import-binding name into a project module."""
    module_name = bindings.get(binding_name)
    if module_name is None:
        return ImportResolution(module_name="", is_resolved=False, resolved_path=None)
    return resolve_project_import(
        project_root,
        module_name,
        known_runtime_modules=known_runtime_modules,
        allow_runtime_import_probe=allow_runtime_import_probe,
        metadata=metadata,
        layout=layout,
    )
