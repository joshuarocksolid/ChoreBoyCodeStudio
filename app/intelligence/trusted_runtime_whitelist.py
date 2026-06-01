"""Shared whitelist policy for trusted runtime module introspection."""

from __future__ import annotations

import re

TRUSTED_RUNTIME_ROOTS = frozenset(
    {
        "FreeCAD",
        "FreeCADGui",
        "PySide2",
        "QtCore",
        "QtGui",
        "QtWidgets",
    }
)
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def is_whitelisted_target_path(target_path: str) -> bool:
    """Return whether ``target_path`` is allowed for runtime introspection."""

    parts = [part for part in str(target_path or "").split(".") if part]
    if not parts or not _IDENTIFIER.match(parts[0]):
        return False
    if parts[0] not in TRUSTED_RUNTIME_ROOTS:
        return False
    return all(_IDENTIFIER.match(part) for part in parts)
