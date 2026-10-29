"""Form > Main window ▸ Add menu bar, Add toolbar, Add status bar (UX-MAIN-002).

Absent, not disabled, on a form that is not a main window; a part a window can
only have once is absent once it has one.
"""

from __future__ import annotations

from typing import Any, Callable

from app.features.form_builder.engine.commands.catalog_ext.main_window import AddMainWindowPart
from app.features.form_builder.engine.query import actions as q
from app.features.form_builder.integration.form_menu_ext import FormMenuItem

_TITLE = "Main window"


def _main(surface: Any) -> bool:
    return q.is_main_window(surface.session.document)


def _lacking(part: str) -> Callable[[Any], bool]:
    def offered(surface: Any) -> bool:
        doc = surface.session.document
        return q.is_main_window(doc) and not q.parts(doc)[part]

    return offered


def _add(part: str) -> Callable[[Any], None]:
    def run(surface: Any) -> None:
        surface.session.log.execute(AddMainWindowPart(part))

    return run


def register(registry: object) -> None:
    add = getattr(registry, "add")
    add(FormMenuItem("form.mainWindow.addMenuBar", (_TITLE, "Add menu bar"), _add("menubar"), rank=0, offered=_lacking("menubar")))
    add(FormMenuItem("form.mainWindow.addToolbar", (_TITLE, "Add toolbar"), _add("toolbar"), rank=1, offered=_main))
    add(FormMenuItem("form.mainWindow.addStatusBar", (_TITLE, "Add status bar"), _add("statusbar"), rank=2, offered=_lacking("statusbar")))
