"""Walk from a Data-tab widget to the session, the canvas and the project."""

from __future__ import annotations

from typing import Any, Optional

from app.features.form_builder.qtside.data_panel.model import project_root as _project_root


def session_of(widget: object) -> Any:
    current = widget
    seen = 0
    while current is not None and seen < 16:
        for owner in (
            current,
            getattr(current, "_services", None),
            getattr(current, "_workbench", None),
            getattr(current, "_host", None),
        ):
            session = getattr(owner, "session", None)
            if getattr(session, "document", None) is not None:
                return session
        parent = getattr(current, "parentWidget", None)
        current = parent() if callable(parent) else None
        seen += 1
    return None


def project_root_of(widget: object) -> str:
    session = session_of(widget)
    return _project_root(session, widget) if session is not None else _project_root(None, widget)


def canvas_of(widget: object) -> Any:
    current = widget
    seen = 0
    while current is not None and seen < 16:
        canvas = getattr(current, "canvas", None)
        if canvas is not None and hasattr(canvas, "show_layer"):
            return canvas
        parent = getattr(current, "parentWidget", None)
        current = parent() if callable(parent) else None
        seen += 1
    return None


def note_data_tab(widget: object, which: str, visible: bool) -> None:
    """Show the column chip while a Data tab is on screen."""

    canvas = canvas_of(widget)
    if canvas is None:
        return
    flags = getattr(canvas, "_cbcs_data_tabs", None)
    if not isinstance(flags, dict):
        flags = {"left": False, "inspector": False}
        canvas._cbcs_data_tabs = flags
    flags[which] = visible
    if flags["left"] or flags["inspector"]:
        canvas.show_layer("bind_chips", True)
    else:
        canvas.hide_layer("bind_chips")


def narrate(widget: object, sentence: str) -> None:
    current: Optional[object] = widget
    seen = 0
    while current is not None and seen < 16:
        fn = getattr(current, "narrate", None)
        if callable(fn) and sentence:
            fn(sentence)
            return
        parent = getattr(current, "parentWidget", None)
        current = parent() if callable(parent) else None
        seen += 1


def surface_of(widget: object) -> Any:
    """The form tab, when it can create a window-file method."""

    current = widget
    seen = 0
    while current is not None and seen < 16:
        if getattr(current, "session", None) is not None and hasattr(current, "code_bridge"):
            return current
        parent = getattr(current, "parentWidget", None)
        current = parent() if callable(parent) else None
        seen += 1
    return None
