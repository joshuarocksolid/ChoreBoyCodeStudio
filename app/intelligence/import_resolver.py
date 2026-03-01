"""Import resolution helper facade."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ImportResolution:
    module_name: str
    is_resolved: bool
    resolved_path: str | None


def resolve_project_import(project_root: str, module_name: str) -> ImportResolution:
    """Resolve absolute module import against project files."""
    root = Path(project_root).expanduser().resolve()
    module_path = Path(*module_name.split("."))
    module_file = (root / module_path).with_suffix(".py")
    package_init = root / module_path / "__init__.py"
    if module_file.exists():
        return ImportResolution(module_name=module_name, is_resolved=True, resolved_path=str(module_file.resolve()))
    if package_init.exists():
        return ImportResolution(module_name=module_name, is_resolved=True, resolved_path=str(package_init.resolve()))
    return ImportResolution(module_name=module_name, is_resolved=False, resolved_path=None)
