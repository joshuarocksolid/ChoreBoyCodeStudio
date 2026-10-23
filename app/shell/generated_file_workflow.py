"""The read-only lock on generated files (UX-GEN-001). The only writer of ``EditorTabState.generated``."""

from __future__ import annotations

from dataclasses import replace
from typing import Callable, Optional

from app.editors.editor_tab import EditorTabState
from app.editors.generated_banner import GeneratedLock, read_generated_banner


class GeneratedFileWorkflow:
    def __init__(
        self,
        *,
        tab_for_path: Callable[[str], Optional[EditorTabState]],
        refresh_tab_presentation: Callable[[str], None],
    ) -> None:
        self._tab_for_path = tab_for_path
        self._refresh_tab_presentation = refresh_tab_presentation

    def lock_from_text(self, tab: EditorTabState, text: str) -> None:
        """Lock ``tab`` when ``text`` carries a generated banner. Drops an earlier Edit anyway."""
        banner = read_generated_banner(text)
        tab.generated = None if banner is None else GeneratedLock(banner=banner)

    def edit_anyway(self, file_path: str) -> None:
        tab = self._tab_for_path(file_path)
        if tab is None or tab.generated is None or tab.generated.edit_anyway:
            return
        tab.generated = replace(tab.generated, edit_anyway=True)
        self._refresh_tab_presentation(file_path)


__all__ = ["GeneratedFileWorkflow"]
