"""Themed Markdown preview widget for editor tabs."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide2.QtCore import QUrl
from PySide2.QtGui import QDesktopServices
from PySide2.QtWidgets import QTextBrowser, QWidget

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

    def set_file_path(self, file_path: str) -> None:
        """Set the Markdown source path used for relative resources."""
        self._file_path = str(Path(file_path).expanduser().resolve())
        base_dir = Path(self._file_path).parent
        self.setSearchPaths([str(base_dir)])
        self.document().setBaseUrl(QUrl.fromLocalFile(f"{base_dir}/"))

    def apply_theme(self, tokens: ShellThemeTokens) -> None:
        """Apply shell theme colors to the preview document."""
        self._tokens = tokens
        self.setStyleSheet(
            f"""
            QTextBrowser#shell\\.markdownPreview\\.browser {{
                background: {tokens.editor_bg};
                color: {tokens.text_primary};
                border: none;
                padding: 18px 24px;
                selection-background-color: {tokens.tree_selected_bg};
            }}
            """
        )
        self.document().setDefaultStyleSheet(
            f"""
            body {{
                color: {tokens.text_primary};
                background-color: {tokens.editor_bg};
                font-family: sans-serif;
                font-size: 13px;
                line-height: 1.55;
            }}
            h1, h2, h3, h4, h5, h6 {{
                color: {tokens.text_primary};
                font-weight: 700;
            }}
            h1 {{
                border-bottom: 1px solid {tokens.border};
                padding-bottom: 6px;
            }}
            a {{
                color: {tokens.accent};
            }}
            code, pre {{
                background-color: {tokens.badge_bg};
                color: {tokens.text_primary};
            }}
            blockquote {{
                color: {tokens.text_muted};
                border-left: 3px solid {tokens.border};
                margin-left: 0;
                padding-left: 12px;
            }}
            table, th, td {{
                border: 1px solid {tokens.border};
                border-collapse: collapse;
                padding: 4px 8px;
            }}
            """
        )

    def render_markdown(self, markdown_text: str) -> None:
        """Render Markdown text, preferring raw-HTML-disabled features."""
        features = safe_markdown_features()
        if features is not None:
            try:
                self.setMarkdown(markdown_text, features)
                return
            except TypeError:
                pass
        self.setMarkdown(markdown_text)

    def show_preview_paused_message(self, character_count: int, threshold: int) -> None:
        """Show a friendly large-document guardrail message."""
        tokens = self._tokens
        if tokens is None:
            self.setPlainText(
                "Markdown preview paused for this large file.\n\n"
                f"Characters: {character_count:,}\n"
                f"Live preview limit: {threshold:,}\n\n"
                "Use Refresh Preview to render it manually."
            )
            return
        self.setHtml(
            f"""
            <div style="font-family:sans-serif;color:{tokens.text_primary};
                        background:{tokens.editor_bg};padding:20px;">
              <h2>Markdown preview paused</h2>
              <p>This file is large, so live preview is paused to keep the editor responsive.</p>
              <p><b>Characters:</b> {character_count:,}<br/>
                 <b>Live preview limit:</b> {threshold:,}</p>
              <p>Use <b>Refresh Preview</b> to render it manually.</p>
            </div>
            """
        )

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
        tokens = self._tokens
        if tokens is None:
            self.setToolTip(f"Linked file was not found: {target_path}")
            return
        self.setToolTip(f"Linked file was not found: {target_path}")
