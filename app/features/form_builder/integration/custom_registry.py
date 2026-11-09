"""The project's own-class registry, bound to ``cbcs/project.json`` (M5.4, UX-CUST-006).

``ProjectRegistry`` implements the popover's ``OwnClassPort``. The list lives
under ``form_builder.custom_widgets``. A write is atomic (``project_settings``)
and not on any form's undo stack. A form outside a project has no registry:
reads are empty and writes do nothing.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional, Tuple

from app.features.form_builder.engine.project import custom_widgets as cw
from app.features.form_builder.engine.project.adoption import manifest_path
from app.features.form_builder.engine.project.fs import ProjectOpError
from app.features.form_builder.integration import project_settings


def project_root_of(session: Any) -> Optional[str]:
    """The project a form belongs to, or None for a form outside any project."""
    scope = getattr(session, "scope", None)
    if scope is None or getattr(scope, "kind", "external") == "external":
        return None
    root = getattr(scope, "project_root", None)
    return str(root) if root else None


class _SettingsStore(cw.RegistryStore):
    def __init__(self, root: str) -> None:
        self._root = root
        self._seen: Optional[Tuple[int, int]] = None
        self._cached: Any = None

    def load(self) -> Any:
        try:
            info = os.stat(manifest_path(self._root))
            key: Optional[Tuple[int, int]] = (info.st_mtime_ns, info.st_size)
        except OSError:
            key = None
        if key is not None and key == self._seen:
            return self._cached
        try:
            value = project_settings.get_setting(self._root, cw.SETTING)
        except ProjectOpError:
            value = None
        self._seen, self._cached = key, value
        return value

    def save(self, value: Any) -> None:
        project_settings.set_setting(self._root, cw.SETTING, value)
        self._seen = None


class ProjectRegistry:
    def __init__(self, project_root: Optional[str]) -> None:
        self._root = project_root
        self._registry = cw.CustomWidgetRegistry(_SettingsStore(project_root)) if project_root else None

    @property
    def project_root(self) -> Optional[str]:
        return self._root

    def entries(self) -> Tuple[cw.RegistryEntry, ...]:
        return self._registry.entries() if self._registry is not None else ()

    def find(self, class_name: str) -> Optional[cw.RegistryEntry]:
        return self._registry.find(class_name) if self._registry is not None else None

    def upsert(self, entry: cw.RegistryEntry) -> bool:
        if self._registry is None:
            return False
        try:
            return self._registry.upsert(entry)
        except ProjectOpError:
            return False

    def remove(self, class_name: str) -> bool:
        if self._registry is None:
            return False
        try:
            return self._registry.remove(class_name)
        except ProjectOpError:
            return False


_BY_ROOT: Dict[str, ProjectRegistry] = {}


def registry_for(project_root: Optional[str]) -> ProjectRegistry:
    """One registry object per project root, so its manifest cache is shared by every form tab."""
    if not project_root:
        return ProjectRegistry(None)
    key = os.path.abspath(project_root)
    found = _BY_ROOT.get(key)
    if found is None:
        found = ProjectRegistry(key)
        _BY_ROOT[key] = found
    return found


def registry_of(session: Any) -> ProjectRegistry:
    return registry_for(project_root_of(session))


__all__ = ["ProjectRegistry", "project_root_of", "registry_for", "registry_of"]
