"""Qt-free text and dirty state for a tab whose buffer is not a plain string.

``EditorTabState`` stores ``content_source``. When one is attached:

* ``current_content`` reads ``content_source.current_text()``.
* ``is_dirty`` reads ``content_source.is_dirty()``.
* ``update_content`` raises ``ValueError``.
* ``mark_saved`` passes the exact text written to ``content_source.mark_saved``.
"""

from __future__ import annotations

from typing import Callable, Protocol


class TabContentSource(Protocol):
    def current_text(self) -> str:
        """The text Save would write now. May serialize (memoized by revision)."""
        ...

    def is_dirty(self) -> bool:
        """O(1). Must not serialize."""
        ...

    def mark_saved(self, saved_text: str) -> None:
        """Called after the bytes are on disk."""
        ...

    def revision(self) -> int:
        """Increases whenever ``current_text()`` may have changed; O(1). The draft
        autosave compares it to skip unchanged drafts without serializing."""
        ...

    def subscribe_changed(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Called (no arguments) after any change of revision or dirty state, on the
        GUI thread. Replaces the text widget's ``textChanged`` for the shell's dirty
        indicator, save-action state and draft scheduling."""
        ...
