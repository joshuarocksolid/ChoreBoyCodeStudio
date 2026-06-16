"""Shared AD-018 stale-result policy for async editor intelligence delivery."""

from __future__ import annotations

from collections.abc import Callable

from app.editors.code_editor_widget import CodeEditorWidget


def is_stale_revision_gated_editor_request(
    *,
    file_path: str,
    editor_widget: CodeEditorWidget,
    requested_revision: int | None,
    editor_widget_for_path: Callable[[str], CodeEditorWidget | None],
    buffer_revision: Callable[[str], int | None],
    requested_generation: int | None = None,
    current_generation: int | None = None,
) -> bool:
    """Return True when an async editor intelligence result should be dropped."""
    active_widget = editor_widget_for_path(file_path)
    if active_widget is not editor_widget:
        return True
    if buffer_revision(file_path) != requested_revision:
        return True
    if requested_generation is not None and current_generation is not None:
        if current_generation != requested_generation:
            return True
    return False


def deliver_revision_gated_editor_result(
    *,
    file_path: str,
    editor_widget: CodeEditorWidget,
    requested_revision: int | None,
    editor_widget_for_path: Callable[[str], CodeEditorWidget | None],
    buffer_revision: Callable[[str], int | None],
    deliver: Callable[[], None],
    requested_generation: int | None = None,
    current_generation: int | None = None,
) -> None:
    """Invoke ``deliver`` only when the editor buffer and widget are still current."""
    if is_stale_revision_gated_editor_request(
        file_path=file_path,
        editor_widget=editor_widget,
        requested_revision=requested_revision,
        editor_widget_for_path=editor_widget_for_path,
        buffer_revision=buffer_revision,
        requested_generation=requested_generation,
        current_generation=current_generation,
    ):
        return
    deliver()
