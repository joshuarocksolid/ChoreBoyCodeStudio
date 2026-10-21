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
_buffer_warmup_timers: dict[int, QTimer] = {}


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


def schedule_open_buffer_warmup(window: Any, *, debounce_ms: int = 150) -> None:
    """Queue a low-priority Jedi warm of the active Python buffer.

    Cursor moves restart the timer so a buffer is warmed once the caret rests,
    which is the gap between opening a file and the first Ctrl+Space.
    """

    if not _window_shown:
        return
    timer = _buffer_warmup_timers.get(id(window))
    if timer is None:
        timer = QTimer(window)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: _start_buffer_warmup(window))
        _buffer_warmup_timers[id(window)] = timer
    timer.start(max(0, debounce_ms))


def _start_buffer_warmup(window: Any) -> None:
    if not _window_shown:
        return
    workflow = getattr(window, "_editor_tab_workflow", None)
    session = getattr(window, "_semantic_session", None)
    if workflow is None or session is None:
        return
    editor = workflow.active_editor_widget()
    if editor is None:
        return
    path = editor._active_file_path
    if not path or not str(path).endswith(".py"):
        return
    language = editor.active_language_key()
    if language not in (None, "python"):
        return
    project = getattr(window, "_loaded_project", None)
    project_root = None if project is None else getattr(project, "project_root", None)
    source_text = editor.toPlainText()
    cursor_position = editor.textCursor().position()
    coordinator = getattr(window, "_runtime_introspection_coordinator", None)

    def prefetch(target: str) -> None:
        if coordinator is None:
            return
        from app.intelligence.runtime_introspection import RuntimeIntrospectionQuery

        query = RuntimeIntrospectionQuery(target_path=target, member_prefix="")
        if coordinator.cached_items(query) is not None:
            return
        coordinator.fetch_and_cache_from_runner(query)

    session.request_buffer_warmup(
        project_root=None if project_root is None else str(project_root),
        current_file_path=str(path),
        source_text=source_text,
        cursor_position=cursor_position,
        prefetch_target=prefetch if coordinator is not None else None,
    )


def _warm_open_editor_popups(window: Any) -> None:
    widgets = getattr(window, "_editor_widgets_by_path", {})
    for editor in widgets.values():
        popup = getattr(editor, "_completion_popup", None)
        warm = getattr(popup, "warm_surface", None)
        if callable(warm):
            warm()
