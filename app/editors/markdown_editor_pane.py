"""Composite source/preview pane for Markdown editor tabs."""

from __future__ import annotations

from typing import Any

from PySide2.QtCore import Signal, QTimer, Qt
from PySide2.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.editors.code_editor_widget import CodeEditorWidget
from app.editors.markdown_preview_widget import ExternalLinkCallback, LocalLinkCallback, MarkdownPreviewWidget
from app.editors.markdown_rendering import MAX_LIVE_MARKDOWN_PREVIEW_CHARS
from app.shell.theme_tokens import ShellThemeTokens


class MarkdownPreviewMode:
    """String constants for Markdown tab display modes."""

    SOURCE = "source"
    PREVIEW = "preview"
    SPLIT = "split"


class MarkdownEditorPane(QWidget):
    """Markdown tab content with source, rendered preview, and split modes."""

    mode_changed: Any = Signal(str)

    def __init__(
        self,
        source_editor: CodeEditorWidget,
        file_path: str,
        parent: QWidget | None = None,
        *,
        local_link_callback: LocalLinkCallback | None = None,
        external_link_callback: ExternalLinkCallback | None = None,
        initial_mode: str = MarkdownPreviewMode.PREVIEW,
        render_debounce_ms: int = 200,
        live_preview_threshold_chars: int = MAX_LIVE_MARKDOWN_PREVIEW_CHARS,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("shell.markdownEditorPane")
        self._source_editor = source_editor
        self._file_path = file_path
        self._mode = MarkdownPreviewMode.SOURCE
        self._live_preview_threshold_chars = live_preview_threshold_chars
        self._syncing_scroll = False

        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.setInterval(render_debounce_ms)
        self._render_timer.timeout.connect(self.render_preview)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        toolbar = QWidget(self)
        toolbar.setObjectName("shell.markdownEditorPane.toolbar")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(8, 4, 8, 4)
        toolbar_layout.setSpacing(4)

        title = QLabel("Markdown", toolbar)
        title.setObjectName("shell.markdownEditorPane.title")
        toolbar_layout.addWidget(title)
        toolbar_layout.addStretch()

        self._source_button = self._make_mode_button("Markdown", MarkdownPreviewMode.SOURCE, toolbar)
        self._preview_button = self._make_mode_button("Preview", MarkdownPreviewMode.PREVIEW, toolbar)
        self._split_button = self._make_mode_button("Split", MarkdownPreviewMode.SPLIT, toolbar)
        toolbar_layout.addWidget(self._source_button)
        toolbar_layout.addWidget(self._preview_button)
        toolbar_layout.addWidget(self._split_button)

        self._refresh_button = QToolButton(toolbar)
        self._refresh_button.setObjectName("shell.markdownEditorPane.refreshButton")
        self._refresh_button.setText("Refresh")
        self._refresh_button.setToolTip("Refresh Markdown preview")
        self._refresh_button.setAutoRaise(True)
        self._refresh_button.clicked.connect(lambda: self.render_preview(force=True))
        toolbar_layout.addWidget(self._refresh_button)

        self._status_label = QLabel("", toolbar)
        self._status_label.setObjectName("shell.markdownEditorPane.status")
        toolbar_layout.addWidget(self._status_label)
        layout.addWidget(toolbar, 0)

        self._splitter = QSplitter(Qt.Horizontal, self)
        self._splitter.setObjectName("shell.markdownEditorPane.splitter")
        self._splitter.setChildrenCollapsible(False)

        self._preview = MarkdownPreviewWidget(
            self._splitter,
            local_link_callback=local_link_callback,
            external_link_callback=external_link_callback,
        )
        self._preview.set_file_path(file_path)

        self._splitter.addWidget(source_editor)
        self._splitter.addWidget(self._preview)
        self._splitter.setStretchFactor(0, 1)
        self._splitter.setStretchFactor(1, 1)
        layout.addWidget(self._splitter, 1)

        self._source_editor.textChanged.connect(self.schedule_preview_render)
        self._source_editor.verticalScrollBar().valueChanged.connect(self._sync_preview_scroll_from_source)

        self.set_mode(initial_mode)
        self.schedule_preview_render()

    def source_editor(self) -> CodeEditorWidget:
        """Return the canonical editable source widget."""
        return self._source_editor

    def preview_widget(self) -> MarkdownPreviewWidget:
        """Return the rendered preview widget."""
        return self._preview

    def mode(self) -> str:
        """Return the active display mode."""
        return self._mode

    def set_file_path(self, file_path: str) -> None:
        """Update path-dependent preview behavior after a move or rename."""
        self._file_path = file_path
        self._preview.set_file_path(file_path)

    def apply_theme(self, tokens: ShellThemeTokens) -> None:
        """Apply theme tokens to both source and preview widgets."""
        self._source_editor.apply_theme(tokens)
        self._preview.apply_theme(tokens)

    def set_mode(self, mode: str) -> None:
        """Switch between source, preview, and split modes."""
        if mode not in {MarkdownPreviewMode.SOURCE, MarkdownPreviewMode.PREVIEW, MarkdownPreviewMode.SPLIT}:
            mode = MarkdownPreviewMode.PREVIEW
        self._mode = mode
        self._source_editor.setVisible(mode in {MarkdownPreviewMode.SOURCE, MarkdownPreviewMode.SPLIT})
        self._preview.setVisible(mode in {MarkdownPreviewMode.PREVIEW, MarkdownPreviewMode.SPLIT})
        self._source_button.setChecked(mode == MarkdownPreviewMode.SOURCE)
        self._preview_button.setChecked(mode == MarkdownPreviewMode.PREVIEW)
        self._split_button.setChecked(mode == MarkdownPreviewMode.SPLIT)
        if mode in {MarkdownPreviewMode.PREVIEW, MarkdownPreviewMode.SPLIT}:
            self.schedule_preview_render()
        self.mode_changed.emit(mode)

    def toggle_preview(self) -> None:
        """Toggle source-only and preview-only display."""
        if self._mode == MarkdownPreviewMode.PREVIEW:
            self.set_mode(MarkdownPreviewMode.SOURCE)
        else:
            self.set_mode(MarkdownPreviewMode.PREVIEW)

    def schedule_preview_render(self) -> None:
        """Debounce live preview rendering from source changes."""
        if self._mode not in {MarkdownPreviewMode.PREVIEW, MarkdownPreviewMode.SPLIT}:
            return
        self._render_timer.start()

    def render_preview(self, *, force: bool = False) -> None:
        """Render the current source buffer into the preview."""
        text = self._source_editor.toPlainText()
        if not force and len(text) > self._live_preview_threshold_chars:
            self._preview.show_preview_paused_message(len(text), self._live_preview_threshold_chars)
            self._status_label.setText("Preview paused")
            return
        self._preview.render_markdown(text)
        self._status_label.setText("Preview current")

    def _make_mode_button(self, label: str, mode: str, parent: QWidget) -> QToolButton:
        button = QToolButton(parent)
        button.setObjectName("shell.markdownEditorPane.modeButton")
        button.setText(label)
        button.setCheckable(True)
        button.setAutoRaise(True)
        button.clicked.connect(lambda _checked=False, selected_mode=mode: self.set_mode(selected_mode))
        return button

    def _sync_preview_scroll_from_source(self, _value: int) -> None:
        if self._mode != MarkdownPreviewMode.SPLIT or self._syncing_scroll:
            return
        source_bar = self._source_editor.verticalScrollBar()
        preview_bar = self._preview.verticalScrollBar()
        source_max = source_bar.maximum()
        preview_max = preview_bar.maximum()
        if source_max <= 0 or preview_max <= 0:
            return
        self._syncing_scroll = True
        try:
            preview_bar.setValue(round((source_bar.value() / source_max) * preview_max))
        finally:
            self._syncing_scroll = False
