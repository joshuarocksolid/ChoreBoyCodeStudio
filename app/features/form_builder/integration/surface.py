"""Minimal form tab: the form name, a structure tree, and View XML.

The canvas arrives in M3. This surface still owns one command log per tab and
commits View XML through ``ReplaceDocument``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Optional, Sequence

from app.qt.QtWidgets import (
    QAbstractItemView,
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
from app.features.form_builder.integration.content_source import FormContentSource, plain_read_error
from app.features.form_builder.integration.structure import structure_rows
from app.intelligence.diagnostics_models import CodeDiagnostic
from app.shell.tab_content_providers import RestoreReason, TabSurfaceRequest
from app.shell.theme_tokens import ShellThemeTokens

XML_APPLY_HINT = "Edits here apply to the design when you switch back."

_RESTORE_REASON = {
    "draft": "draft",
    "history": "history",
    "external_reload": "reload",
}


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
        self.setObjectName("formBuilder.surface")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(8)
        self._name = QLabel(self)
        self._name.setObjectName("formBuilder.name")
        header.addWidget(self._name, 1)
        self._toggle = QPushButton("View XML", self)
        self._toggle.setObjectName("formBuilder.viewXml")
        self._toggle.setCheckable(True)
        self._toggle.toggled.connect(self._on_toggled)
        header.addWidget(self._toggle, 0)
        layout.addLayout(header)

        self._banner = QLabel(self)
        self._banner.setObjectName("formBuilder.xmlBanner")
        self._banner.setWordWrap(True)
        self._banner.hide()
        layout.addWidget(self._banner)

        self._stack = QStackedWidget(self)
        self._tree = QTreeWidget(self._stack)
        self._tree.setObjectName("formBuilder.structure")
        self._tree.setHeaderHidden(True)
        self._tree.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self._stack.addWidget(self._tree)
        layout.addWidget(self._stack, 1)

        self._changes: Subscription = log.subscribe(self._on_log, priority=1)
        self._rebuild_tree()
        self._refresh_name()
        self.apply_theme(request.theme)

    def widget(self) -> QWidget:
        return self

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
            "QLabel#formBuilder\\.xmlBanner {"
            f" color: {tokens.text_primary}; background: {tokens.editor_bg};"
            f" border: 1px solid {tokens.border}; padding: 4px 8px; }}"
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
            self._banner.hide()
            self._stack.setCurrentWidget(self._tree)
        self._rebuild_tree()
        self._refresh_name()

    def close_blockers(self) -> tuple[str, ...]:
        return ()

    def file_path_changed(self, new_path: str) -> None:
        self._path = new_path
        self._refresh_name()

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
            self._banner.setText(XML_APPLY_HINT)
            self._banner.show()
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
            self._banner.setText(error)
            self._banner.show()
            return
        self._banner.hide()
        self._stack.setCurrentWidget(self._tree)
        self._rebuild_tree()
        self._refresh_name()
        self._tree.setFocus()

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


__all__ = ["XML_APPLY_HINT", "FormSurface"]
