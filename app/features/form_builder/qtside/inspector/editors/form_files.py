"""The form inspector's pictures-files group (UX-RES-006), added through the form-group slot.

It lists the ``.qrc`` files the form includes with an Open button and a "Stop
using in this form" item, and offers "Use another pictures file…" for the
project's other ``.qrc`` files. Each change is one undo step on the form.
"""

from __future__ import annotations

import os
from typing import Callable, List, Optional, Tuple

from app.features.form_builder.engine.project.picture_adopt import include_commands, included_qrcs, stop_using
from app.features.form_builder.engine.project.pictures import (
    load_pictures,
    picture_uses,
    project_qrc_files,
    resource_locations,
)
from app.features.form_builder.qtside.inspector.api import GroupBody, GroupHost, Registrar, Row
from app.features.form_builder.qtside.resources.opening import open_linked_file
from app.qt.QtCore import Qt
from app.qt.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

STOP_USING = "Stop using in this form"
USE_ANOTHER = "Use another pictures file…"
NONE_YET = "This form uses no pictures file."


def count_text(count: int) -> str:
    return "%d picture" % count if count == 1 else "%d pictures" % count


def summary_text(label: str, count: int) -> str:
    """"Pictures from forms/resources.qrc · 3 pictures" (UX-RES-006)."""
    return "Pictures from %s · %s" % (label, count_text(count))


def stop_prompt(uses: int) -> str:
    noun = "property uses" if uses == 1 else "properties use"
    return "%d %s pictures from this file. They will show as missing." % (uses, noun)


def _focus(name: str) -> object:
    return getattr(getattr(Qt, "FocusPolicy", Qt), name)


class FilesBody:
    """A column of file rows and the "Use another" button."""

    def __init__(self, host: GroupHost, parent: QWidget) -> None:
        self._host = host
        self._root = QWidget(parent)
        self._root.setObjectName("formBuilder.picturesFiles")
        self._layout = QVBoxLayout(self._root)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(4)
        self._rows: List[QWidget] = []
        self._empty = QLabel(NONE_YET, self._root)
        self._empty.setObjectName("formBuilder.picturesFilesNone")
        self._empty.setWordWrap(True)
        self._layout.addWidget(self._empty)
        self._another = QPushButton(USE_ANOTHER, self._root)
        self._another.setObjectName("formBuilder.picturesFilesUse")
        self._another.setAccessibleName("Pictures: use another pictures file")
        self._menu = QMenu(self._another)
        self._another.setMenu(self._menu)
        self._layout.addWidget(self._another)

    @property
    def widget(self) -> QWidget:
        return self._root

    def show(self, rows: Tuple[Row, ...]) -> None:
        del rows
        for row in self._rows:
            self._layout.removeWidget(row)
            row.deleteLater()
        self._rows = []
        document = self._host.document
        ui_path, root = self._where()
        locations = resource_locations(document)
        self._empty.setVisible(not locations)
        for index, location in enumerate(locations):
            row = self._file_row(document, ui_path, root, location)
            self._layout.insertWidget(index + 1, row)
            self._rows.append(row)
        self._fill_menu(document, ui_path, root)

    def _where(self) -> Tuple[str, str]:
        session = getattr(self._host, "session", None)
        scope = getattr(session, "scope", None)
        root = getattr(scope, "project_root", None) if getattr(scope, "generates", False) else None
        return str(getattr(session, "path", "") or ""), str(root or "")

    def _absolute(self, ui_path: str, location: str) -> str:
        if os.path.isabs(location):
            return location
        return os.path.normpath(os.path.join(os.path.dirname(ui_path), location)) if ui_path else location

    def _label(self, path: str, root: str, location: str) -> str:
        if root:
            try:
                relative = os.path.relpath(path, root).replace(os.sep, "/")
            except ValueError:
                return location
            if not relative.startswith(".."):
                return relative
        return location

    def _file_row(self, document: object, ui_path: str, root: str, location: str) -> QWidget:
        path = self._absolute(ui_path, location)
        label = self._label(path, root, location)
        index = load_pictures((path,), os.path.dirname(path))
        row = QWidget(self._root)
        row.setObjectName("formBuilder.picturesFile")
        box = QHBoxLayout(row)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(4)
        text = QLabel(summary_text(label, len(index.pictures)), row)
        text.setWordWrap(True)
        text.setObjectName("formBuilder.picturesFileText")
        box.addWidget(text, 1)
        open_button = QPushButton("Open", row)
        open_button.setObjectName("formBuilder.picturesFileOpen")
        open_button.setAccessibleName("Open %s" % label)
        open_button.clicked.connect(lambda _checked=False, target=path: open_linked_file(self._root, target))
        box.addWidget(open_button, 0)
        more = QToolButton(row)
        more.setObjectName("formBuilder.picturesFileMore")
        more.setText("⋯")
        more.setAccessibleName("More for %s" % label)
        more.setPopupMode(getattr(QToolButton, "ToolButtonPopupMode", QToolButton).InstantPopup)
        more.setFocusPolicy(_focus("StrongFocus"))  # type: ignore[arg-type]
        menu = QMenu(more)
        action = menu.addAction(STOP_USING)
        action.triggered.connect(
            lambda _checked=False: self.stop(location, label, tuple(p.resource_path for p in index.pictures))
        )
        more.setMenu(menu)
        box.addWidget(more, 0)
        return row

    def _fill_menu(self, document: object, ui_path: str, root: str) -> None:
        self._menu.clear()
        have = {os.path.normcase(os.path.abspath(p)) for p in included_qrcs(document, ui_path)}
        choices = [
            rel
            for rel in (project_qrc_files(root) if root else ())
            if os.path.normcase(os.path.abspath(os.path.join(root, *rel.split("/")))) not in have
        ]
        self._another.setVisible(bool(choices))
        for rel in choices:
            action = self._menu.addAction(rel)
            action.triggered.connect(lambda _checked=False, r=rel: self.use(r))

    def use(self, qrc_relative: str) -> Optional[str]:
        """"Use pictures file {path}": one step. Returns the refusal sentence, or None."""
        document = self._host.document
        ui_path, root = self._where()
        qrc = os.path.join(root, *qrc_relative.split("/"))
        commands = include_commands(document, ui_path, qrc)
        if not commands:
            return None
        return self._host.run("Use pictures file %s" % qrc_relative, commands)

    def stop(self, location: str, label: str, resource_paths: Tuple[str, ...], ask: Optional[Callable[[int], bool]] = None) -> Optional[str]:
        """"Stop using pictures file {path}": one step, after asking when properties use its pictures."""
        document = self._host.document
        used = sum(1 for use in picture_uses(document) if use.path in set(resource_paths))
        if used:
            confirm = ask or self._confirm
            if not confirm(used):
                return None
        return self._host.run("Stop using pictures file %s" % label, [stop_using(document, location)])

    def _confirm(self, used: int) -> bool:
        box = QMessageBox(self._root)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Stop using pictures file")
        box.setText(stop_prompt(used))
        go = box.addButton("Stop using", QMessageBox.ButtonRole.AcceptRole)
        cancel = box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(cancel)
        box.exec()
        return box.clickedButton() is go


def _factory(host: GroupHost, parent: QWidget) -> GroupBody:
    return FilesBody(host, parent)  # type: ignore[return-value]


def register_form_groups(registry: object) -> None:
    # After the built-in Window … Files sections, before M5.5b's Code group (order 150).
    registry.add("pictures", "Pictures", _factory, order=120)  # type: ignore[attr-defined]


def register(registrar: Registrar) -> None:
    del registrar
