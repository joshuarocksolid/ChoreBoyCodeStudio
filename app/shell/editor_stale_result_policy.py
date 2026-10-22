"""Shared AD-018 stale-result policy for async editor intelligence delivery."""

from __future__ import annotations

from collections.abc import Callable

from app.editors.code_editor_widget import CodeEditorWidget


def capture_buffer_revision(
    file_path: str,
    *,
    buffer_id_for_path: Callable[[str], str | None],
    buffer_revision_for_buffer_id: Callable[[str], int | None],
) -> tuple[str | None, int | None]:
    """Pin a request to the buffer currently at ``file_path`` and its revision."""
    buffer_id = buffer_id_for_path(file_path)
    if buffer_id is None:
        return None, None
    return buffer_id, buffer_revision_for_buffer_id(buffer_id)


def is_stale_revision_gated_editor_request(
    *,
    buffer_id: str | None,
    editor_widget: CodeEditorWidget,
    requested_revision: int | None,
    editor_widget_for_buffer_id: Callable[[str], CodeEditorWidget | None],
    buffer_revision_for_buffer_id: Callable[[str], int | None],
    requested_generation: int | None = None,
    current_generation: int | None = None,
) -> bool:
    """Return True when an async editor intelligence result should be dropped."""
    if buffer_id is None:
        return True
    if editor_widget_for_buffer_id(buffer_id) is not editor_widget:
        return True
    if buffer_revision_for_buffer_id(buffer_id) != requested_revision:
        return True
    if requested_generation is not None and current_generation is not None:
        if current_generation != requested_generation:
            return True
    return False


def deliver_revision_gated_editor_result(
    *,
    buffer_id: str | None,
    editor_widget: CodeEditorWidget,
    requested_revision: int | None,
    editor_widget_for_buffer_id: Callable[[str], CodeEditorWidget | None],
    buffer_revision_for_buffer_id: Callable[[str], int | None],
    deliver: Callable[[], None],
    requested_generation: int | None = None,
    current_generation: int | None = None,
) -> None:
    """Invoke ``deliver`` only when the editor buffer and widget are still current."""
    if is_stale_revision_gated_editor_request(
        buffer_id=buffer_id,
        editor_widget=editor_widget,
        requested_revision=requested_revision,
        editor_widget_for_buffer_id=editor_widget_for_buffer_id,
        buffer_revision_for_buffer_id=buffer_revision_for_buffer_id,
        requested_generation=requested_generation,
        current_generation=current_generation,
    ):
        return
    deliver()
