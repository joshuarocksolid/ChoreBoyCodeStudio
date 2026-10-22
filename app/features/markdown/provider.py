"""Markdown tab-content provider.

Matches the same paths ``wrap_tab_content_if_markdown`` used to wrap, and builds
the same ``MarkdownEditorPane``. ``content_source()`` is None, so dirty state
and save stay on the source editor's text.
"""

from __future__ import annotations

from typing import Callable, Mapping, Optional, Sequence

from app.editors.code_editor_widget import CodeEditorWidget
from app.editors.markdown_rendering import is_markdown_path
from app.editors.tab_content_source import TabContentSource
from app.features.markdown.markdown_editor_pane import MarkdownEditorPane, MarkdownPreviewMode
from app.intelligence.diagnostics_models import CodeDiagnostic
from app.shell.tab_content_providers import RestoreReason, TabMatchContext, TabSurfaceRequest
from app.shell.theme_tokens import ShellThemeTokens


class MarkdownTabSurface:
    """``TabSurface`` for one Markdown pane."""

    def __init__(
        self,
        pane: MarkdownEditorPane,
        panes_by_path: dict[str, MarkdownEditorPane],
        file_path: str,
    ) -> None:
        self._pane = pane
        self._panes_by_path = panes_by_path
        self._path = file_path
        self._released = False

    def widget(self) -> MarkdownEditorPane:
        return self._pane

    def content_source(self) -> Optional[TabContentSource]:
        return None

    def source_editor(self) -> Optional[CodeEditorWidget]:
        return self._pane.source_editor()

    def apply_theme(self, tokens: ShellThemeTokens) -> None:
        self._pane.apply_theme(tokens)

    def set_diagnostics(self, diagnostics: Sequence[CodeDiagnostic]) -> None:
        self._pane.source_editor().set_diagnostics(list(diagnostics))

    def reveal(self, line: int, detail: Optional[Mapping[str, str]]) -> bool:
        del detail
        if line < 1:
            return False
        self._pane.source_editor().go_to_line(line)
        return True

    def restore_text(self, text: str, reason: RestoreReason) -> None:
        editor = self._pane.source_editor()
        if reason == "external_reload":
            editor.blockSignals(True)
            editor.setPlainText(text)
            editor.blockSignals(False)
            return
        editor.replace_document_text(text)

    def close_blockers(self) -> tuple[str, ...]:
        return ()

    def file_path_changed(self, new_path: str) -> None:
        self._panes_by_path.pop(self._path, None)
        self._path = new_path
        self._pane.set_file_path(new_path)
        self._panes_by_path[new_path] = self._pane

    def focus_primary(self) -> None:
        editor = self._pane.source_editor()
        if editor.isVisible():
            editor.setFocus()
            return
        self._pane.preview_widget().setFocus()

    def release(self) -> None:
        if self._released:
            return
        self._released = True
        self._panes_by_path.pop(self._path, None)
        self._pane.deleteLater()


class MarkdownTabContentProvider:
    """Provider id ``markdown``. Registered from ``install_markdown``."""

    provider_id = "markdown"
    priority = 0

    def __init__(
        self,
        panes_by_path: dict[str, MarkdownEditorPane],
        *,
        on_mode_changed: Callable[[], None],
        markdown_supported: Optional[bool] = None,
    ) -> None:
        self._panes_by_path = panes_by_path
        self._on_mode_changed = on_mode_changed
        if markdown_supported is None:
            from app.editors.markdown_rendering import qt_markdown_supported

            markdown_supported = qt_markdown_supported()
        self._markdown_supported = markdown_supported

    def matches(self, file_path: str, context: TabMatchContext) -> bool:
        if context.forced_text or not self._markdown_supported:
            return False
        return is_markdown_path(file_path)

    def create_surface(self, request: TabSurfaceRequest) -> MarkdownTabSurface:
        editor = request.create_source_editor()
        pane = MarkdownEditorPane(
            editor,
            request.file_path,
            request.parent,
            local_link_callback=lambda linked_path: request.open_linked_file(linked_path),
            initial_mode=MarkdownPreviewMode.SPLIT,
        )
        pane.apply_theme(request.theme)
        pane.mode_changed.connect(lambda _mode: self._on_mode_changed())
        self._panes_by_path[request.file_path] = pane
        return MarkdownTabSurface(pane, self._panes_by_path, request.file_path)


__all__ = ["MarkdownTabContentProvider", "MarkdownTabSurface"]
