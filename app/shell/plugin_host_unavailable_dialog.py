"""Isolated copy for the plugin-host startup dialog.

The look of this dialog is temporary. Restyle this function when the
owner-approved startup prototype lands.
"""

from __future__ import annotations


def freecad_version_label() -> str:
    """Return FreeCAD's version, or ``unknown`` when FreeCAD cannot be imported."""
    import importlib

    try:
        freecad = importlib.import_module("FreeCAD")
    except Exception:
        return "unknown"
    try:
        version = freecad.Version()
    except Exception:
        return "unknown"
    if isinstance(version, (list, tuple)):
        parts = [str(part) for part in list(version)[:3] if str(part)]
        if parts:
            return ".".join(parts)
    text = str(version).strip()
    return text or "unknown"


def plugin_host_unavailable_message(detail: str, freecad_version: str) -> str:
    """Return the dialog body. ``freecad_version`` is ``unknown`` when Version() is missing."""
    return f"Plugins need FreeCAD 1.0. This runtime is {freecad_version}.\n\n{detail}"


def present_plugin_host_unavailable(parent: object, detail: str) -> None:
    """Show the one dialog that names the FreeCAD version and the host error."""
    from PySide2.QtWidgets import QMessageBox

    QMessageBox.warning(
        parent,  # type: ignore[arg-type]
        "Plugin runtime unavailable",
        plugin_host_unavailable_message(detail, freecad_version_label()),
    )
