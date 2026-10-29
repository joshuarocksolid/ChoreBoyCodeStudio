"""The resource editor tab: Pictures | XML for one ``.qrc`` (UX-RES-004).

Pictures edits the layout held by ``QrcEditSource``; XML edits its text and
applies on switching back (an invalid file keeps the XML view, as a form does).
The shell saves the text; ``QrcEditSource.after_save`` then rewrites the
``*_rc.py`` of every form that includes the file.
"""

from __future__ import annotations

import os
from typing import Callable, List, Optional, Sequence, Tuple

from app.features.form_builder.engine.project.fs import OsFileSystem, ProjectOpError
from app.features.form_builder.engine.project.pictures import dialog_filter
from app.features.form_builder.engine.project.qrc_edit import QrcEditSource, new_path_label, uses_of
from app.features.form_builder.engine.project.qrc_write import (
    QrcLayout,
    add_pictures,
    add_prefix,
    normalize_prefix,
    remove_entries,
    resource_of,
    set_alias,
)
from app.features.form_builder.integration.chrome import chrome_for
from app.features.form_builder.qtside.resources.grid import QrcGrid
from app.features.form_builder.qtside.resources.opening import open_linked_file
from app.qt.QtCore import QEvent, Qt
from app.qt.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

XML_HINT = "Changes in XML apply when you switch back to Pictures."


def remove_prompt(forms: int, qrc_name: str) -> str:
    """UX-RES-004: asked when forms use the picture."""
    noun = "form uses" if forms == 1 else "forms use"
    return "%d %s this picture. Remove it from %s anyway?" % (forms, noun, qrc_name)


def used_sentence(use_path: str, count: int) -> str:
    noun = "place" if count == 1 else "places"
    return "%s is used in %d %s." % (use_path, count, noun)


