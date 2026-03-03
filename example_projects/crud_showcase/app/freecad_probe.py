"""Optional FreeCAD capability probe.

This module demonstrates safe detection of FreeCAD availability inside the
AppRun runtime.  When FreeCAD is not installed (e.g. during development on a
normal desktop), every function returns a graceful fallback message instead of
crashing.
"""

from __future__ import annotations


def probe_freecad() -> dict[str, str]:
    """Return a dict of FreeCAD capability facts, or fallback messages."""
    results: dict[str, str] = {}

    try:
        import FreeCAD  # type: ignore[import-untyped]
        results["FreeCAD available"] = "Yes"
        results["FreeCAD version"] = FreeCAD.Version()[0] + "." + FreeCAD.Version()[1]
    except ImportError:
        results["FreeCAD available"] = "No (not in this runtime)"
        results["FreeCAD version"] = "N/A"

    try:
        import FreeCAD  # type: ignore[import-untyped]  # noqa: F811
        doc = FreeCAD.newDocument("ProbeTest")
        box = doc.addObject("Part::Box", "TestBox")
        results["Headless Part::Box"] = f"Created — dims {box.Length}x{box.Width}x{box.Height}"
        FreeCAD.closeDocument("ProbeTest")
    except ImportError:
        results["Headless Part::Box"] = "Skipped (FreeCAD not available)"
    except Exception as exc:
        results["Headless Part::Box"] = f"Failed: {exc}"

    return results
