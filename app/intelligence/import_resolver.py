"""Import resolution helper facade."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class ImportResolution:
    module_name: str
    is_resolved: bool
    resolved_path: str | None


def resolve_project_import(
    project_root: str,
    module_name: str,
    known_runtime_modules: frozenset[str] | None = None,
) -> ImportResolution:
    """Resolve absolute module import against project files and runtime modules."""
    top_level = module_name.split(".")[0]
    if known_runtime_modules and top_level in known_runtime_modules:
        return ImportResolution(module_name=module_name, is_resolved=True, resolved_path=None)
    root = Path(project_root).expanduser().resolve()
    module_path = Path(*module_name.split("."))
    for base in (root, root / "vendor"):
        module_file = (base / module_path).with_suffix(".py")
        package_init = base / module_path / "__init__.py"
        if module_file.exists():
            return ImportResolution(module_name=module_name, is_resolved=True, resolved_path=str(module_file.resolve()))
        if package_init.exists():
            return ImportResolution(module_name=module_name, is_resolved=True, resolved_path=str(package_init.resolve()))
    return ImportResolution(module_name=module_name, is_resolved=False, resolved_path=None)


def resolve_module_binding(
    project_root: str,
    *,
    bindings: Mapping[str, str],
    binding_name: str,
) -> ImportResolution:
    """Resolve a local import-binding name into a project module."""
    module_name = bindings.get(binding_name)
    if module_name is None:
        return ImportResolution(module_name="", is_resolved=False, resolved_path=None)
    return resolve_project_import(project_root, module_name)
