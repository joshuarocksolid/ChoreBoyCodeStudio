"""Themed Markdown preview widget for editor tabs."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide2.QtCore import QUrl
from PySide2.QtGui import QDesktopServices
from PySide2.QtWidgets import QTextBrowser, QWidget

from app.editors.markdown_preview_enhancements import enhance_preview_document
from app.editors.markdown_preview_styles import (
    build_preview_document_stylesheet,
    build_preview_paused_html,
    build_preview_widget_stylesheet,
)
from app.editors.markdown_rendering import (
    LINK_KIND_ANCHOR,
    LINK_KIND_EXTERNAL,
    LINK_KIND_LOCAL_FILE,
    LINK_KIND_MISSING,
    resolve_markdown_link,
    safe_markdown_features,
)
from app.shell.theme_tokens import ShellThemeTokens


LocalLinkCallback = Callable[[str], object]
ExternalLinkCallback = Callable[[QUrl], object]


class MarkdownPreviewWidget(QTextBrowser):
    """Render Markdown text using Qt's native rich-text document support."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        local_link_callback: LocalLinkCallback | None = None,
        external_link_callback: ExternalLinkCallback | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("shell.markdownPreview.browser")
        self.setReadOnly(True)
        self.setOpenLinks(False)
        self.setOpenExternalLinks(False)
        self.anchorClicked.connect(self._handle_anchor_clicked)
        self._file_path: str | None = None
        self._local_link_callback = local_link_callback
        self._external_link_callback = external_link_callback
        self._tokens: ShellThemeTokens | None = None
        self._last_markdown_text: str | None = None
        self._paused_character_count: int | None = None
        self._paused_threshold: int | None = None

    def set_file_path(self, file_path: str) -> None:
        """Set the Markdown source path used for relative resources."""
        self._file_path = str(Path(file_path).expanduser().resolve())
        base_dir = Path(self._file_path).parent
        self.setSearchPaths([str(base_dir)])
        self.document().setBaseUrl(QUrl.fromLocalFile(f"{base_dir}/"))

    def apply_theme(self, tokens: ShellThemeTokens) -> None:
        """Apply shell theme colors to the preview document."""
        self._tokens = tokens
        self.setStyleSheet(build_preview_widget_stylesheet(tokens))
        self.document().setDefaultStyleSheet(build_preview_document_stylesheet(tokens))
        if self._paused_character_count is not None and self._paused_threshold is not None:
            self.show_preview_paused_message(self._paused_character_count, self._paused_threshold)
        elif self._last_markdown_text is not None:
            self.render_markdown(self._last_markdown_text)

    def render_markdown(self, markdown_text: str) -> None:
        """Render Markdown text, preferring raw-HTML-disabled features."""
        self._paused_character_count = None
        self._paused_threshold = None
        self._last_markdown_text = markdown_text
        features = safe_markdown_features()
        if features is not None:
            try:
                self.setMarkdown(markdown_text, features)
            except TypeError:
                self.setMarkdown(markdown_text)
        else:
            self.setMarkdown(markdown_text)
        if self._tokens is not None:
            enhance_preview_document(
                self.document(),
                tokens=self._tokens,
                base_file_path=self._file_path,
            )

    def show_preview_paused_message(self, character_count: int, threshold: int) -> None:
        """Show a friendly large-document guardrail message."""
        self._last_markdown_text = None
        self._paused_character_count = character_count
        self._paused_threshold = threshold
        tokens = self._tokens
        if tokens is None:
            self.setPlainText(
                "Markdown preview paused for this large file.\n\n"
                f"Characters: {character_count:,}\n"
                f"Live preview limit: {threshold:,}\n\n"
                "Use Refresh to render it manually."
            )
            return
        self.setHtml(build_preview_paused_html(tokens, character_count=character_count, threshold=threshold))

    def _handle_anchor_clicked(self, url: QUrl) -> None:
        href = url.toString()
        if self._file_path is None:
            return
        resolved = resolve_markdown_link(self._file_path, href)
        if resolved.kind == LINK_KIND_ANCHOR and resolved.anchor:
            self.scrollToAnchor(resolved.anchor)
            return
        if resolved.kind == LINK_KIND_LOCAL_FILE and resolved.target_path:
            if self._local_link_callback is not None:
                self._local_link_callback(resolved.target_path)
            return
        if resolved.kind == LINK_KIND_EXTERNAL:
            if self._external_link_callback is not None:
                self._external_link_callback(url)
            else:
                QDesktopServices.openUrl(url)
            return
        if resolved.kind == LINK_KIND_MISSING and resolved.target_path:
            self._show_missing_link_message(resolved.target_path)

    def _show_missing_link_message(self, target_path: str) -> None:
        self.setToolTip(f"Linked file was not found: {target_path}")
