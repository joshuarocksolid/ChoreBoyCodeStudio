"""Your own classes in a form workbench (M5.4).

For every workbench built: the canvas draws the corner tag of a widget that
uses your own class, the realizer reads stand-in sizes from the project
registry, Insert's "Your widgets" lists the registry, and FB035 follows the
form. All of it reads declarations and files with ``ast``; nothing imports
project code (CONTRACTS section 10.4).
"""

from __future__ import annotations

from typing import Any

from app.features.form_builder.integration.custom_checks import attach_custom_checks
from app.features.form_builder.integration import preview_notice
from app.features.form_builder.integration.custom_registry import project_root_of, registry_for
from app.features.form_builder.qtside.canvas.layers import own_class


def _surface_of(workbench: Any) -> Any:
    """The form tab that holds the workbench (its stack is the workbench's parent)."""
    widget = workbench.parentWidget()
    while widget is not None:
        if hasattr(widget, "request_preview"):
            return widget
        widget = widget.parentWidget()
    return None


def _attach(workbench: Any) -> None:
    session = workbench._session
    root = project_root_of(session)
    registry = registry_for(root)
    canvas = workbench.canvas
    show = getattr(canvas, "show_layer", None)
    if callable(show):
        show(own_class.NAME, True)
    realizer = getattr(canvas, "_realizer", None)
    if realizer is not None:
        realizer.own_class_lookup = registry.find
    bind = getattr(workbench.insert, "bind_registry", None)
    if callable(bind):
        bind(registry)
    if root:
        attach_custom_checks(session, root)
    surface = _surface_of(workbench)
    if surface is not None:
        preview_notice.attach(surface, session)


def register(slots: Any) -> None:
    slots.on_workbench(_attach, module=__name__)
