"""PROPOSED for platform.editors by M2.0 (CONTRACTS.md section 11.2).

A Qt-free source of a tab's text and dirty state, for tabs whose buffer is not a
plain string (the form builder's document + command log). ``EditorTabState``
gains ``content_source: Optional[TabContentSource] = None``:

* ``current_content`` becomes a property: ``content_source.current_text()`` when
  a source is attached, else the stored string. Every existing reader of
  ``current_content`` (save, local-history snapshot, draft autosave, View XML
  fallback) therefore triggers lazy serialization only when it actually reads.
* ``is_dirty`` returns ``content_source.is_dirty()`` when attached.
* ``update_content(text)`` on a sourced tab is a programming error (ValueError);
  provider surfaces never route editor ``textChanged`` into it.
* ``mark_saved`` calls ``content_source.mark_saved(saved_text)`` with the exact
  text written.
* Sourced tabs skip every save transform (trim trailing whitespace, final
  newline, format on save). Save writes ``current_text()`` as UTF-8, no BOM.
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
