"""Open another project file from a form tab or a resource tab (the "Open" links of UX-RES-006, UX-RES-007)."""

from __future__ import annotations

from typing import Optional

from app.qt.QtWidgets import QWidget


def open_linked_file(widget: Optional[QWidget], path: str) -> bool:
    """Ask the tab that holds ``widget`` to open ``path``. False when no tab can.

    A tab surface keeps the shell's ``TabSurfaceRequest`` as ``_request``;
    ``open_linked_file`` on it is the one call the shell offers a provider for this.
    """
    current = widget
    while current is not None:
        request = getattr(current, "_request", None)
        opener = getattr(request, "open_linked_file", None)
        if callable(opener):
            opener(path)
            return True
        current = current.parentWidget()
    return False


__all__ = ["open_linked_file"]
