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
    return (
        "Plugins need FreeCAD 1.0. "
        "Running, debugging, and the Python console need FreeCAD 1.0 too, "
        "because all of them start /opt/freecad/AppRun, which FreeCAD 0.21 blocks. "
        f"This runtime is {freecad_version}.\n\n"
        f"{detail}\n\n"
        "Click Copy Details and post them to the LibrePy group."
    )


def present_plugin_host_unavailable(parent: object, detail: str) -> None:
    """Show the FreeCAD 1.0 explanation for a plugin-host start failure on FreeCAD 0.x.

    On FreeCAD 1.0 or newer the explanation would be wrong, so the status bar
    warning and the log carry the failure instead.
    """
    if freecad_is_at_least_1(freecad_version_label()):
        return
    from app.shell.startup_dialogs import present_freecad_requirement

    present_freecad_requirement(parent, detail)  # type: ignore[arg-type]


def freecad_is_at_least_1(version_label: str) -> bool:
    """Return True for a known FreeCAD version of 1.0 or newer."""
    major = version_label.split(".", 1)[0]
    return major.isdigit() and int(major) >= 1
