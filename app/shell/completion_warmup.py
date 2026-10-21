"""Schedule completion warmup after the window is on screen.

The callback only queues work. Jedi and the first member listing run on the
semantic worker, so the UI thread does not hold the GIL for them and
time-to-window stays the moment ``showMaximized`` returns.
"""

from __future__ import annotations

from typing import Any

from app.qt.QtCore import QTimer
from app.qt.qt_compat import QT_API

from app.intelligence.runtime_members import RuntimeUnavailable

_REPL_WARM_TARGET = QT_API + ".QtCore.QObject"
_window_shown = False


def note_window_shown() -> None:
    """Record that ``showMaximized`` has returned."""

    global _window_shown
    _window_shown = True


def window_is_shown() -> bool:
    return _window_shown


def schedule_completion_warmup(window: Any, *, refresh_repl: bool = False) -> None:
    """Queue warmup on the next event-loop turn, after the window is visible."""

    if not _window_shown:
        return
    QTimer.singleShot(0, lambda: _start_completion_warmup(window, refresh_repl=refresh_repl))


def _start_completion_warmup(window: Any, *, refresh_repl: bool) -> None:
    project = getattr(window, "_loaded_project", None)
    project_root = None if project is None else getattr(project, "project_root", None)
    window._semantic_session.request_completion_warmup(
        project_root=project_root,
        repl_warm=lambda: _warm_repl_listing(window),
        refresh_repl=refresh_repl,
    )
    _warm_open_editor_popups(window)


def _warm_repl_listing(window: Any) -> bool:
    listing = window._repl_manager.list_members(target_path=_REPL_WARM_TARGET)
    return not isinstance(listing, RuntimeUnavailable)


def _warm_open_editor_popups(window: Any) -> None:
    widgets = getattr(window, "_editor_widgets_by_path", {})
    for editor in widgets.values():
        popup = getattr(editor, "_completion_popup", None)
        warm = getattr(popup, "warm_surface", None)
        if callable(warm):
            warm()
