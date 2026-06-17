"""Shell–editor completion wiring contracts."""

from __future__ import annotations

from typing import Protocol


class CompletionRequester(Protocol):
    """Async completion request callback wired from shell into the editor.

    The editor invokes this callable with a buffer snapshot and trigger metadata.
    Shell adapters (for example ``editor_tab_factory``) bind ``file_path`` and
    ``editor_widget`` before delegating to ``EditorCompletionWorkflow``.
    """

    def __call__(
        self,
        source_text: str,
        cursor_position: int,
        manual_trigger: bool,
        request_generation: int,
        trigger_kind: str,
        trigger_character: str,
    ) -> None:
        """Request asynchronous completion for the current editor buffer."""
        ...
