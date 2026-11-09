"""Preview options of a form tab: style, screen, the Preview window and its picture (M5.5a).

For every workbench built, this makes the tab's ``PreviewControl`` (after
``custom`` has attached the stand-in notices), sends F5 on a form outside a
project and Ctrl+Shift+R through it, and puts Style and Screen in the Aa menu.
"""

from __future__ import annotations

from typing import Any

from app.features.form_builder.integration.preview_control import PreviewControl


def _surface_of(workbench: Any) -> Any:
    widget = workbench.parentWidget()
    while widget is not None:
        if hasattr(widget, "request_preview"):
            return widget
        widget = widget.parentWidget()
    return None


def _attach(workbench: Any) -> None:
    surface = _surface_of(workbench)
    notices = getattr(surface, "own_class_preview", None)
    if surface is None or notices is None:
        return
    control = PreviewControl(surface, notices)
    surface.preview_control = control
    surface._preview_listener = control.preview
    workbench.destroyed.connect(lambda *_args: control.close())


def register(slots: Any) -> None:
    slots.on_workbench(_attach, module=__name__)
