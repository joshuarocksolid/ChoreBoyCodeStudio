"""Slug and machine-file path for one project.

The engine module takes a path. This module is the place that knows the
state root and the project manifest.
"""

from __future__ import annotations

import os
from typing import Optional, Tuple

from app.bootstrap.paths import project_manifest_path, resolve_global_state_root
from app.features.form_builder.engine.data.machine import (
    MachineEntry,
    MachineFile,
    load_machine,
    machine_path,
    rename_entry,
    save_machine,
)
from app.project.project_manifest import load_project_manifest
from app.support.preflight_paths import sanitize_project_name


def project_slug(project_root: str) -> str:
    """The manifest name, slugified. A missing manifest uses the directory name."""

    name = ""
    path = project_manifest_path(project_root)
    if os.path.isfile(str(path)):
        try:
            name = load_project_manifest(path).name or ""
        except Exception:
            name = ""
    if not name:
        name = os.path.basename(os.path.abspath(project_root))
    return sanitize_project_name(name)


def project_machine_path(project_root: str, *, state_root: Optional[str] = None) -> str:
    root = str(resolve_global_state_root(state_root))
    return machine_path(root, project_slug(project_root))


def load_project_machine(project_root: str, *, state_root: Optional[str] = None) -> MachineFile:
    return load_machine(project_machine_path(project_root, state_root=state_root))


def save_project_machine(
    project_root: str,
    entries: Tuple[Tuple[str, MachineEntry], ...],
    *,
    state_root: Optional[str] = None,
) -> None:
    save_machine(
        project_machine_path(project_root, state_root=state_root),
        entries,
        project_root=project_root,
    )


def rename_project_entry(
    project_root: str,
    old: str,
    new: str,
    *,
    state_root: Optional[str] = None,
) -> None:
    rename_entry(
        project_machine_path(project_root, state_root=state_root),
        old,
        new,
        project_root=project_root,
    )