class QrcSurface(QWidget):
    """The tab surface. Implements the shell's ``TabSurface`` protocol."""

    def __init__(self, request: object, source: QrcEditSource) -> None:
        super().__init__(getattr(request, "parent", None))
        self._request = request
        self._source = source
        self._tokens: object = None
        self._editor: Optional[QWidget] = None
        self._released = False
        self._loading = False
        self.setObjectName("formBuilder.qrcSurface")
        self.setAccessibleName("Pictures file")
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 8, 12, 8)
        root.setSpacing(8)

        head = QHBoxLayout()
        head.setSpacing(0)
        self._pictures = self._segment("Pictures", "formBuilder.qrcPictures")
        self._xml = self._segment("XML", "formBuilder.qrcXml")
        self._pictures.setChecked(True)
        self._pictures.clicked.connect(self._show_pictures)
        self._xml.clicked.connect(self._show_xml)
        head.addWidget(self._pictures)
        head.addWidget(self._xml)
        head.addSpacing(12)
        self._title = QLabel(new_path_label(source.path, source.project_root), self)
        self._title.setObjectName("formBuilder.qrcTitle")
        head.addWidget(self._title, 1)
        root.addLayout(head)

        self._bar = QWidget(self)
        bar = QHBoxLayout(self._bar)
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setSpacing(6)
        self._add = self._action("Add pictures…", "formBuilder.qrcAdd", self.add_pictures_dialog)
        self._prefix = self._action("New prefix…", "formBuilder.qrcPrefix", self.new_prefix_dialog)
        self._remove = self._action("Remove from this file", "formBuilder.qrcRemove", self.remove_selected)
        self._rename = self._action("Rename…", "formBuilder.qrcRename", self.rename_dialog)
        self._where = self._action("Show where it's used", "formBuilder.qrcWhere", self.show_uses)
        for button in (self._add, self._prefix, self._remove, self._rename, self._where):
            bar.addWidget(button)
        bar.addStretch(1)
        root.addWidget(self._bar)

        self._banner = QLabel(self)
        self._banner.setObjectName("formBuilder.qrcBanner")
        self._banner.setWordWrap(True)
        self._banner.hide()
        root.addWidget(self._banner)

        self._stack = QStackedWidget(self)
        self._grid = QrcGrid(self)
        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setWidget(self._grid)
        self._scroll.setSizePolicy(getattr(QSizePolicy, "Policy", QSizePolicy).Expanding, getattr(QSizePolicy, "Policy", QSizePolicy).Expanding)
        self._scroll.setFocusPolicy(getattr(getattr(Qt, "FocusPolicy", Qt), "NoFocus"))  # type: ignore[arg-type]
        self._stack.addWidget(self._scroll)
        root.addWidget(self._stack, 1)
        self._grid.on_rename = self.rename_dialog
        self._grid.on_remove = self.remove_selected
        self._grid.on_selection = self._sync_buttons
        self._grid.on_undo = self.undo
        self._grid.on_redo = self.redo

        self._unsubscribe = source.subscribe_changed(self._on_source)
        tokens = getattr(request, "theme", None)
        if tokens is not None:
            self.apply_theme(tokens)  # type: ignore[arg-type]
        if source.mode == "xml":
            self._show_xml()
            if source.error:
                self._say(source.error, error=True)
        self._refresh()

    # ----- TabSurface -----

    def widget(self) -> QWidget:
        return self

    def content_source(self) -> QrcEditSource:
        return self._source

    def source_editor(self) -> Optional[QWidget]:
        return self._editor

    def apply_theme(self, tokens: object) -> None:
        self._tokens = tokens
        chrome = chrome_for(tokens)  # type: ignore[arg-type]
        self._grid.set_tokens(chrome)
        self.setStyleSheet(
            "QWidget#formBuilder\\.qrcSurface { background: %s; color: %s; }"
            "QLabel { color: %s; }"
            "QPushButton[fbSegment=\"true\"] { background: %s; color: %s; border: 1px solid %s; padding: 3px 14px; }"
            "QPushButton[fbSegment=\"true\"]:checked { background: %s; color: %s; border: 1px solid %s; }"
            "QPushButton[fbSegment=\"true\"]:focus { border: %dpx solid %s; }"
            "QPushButton[fbBar=\"true\"] { background: %s; color: %s; border: 1px solid %s; padding: 3px 10px; }"
            "QPushButton[fbBar=\"true\"]:disabled { color: %s; }"
            "QPushButton[fbBar=\"true\"]:focus { border: %dpx solid %s; }"
            % (
                chrome.panel,
                chrome.text,
                chrome.text,
                chrome.input,
                chrome.text,
                chrome.border,
                chrome.selected,
                chrome.text,
                chrome.accent,
                chrome.focus_width,
                chrome.accent,
                chrome.input,
                chrome.text,
                chrome.border,
                chrome.faint,
                chrome.focus_width,
                chrome.accent,
            )
        )
        editor = self._editor
        applier = getattr(editor, "apply_theme", None)
        if callable(applier):
            applier(tokens)
        self._paint_banner()

    def set_diagnostics(self, diagnostics: Sequence[object]) -> None:
        del diagnostics

    def reveal(self, line: int, detail: object) -> bool:
        del line, detail
        return False

    def restore_text(self, text: str, reason: str) -> None:
        del reason
        self._source.restore_text(text)
        if self._source.mode == "xml":
            self._show_xml()
        self._refresh()

    def close_blockers(self) -> Tuple[str, ...]:
        return ()

    def file_path_changed(self, new_path: str) -> None:
        self._source.set_path(new_path)
        self._title.setText(new_path_label(new_path, self._source.project_root))

    def focus_primary(self) -> None:
        if self._source.mode == "xml" and self._editor is not None:
            self._editor.setFocus()
            return
        self._grid.setFocus()

    def release(self) -> None:
        if self._released:
            return
        self._released = True
        self._unsubscribe()
        self.deleteLater()

    # ----- state -----

    @property
    def source(self) -> QrcEditSource:
        return self._source

    @property
    def grid(self) -> QrcGrid:
        return self._grid

    @property
    def banner_text(self) -> str:
        return "" if self._banner.isHidden() else self._banner.text()

    def undo(self) -> bool:
        if self._source.mode == "xml":
            return False
        done = self._source.undo()
        return done

    def redo(self) -> bool:
        if self._source.mode == "xml":
            return False
        return self._source.redo()

    # ----- actions -----

    def _qrc_root(self) -> str:
        return self._source.project_root or os.path.dirname(self._source.path)

    def _selected_group(self) -> int:
        cell = self._grid.selected()
        return cell[0] if cell is not None else -1

    def add_pictures_dialog(self) -> None:
        names, _filter = QFileDialog.getOpenFileNames(self, "Add pictures", "", dialog_filter())
        if names:
            self.add_pictures(list(names))

    def add_pictures(self, sources: Sequence[str]) -> bool:
        """Copy ``sources`` next to the file and list them: one step "Add {n} pictures"."""
        if self._source.mode != "pictures":
            return False
        group = self._selected_group()
        prefix = self._source.layout.groups[group].prefix if 0 <= group < len(self._source.layout.groups) else "/"
        try:
            outcome = add_pictures(
                self._qrc_root(),
                self._source.path,
                sources,
                OsFileSystem(),
                prefix=prefix,
                layout=self._source.layout,
                write=False,
            )
        except ProjectOpError as exc:
            self._say(str(exc), error=True)
            return False
        count = len(outcome.file_names)
        label = "Add picture %s" % outcome.file_names[0] if count == 1 else "Add %d pictures" % count
        self._source.apply(label, outcome.layout)
        self._grid.select_resource(outcome.resource_paths[0])
        self._say("")
        return True

    def new_prefix_dialog(self) -> None:
        text, accepted = QInputDialog.getText(self, "New prefix", "Prefix, like /icons")
        if accepted and text.strip():
            self.new_prefix(text)

    def new_prefix(self, prefix: str) -> None:
        clean = normalize_prefix(prefix)
        self._source.apply("New prefix %s" % clean, add_prefix(self._source.layout, clean))

    def rename_dialog(self) -> None:
        name = self._grid.selected_name()
        if not name:
            return
        text, accepted = QInputDialog.getText(
            self, "Rename picture", "Name in code (leave empty for the file name)", text=name
        )
        if accepted:
            self.rename(text)

    def rename(self, alias: str) -> None:
        """Set the selected picture's alias (an empty name clears it): one step "Rename {file}"."""
        cell = self._grid.selected()
        if cell is None:
            return
        name = self._grid.selected_name()
        self._source.apply("Rename %s" % name, set_alias(self._source.layout, cell[0], cell[1], alias))
        self._grid.select(cell)

    def remove_selected(self, confirm: Optional[Callable[[int], bool]] = None) -> bool:
        """Remove the selected picture from this file (the file on disk stays)."""
        cell = self._grid.selected()
        if cell is None or self._source.mode != "pictures":
            return False
        resource = self._grid.selected_resource()
        name = self._grid.selected_name()
        forms = {path for path, _use in uses_of(self._source.project_root, self._source.path, (resource,))} if self._source.project_root else set()
        if forms:
            ask = confirm or self._confirm_remove
            if not ask(len(forms)):
                return False
        self._source.apply("Remove %s" % name, remove_entries(self._source.layout, cell[0], [cell[1]]))
        return True

    def _confirm_remove(self, forms: int) -> bool:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Remove picture")
        box.setText(remove_prompt(forms, os.path.basename(self._source.path)))
        go = box.addButton("Remove", QMessageBox.ButtonRole.AcceptRole)
        cancel = box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(cancel)
        box.exec()
        return box.clickedButton() is go

    def uses(self) -> List[Tuple[str, str]]:
        """``(form path, "name.property")`` for each place the selected picture is used."""
        resource = self._grid.selected_resource()
        if not resource or not self._source.project_root:
            return []
        found = []
        for path, use in uses_of(self._source.project_root, self._source.path, (resource,)):
            found.append((path, "%s.%s" % (use.object_name or "form", use.property_name)))
        return found

    def show_uses(self) -> None:
        places = self.uses()
        dialog = QDialog(self)
        dialog.setWindowTitle("Where it's used")
        box = QVBoxLayout(dialog)
        resource = self._grid.selected_resource()
        box.addWidget(QLabel(used_sentence(resource, len(places)) if places else "Nothing in this project uses %s." % resource))
        listing = QListWidget(dialog)
        listing.setObjectName("formBuilder.qrcUses")
        root = self._source.project_root
        for path, place in places:
            listing.addItem("%s · %s" % (new_path_label(path, root), place))
        paths = [path for path, _place in places]
        listing.itemActivated.connect(lambda _item: open_linked_file(self, paths[listing.currentRow()]))
        listing.itemDoubleClicked.connect(lambda _item: open_linked_file(self, paths[listing.currentRow()]))
        box.addWidget(listing)
        close = QPushButton("Close", dialog)
        close.clicked.connect(dialog.accept)
        box.addWidget(close)
        dialog.exec()

    # ----- views -----

    def _segment(self, text: str, name: str) -> QPushButton:
        button = QPushButton(text, self)
        button.setObjectName(name)
        button.setCheckable(True)
        button.setProperty("fbSegment", "true")
        button.setAccessibleName("%s view" % text)
        return button

    def _action(self, text: str, name: str, slot: Callable[[], object]) -> QPushButton:
        button = QPushButton(text, self)
        button.setObjectName(name)
        button.setProperty("fbBar", "true")
        button.clicked.connect(lambda _checked=False: slot())
        return button

    def _ensure_editor(self) -> QWidget:
        if self._editor is not None:
            return self._editor
        created = self._request.create_source_editor()  # type: ignore[attr-defined]
        self._editor = created
        created.textChanged.connect(self._on_xml_edited)
        self._stack.addWidget(created)
        if self._tokens is not None:
            created.apply_theme(self._tokens)
        return created

    def _show_pictures(self) -> None:
        editor = self._editor
        if self._source.mode == "xml":
            if editor is not None:
                self._source.xml_changed(editor.toPlainText())  # type: ignore[attr-defined]
            error = self._source.leave_xml()
            if error is not None:
                self._pictures.setChecked(False)
                self._xml.setChecked(True)
                self._say(error, error=True)
                return
        self._xml.setChecked(False)
        self._pictures.setChecked(True)
        self._say("")
        self._bar.show()
        self._stack.setCurrentWidget(self._scroll)
        self._refresh()
        self._grid.setFocus()

    def _show_xml(self) -> None:
        editor = self._ensure_editor()
        text = self._source.enter_xml() if self._source.mode != "xml" else self._source.current_text()
        self._loading = True
        editor.setPlainText(text)  # type: ignore[attr-defined]
        self._loading = False
        self._pictures.setChecked(False)
        self._xml.setChecked(True)
        self._bar.hide()
        self._stack.setCurrentWidget(editor)
        if not self._source.error:
            self._say(XML_HINT, error=False)
        editor.setFocus()

    def _on_xml_edited(self) -> None:
        editor = self._editor
        if editor is None or self._loading:
            return
        self._source.xml_changed(editor.toPlainText())  # type: ignore[attr-defined]

    def _on_source(self) -> None:
        if self._released:
            return
        self._refresh()

    def _refresh(self) -> None:
        source = self._source
        if source.mode == "pictures":
            self._grid.set_layout(source.layout, source.path, source.project_root)
        self._sync_buttons()

    def _sync_buttons(self) -> None:
        has = self._grid.selected() is not None and self._source.mode == "pictures"
        self._remove.setEnabled(has)
        self._rename.setEnabled(has)
        self._where.setEnabled(has)
        notice = self._source.notice
        if notice:
            self._say(notice, error=True)

    def _say(self, text: str, *, error: bool = False) -> None:
        self._banner.setText(text)
        self._banner_error = error
        self._banner.setVisible(bool(text))
        self._paint_banner()

    def _paint_banner(self) -> None:
        tokens = self._tokens
        if tokens is None:
            return
        color = getattr(tokens, "diag_error_color", "") if getattr(self, "_banner_error", False) else getattr(tokens, "text_primary", "")
        self._banner.setStyleSheet("QLabel { color: %s; }" % color)


__all__ = ["QrcSurface", "remove_prompt", "used_sentence"]
