"""Minimal form tab: the form name, a structure tree, and View XML.

The canvas arrives in M3. This surface still owns one command log per tab and
commits View XML through ``ReplaceDocument``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Mapping, Optional, Sequence

from app.qt.QtCore import Qt
from app.qt.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.editors.code_editor_widget import CodeEditorWidget
from app.features.form_builder.engine.commands.base import CommandRejected
from app.features.form_builder.engine.commands.catalog import ReplaceDocument
from app.features.form_builder.engine.commands.log import CommandLog, Subscription
from app.features.form_builder.integration.content_source import FormContentSource
from app.features.form_builder.integration.run_action import run_open_form
from app.features.form_builder.integration.structure import structure_rows
from app.intelligence.diagnostics_models import CodeDiagnostic
from app.shell.tab_content_providers import RestoreReason, TabSurfaceRequest
from app.shell.theme_tokens import ShellThemeTokens

XML_APPLY_HINT = "Edits here apply to the design when you switch back."
XML_DISCARD_LABEL = "Discard XML edits"
VIEW_XML_TOOLTIP = "View XML (Ctrl+Shift+V)"

_RESTORE_REASON = {
    "draft": "draft",
    "history": "history",
    "external_reload": "reload",
}


def plain_banner_error(error: str) -> str:
    """``Line 134: this form is not valid XML.`` from a reader sentence."""
    message = error.strip()
    line = ""
    marker = " (line "
    if message.endswith(")") and marker in message:
        message, _, tail = message.rpartition(marker)
        line = tail[:-1].strip()
    message = message.strip().rstrip(".")
    if message:
        message = message[0].lower() + message[1:]
    if line:
        return f"Line {line}: {message}."
    if not message:
        return error
    return message[0].upper() + message[1:] + "."


class FormSurface(QWidget):
    """``TabSurface`` for one ``.ui`` tab."""

    def __init__(
        self,
        request: TabSurfaceRequest,
        log: CommandLog,
        source: FormContentSource,
    ) -> None:
        super().__init__(request.parent)
        self._request = request
        self._log = log
        self._source = source
        self._path = request.file_path
        self._editor: Optional[CodeEditorWidget] = None
        self._released = False
        self._preview_request: Optional[str] = None
        self._preview_listener: Optional[Callable[[str], None]] = None
        self.setObjectName("formBuilder.surface")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(8)
        self._name = QLabel(self)
        self._name.setObjectName("formBuilder.name")
        self._name.setAccessibleName("Form name")
        header.addWidget(self._name, 1)
        self._toggle = QPushButton("View XML", self)
        self._toggle.setObjectName("formBuilder.viewXml")
        self._toggle.setToolTip(VIEW_XML_TOOLTIP)
        self._toggle.setCheckable(True)
        self._toggle.toggled.connect(self._on_toggled)
        header.addWidget(self._toggle, 0)
        layout.addLayout(header)

        # One notice box: the message, and Discard at its right on errors.
        self._banner_frame = QFrame(self)
        self._banner_frame.setObjectName("formBuilder.xmlBanner")
        banner_row = QHBoxLayout(self._banner_frame)
        banner_row.setContentsMargins(8, 4, 4, 4)
        self._banner = QLabel(self._banner_frame)
        self._banner.setObjectName("formBuilder.xmlBannerText")
        self._banner.setAccessibleName("XML notice")
        self._banner.setWordWrap(True)
        banner_row.addWidget(self._banner, 1)
        self._discard = QPushButton(XML_DISCARD_LABEL, self._banner_frame)
        self._discard.setObjectName("formBuilder.discardXml")
        self._discard.clicked.connect(self._discard_xml)
        self._discard.hide()
        banner_row.addWidget(self._discard, 0, Qt.AlignmentFlag.AlignTop)
        self._banner_frame.hide()
        layout.addWidget(self._banner_frame)

        self._stack = QStackedWidget(self)
        self._tree = QTreeWidget(self._stack)
        self._tree.setObjectName("formBuilder.structure")
        self._tree.setAccessibleName("Form structure")
        self._tree.setHeaderHidden(True)
        self._tree.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self._stack.addWidget(self._tree)
        layout.addWidget(self._stack, 1)

        self._tokens = request.theme
        self._banner_is_error = False
        self._changes: Subscription = log.subscribe(self._on_log, priority=1)
        self._rebuild_tree()
        self._refresh_name()
        self.apply_theme(request.theme)

    def widget(self) -> QWidget:
        return self

    def form_path(self) -> str:
        return self._path

    def current_text(self) -> str:
        return self._source.current_text()

    def mark_saved(self, saved_text: str) -> None:
        self._source.mark_saved(saved_text)

    def run_active_file(self, workflow: object) -> bool:
        return run_open_form(self, workflow)

    def request_preview(self, path: str) -> None:
        # The preview window is a later slice. F5 records the request here.
        self._preview_request = path
        listener = self._preview_listener
        if callable(listener):
            listener(path)

    def content_source(self) -> FormContentSource:
        return self._source

    def source_editor(self) -> Optional[CodeEditorWidget]:
        return self._editor

    def apply_theme(self, tokens: ShellThemeTokens) -> None:
        width = tokens.focus_border_width
        self.setStyleSheet(
            "QWidget#formBuilder\\.surface {"
            f" background: {tokens.panel_bg}; color: {tokens.text_primary}; }}"
            "QLabel#formBuilder\\.name {"
            f" color: {tokens.text_primary}; background: transparent; }}"
            "QTreeWidget#formBuilder\\.structure {"
            f" background: {tokens.editor_bg}; color: {tokens.text_primary};"
            f" border: 1px solid {tokens.border}; }}"
            "QTreeWidget#formBuilder\\.structure::item:selected {"
            f" background: {tokens.tree_selected_bg}; color: {tokens.text_primary}; }}"
            "QPushButton#formBuilder\\.viewXml {"
            f" color: {tokens.text_primary}; background: {tokens.input_bg};"
            f" border: 1px solid {tokens.border}; padding: 2px 8px; }}"
            "QPushButton#formBuilder\\.viewXml:checked {"
            f" background: {tokens.tree_selected_bg}; border: 1px solid {tokens.accent}; }}"
            "QPushButton#formBuilder\\.viewXml:focus {"
            f" border: {width}px solid {tokens.accent}; }}"
        )
        self._tokens = tokens
        self._paint_banner()
        editor = self._editor
        if editor is not None:
            editor.apply_theme(tokens)

    def set_diagnostics(self, diagnostics: Sequence[CodeDiagnostic]) -> None:
        del diagnostics

    def reveal(self, line: int, detail: Optional[Mapping[str, str]]) -> bool:
        del detail
        editor = self._editor
        if editor is None or line < 1:
            return False
        if not self._toggle.isChecked():
            self._toggle.setChecked(True)
        editor.go_to_line(line)
        return True

    def restore_text(self, text: str, reason: RestoreReason) -> None:
        try:
            self._log.execute(ReplaceDocument(text, reason=_RESTORE_REASON[reason]))
        except CommandRejected:
            return
        if self._source.mode == "xml":
            self._source.cancel_xml_mode()
            self._toggle.blockSignals(True)
            self._toggle.setChecked(False)
            self._toggle.blockSignals(False)
            self._hide_banner()
            self._stack.setCurrentWidget(self._tree)
        self._rebuild_tree()
        self._refresh_name()

    def close_blockers(self) -> tuple[str, ...]:
        return ()

    def file_path_changed(self, new_path: str) -> None:
        self._path = new_path
        self._refresh_name()

    def toggle_source_view(self) -> None:
        """Switch Design and View XML. The shell's Ctrl+Shift+V action calls this."""
        self._toggle.setChecked(not self._toggle.isChecked())

    def focus_primary(self) -> None:
        editor = self._editor
        if self._source.mode == "xml" and editor is not None:
            editor.setFocus()
            return
        self._tree.setFocus()

    def release(self) -> None:
        if self._released:
            return
        self._released = True
        self._changes.close()
        self._source.close()
        self.deleteLater()

    def undo(self) -> bool:
        """Undo the last command while Design is showing."""
        if self._source.mode != "visual":
            return False
        return self._log.undo()

    def _on_toggled(self, checked: bool) -> None:
        if checked:
            self._show_xml()
            return
        self._commit_xml()

    def _show_xml(self) -> None:
        editor = self._ensure_editor()
        if self._source.mode != "xml":
            editor.blockSignals(True)
            editor.setPlainText(self._source.current_text())
            shown = editor.toPlainText()
            editor.blockSignals(False)
            self._source.enter_xml_mode(shown)
            self._show_banner(XML_APPLY_HINT, error=False)
        self._stack.setCurrentWidget(editor)
        editor.setFocus()

    def _commit_xml(self) -> None:
        editor = self._editor
        if editor is not None and self._source.mode == "xml":
            self._source.xml_text_changed(editor.toPlainText())
        error = self._source.leave_xml_mode()
        if error is not None:
            self._toggle.blockSignals(True)
            self._toggle.setChecked(True)
            self._toggle.blockSignals(False)
            self._show_banner(plain_banner_error(error), error=True)
            return
        self._hide_banner()
        self._stack.setCurrentWidget(self._tree)
        self._rebuild_tree()
        self._refresh_name()
        self._tree.setFocus()

    def _discard_xml(self) -> None:
        self._source.cancel_xml_mode()
        self._toggle.blockSignals(True)
        self._toggle.setChecked(False)
        self._toggle.blockSignals(False)
        self._hide_banner()
        self._stack.setCurrentWidget(self._tree)
        self._rebuild_tree()
        self._refresh_name()
        self._tree.setFocus()

    def _show_banner(self, text: str, *, error: bool) -> None:
        self._banner.setText(text)
        self._banner_is_error = error
        self._paint_banner()
        self._discard.setVisible(error)
        self._banner_frame.show()

    def _hide_banner(self) -> None:
        self._banner_is_error = False
        self._banner_frame.hide()
        self._discard.hide()

    def _paint_banner(self) -> None:
        tokens = self._tokens
        if tokens is None:
            return
        width = tokens.focus_border_width
        if self._banner_is_error:
            color = tokens.diag_error_color or tokens.accent
            border = color
        else:
            color = tokens.text_primary
            border = tokens.border
        self._banner_frame.setStyleSheet(
            "QFrame#formBuilder\\.xmlBanner {"
            f" background: {tokens.editor_bg}; border: 1px solid {border}; }}"
            "QLabel#formBuilder\\.xmlBannerText {"
            f" color: {color}; background: transparent; border: none; }}"
        )
        self._discard.setStyleSheet(
            "QPushButton#formBuilder\\.discardXml {"
            f" color: {tokens.text_primary}; background: {tokens.input_bg};"
            f" border: 1px solid {tokens.border}; padding: 2px 8px; }}"
            "QPushButton#formBuilder\\.discardXml:focus {"
            f" border: {width}px solid {tokens.accent}; }}"
        )

    def _ensure_editor(self) -> CodeEditorWidget:
        editor = self._editor
        if editor is not None:
            return editor
        created = self._request.create_source_editor()
        self._editor = created
        created.textChanged.connect(self._on_xml_edited)
        self._stack.addWidget(created)
        return created

    def _on_xml_edited(self) -> None:
        editor = self._editor
        if editor is None:
            return
        self._source.xml_text_changed(editor.toPlainText())

    def _on_log(self, _change_set: object) -> None:
        if self._source.mode != "visual":
            return
        self._rebuild_tree()
        self._refresh_name()

    def _rebuild_tree(self) -> None:
        self._tree.clear()
        parents: dict[int, QTreeWidgetItem] = {}
        for depth, label in structure_rows(self._log.document):
            item = QTreeWidgetItem([label])
            parent = parents.get(depth - 1)
            if parent is None:
                self._tree.addTopLevelItem(item)
            else:
                parent.addChild(item)
            parents[depth] = item
            for deeper in [key for key in parents if key > depth]:
                del parents[deeper]
        self._tree.expandAll()

    def _refresh_name(self) -> None:
        root_name = self._log.document.root.object_name
        if root_name:
            self._name.setText(root_name)
            return
        stem = Path(self._path).stem
        self._name.setText(stem or "Form")


__all__ = ["XML_APPLY_HINT", "XML_DISCARD_LABEL", "VIEW_XML_TOOLTIP", "FormSurface"]
