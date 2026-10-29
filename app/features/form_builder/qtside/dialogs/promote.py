"""The "Use my own class" popover (UX-CUST-001 .. 006).

Level 2, 360 px, anchored beside the widget like the item editor. It reads the
project's registry through an ``OwnClassPort`` (the integration layer binds that
to ``cbcs/project.json``), checks the module path with the ``ast`` resolver and
never imports project code. [Use {Class}] runs one ``UseOwnClass`` step and
saves the class in the registry at once, which is not on the form's undo stack.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Callable, Optional, Protocol, Sequence, Tuple

from app.features.form_builder.engine.commands.base import CommandRejected
from app.features.form_builder.engine.commands.catalog_ext.promote import UseOwnClass
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.project import custom_widgets as cw
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.nodes import CustomWidgetNode, WidgetNode
from app.features.form_builder.qtside.inspector.editors._editor_kit import warning_color
from app.features.form_builder.qtside.inspector.words import class_words
from app.features.form_builder.qtside.items.place import seat_beside
from app.features.form_builder.qtside.theme.chrome import (
    FormChrome,
    apply_level2_shadow,
    control_qss,
    default_chrome,
    field_qss,
    popover_style,
)
from app.qt.QtCore import QEvent, QPoint, QRect, QSize, Qt, QTimer
from app.qt.QtGui import QColor, QGuiApplication, QPalette
from app.qt.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

OBJECT_NAME = "formBuilder.ownClassPopover"
CHECK_DELAY_MS = 150
SAVED_NOTE = "Saved for this project's other forms."
_WIDTH = 360
_OK = ((26, 127, 55), (63, 185, 80), (0, 80, 0), (127, 203, 102))


class OwnClassPort(Protocol):
    """What the popover needs from the project (bound by the integration layer)."""

    @property
    def project_root(self) -> Optional[str]: ...

    def entries(self) -> Tuple[cw.RegistryEntry, ...]: ...

    def upsert(self, entry: cw.RegistryEntry) -> bool: ...

    def remove(self, class_name: str) -> bool: ...


def widget_base(session: FormSession, node_id: NodeId) -> str:
    """The Qt class a widget is, or the base its own class declares."""
    node = session.document.get(node_id)
    if not isinstance(node, WidgetNode):
        return ""
    declared = session.document.custom_widget(node.class_name)
    if isinstance(declared, CustomWidgetNode) and declared.extends:
        return declared.extends
    return node.class_name


def open_popover(
    session: FormSession,
    ids: Sequence[NodeId],
    port: OwnClassPort,
    parent: Optional[QWidget],
    *,
    beside: Optional[QRect] = None,
    chrome: Optional[FormChrome] = None,
    on_done: Optional[Callable[[str], None]] = None,
) -> Optional["OwnClassPopover"]:
    if not ids or widget_base(session, ids[0]) == "":
        return None
    popover = OwnClassPopover(session, tuple(ids), port, parent, chrome=chrome, on_done=on_done)
    popover.seat(beside)
    popover.show()
    popover.raise_()
    popover.activateWindow()
    popover.focus_first()
    return popover


class OwnClassPopover(QFrame):
    def __init__(
        self,
        session: FormSession,
        ids: Tuple[NodeId, ...],
        port: OwnClassPort,
        parent: Optional[QWidget] = None,
        *,
        chrome: Optional[FormChrome] = None,
        on_done: Optional[Callable[[str], None]] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName(OBJECT_NAME)
        self._session = session
        self._ids = ids
        self._port = port
        self._chrome = chrome or default_chrome()
        self._on_done = on_done
        self._base = widget_base(session, ids[0])
        self._base_friendly = class_words(self._base).friendly
        self._editing: Optional[cw.RegistryEntry] = None
        self._closed = False
        self._state = cw.BAD_CLASS
        tool = getattr(Qt, "Tool", None)
        frameless = getattr(Qt, "FramelessWindowHint", None)
        if tool is not None and frameless is not None:
            self.setWindowFlags(tool | frameless)
        self.setAccessibleName("Use my own class")
        self.setFixedWidth(_WIDTH)
        self._paint_chrome()

        column = QVBoxLayout(self)
        column.setContentsMargins(10, 10, 10, 10)
        column.setSpacing(6)
        self._title = QLabel("Use my own class", self)
        self._title.setObjectName("formBuilder.ownClassTitle")
        font = self._title.font()
        font.setBold(True)
        self._title.setFont(font)
        column.addWidget(self._title)

        self._list_box = QWidget(self)
        self._list_layout = QVBoxLayout(self._list_box)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(2)
        self._overline = QLabel("CLASSES IN THIS PROJECT", self._list_box)
        self._overline.setObjectName("formBuilder.ownClassOverline")
        self._overline.setProperty("note", "true")
        small = self._overline.font()
        small.setPointSizeF(max(7.0, small.pointSizeF() * 0.85))
        self._overline.setFont(small)
        self._list_layout.addWidget(self._overline)
        self._rows = QVBoxLayout()
        self._rows.setContentsMargins(0, 0, 0, 0)
        self._rows.setSpacing(2)
        self._list_layout.addLayout(self._rows)
        column.addWidget(self._list_box)

        self._class_label = QLabel("Class", self)
        self._class = QLineEdit(self)
        self._class.setObjectName("formBuilder.ownClassName")
        self._class.setPlaceholderText("TillDisplay")
        self._class.setAccessibleName("Class")
        self._class_label.setBuddy(self._class)
        column.addWidget(self._class_label)
        column.addWidget(self._class)
        self._module_label = QLabel("From Python module", self)
        self._module = QLineEdit(self)
        self._module.setObjectName("formBuilder.ownClassModule")
        self._module.setPlaceholderText("widgets.till_display")
        self._module.setAccessibleName("From Python module")
        self._module_label.setBuddy(self._module)
        column.addWidget(self._module_label)
        column.addWidget(self._module)
        self._based_label = QLabel("Based on", self)
        self._based = QLabel(self._base_friendly, self)
        self._based.setObjectName("formBuilder.ownClassBase")
        self._based.setAccessibleName("Based on")
        based_row = QHBoxLayout()
        based_row.addWidget(self._based_label)
        based_row.addWidget(self._based, 1)
        column.addLayout(based_row)
        self._holds = QCheckBox("Holds other widgets", self)
        self._holds.setObjectName("formBuilder.ownClassHolds")
        self._holds.setVisible(cw.is_container_base(self._base))
        column.addWidget(self._holds)

        self._description_label = QLabel("Description", self)
        self._description = QLineEdit(self)
        self._description.setObjectName("formBuilder.ownClassDescription")
        self._size_label = QLabel("Size on the canvas", self)
        self._width = QSpinBox(self)
        self._width.setObjectName("formBuilder.ownClassWidth")
        self._height = QSpinBox(self)
        self._height.setObjectName("formBuilder.ownClassHeight")
        for box in (self._width, self._height):
            box.setRange(0, 20000)
            box.setSuffix(" px")
        size_row = QHBoxLayout()
        size_row.addWidget(self._size_label)
        size_row.addWidget(self._width)
        size_row.addWidget(self._height)
        self._edit_box = QWidget(self)
        edit_layout = QVBoxLayout(self._edit_box)
        edit_layout.setContentsMargins(0, 0, 0, 0)
        edit_layout.addWidget(self._description_label)
        edit_layout.addWidget(self._description)
        edit_layout.addLayout(size_row)
        self._edit_box.hide()
        column.addWidget(self._edit_box)

        self._check = QLabel("", self)
        self._check.setObjectName("formBuilder.ownClassCheck")
        self._check.setWordWrap(True)
        self._check.setAccessibleName("Check")
        column.addWidget(self._check)
        self._saved = QLabel(SAVED_NOTE, self)
        self._saved.setObjectName("formBuilder.ownClassSaved")
        self._saved.setProperty("note", "true")
        column.addWidget(self._saved)

        footer = QHBoxLayout()
        footer.addStretch(1)
        self._use = QPushButton("Use", self)
        self._use.setObjectName("formBuilder.ownClassUse")
        self._use.setDefault(True)
        self._use.clicked.connect(self.accept)
        self._cancel = QPushButton("Cancel", self)
        self._cancel.setObjectName("formBuilder.ownClassCancel")
        self._cancel.setAutoDefault(True)
        self._cancel.clicked.connect(self.cancel)
        footer.addWidget(self._use)
        footer.addWidget(self._cancel)
        column.addLayout(footer)

        self.setTabOrder(self._class, self._module)
        self.setTabOrder(self._module, self._holds)
        self.setTabOrder(self._holds, self._use)
        self.setTabOrder(self._use, self._cancel)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(CHECK_DELAY_MS)
        self._timer.timeout.connect(self.update_check)
        self._class.textChanged.connect(self._typed)
        self._module.textChanged.connect(self._typed)
        self._class.returnPressed.connect(self._module.setFocus)
        self._module.returnPressed.connect(self._enter_in_module)
        self._description.returnPressed.connect(self.accept)

        self._fill_from_widget()
        self._refill_rows()
        self.update_check()

    # ----------------------------------------------------------------- look

    def _paint_chrome(self) -> None:
        chrome = self._chrome
        palette = self.palette()
        palette.setColor(QPalette.Window, QColor(chrome.popup or chrome.panel))
        palette.setColor(QPalette.WindowText, QColor(chrome.text))
        self.setPalette(palette)
        self.setAutoFillBackground(True)
        styled = getattr(Qt, "WA_StyledBackground", None)
        if styled is not None:
            self.setAttribute(styled, True)
        name = "QFrame#%s" % OBJECT_NAME.replace(".", "\\.")
        self.setStyleSheet(
            popover_style(OBJECT_NAME, chrome) + field_qss(chrome, name) + control_qss(chrome, name)
        )
        apply_level2_shadow(self, chrome)

    def restyle(self, chrome: FormChrome) -> None:
        self._chrome = chrome
        self._paint_chrome()
        self.update_check()

    def _ink(self, state: str) -> str:
        chrome = self._chrome
        if state in (cw.BAD_MODULE, cw.BAD_CLASS):
            return chrome.error
        if state in (cw.OTHER_BASE, cw.NO_CLASS, cw.NO_FILE):
            return warning_color(chrome)
        if state == cw.FOUND:
            index = (2 if chrome.is_high_contrast else 0) + (1 if chrome.is_dark else 0)
            return QColor(*_OK[index]).name()
        return chrome.faint or chrome.muted

    # ----------------------------------------------------------------- seat and focus

    def seat(self, beside: Optional[QRect]) -> None:
        self.adjustSize()
        screen = _screen()
        size = self.size()
        if beside is not None:
            self.move(seat_beside(beside, size, screen or beside))
        elif screen is not None:
            self.move(screen.center() - QPoint(size.width() // 2, size.height() // 2))

    def focus_first(self) -> None:
        self._class.setFocus()
        self._class.selectAll()

    # ----------------------------------------------------------------- state

    @property
    def state(self) -> str:
        return self._state

    @property
    def check_text(self) -> str:
        return self._check.text()

    def set_fields(self, class_name: str, module: str) -> None:
        self._class.setText(class_name)
        self._module.setText(module)
        self.update_check()

    def use_enabled(self) -> bool:
        return self._use.isEnabled()

    def _fill_from_widget(self) -> None:
        declared = self._session.document.get(self._ids[0])
        if not isinstance(declared, WidgetNode):
            return
        custom = self._session.document.custom_widget(declared.class_name)
        if isinstance(custom, CustomWidgetNode):
            entry = cw.entry_from_declaration(custom)
            if entry is not None:
                self._class.setText(entry.class_name)
                self._module.setText(entry.module)
                self._holds.setChecked(entry.container)

    def _refill_rows(self) -> None:
        while self._rows.count():
            item = self._rows.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.deleteLater()
        found = (
            self._port.entries()
            if self._editing is not None
            else tuple(
                entry for entry in self._port.entries() if _compatible(entry, self._base)
            )
        )
        self._list_box.setVisible(bool(found) and self._editing is None)
        for entry in found:
            self._rows.addWidget(self._row_for(entry))
        first_time = not self._port.entries() and bool(self._port.project_root)
        self._saved.setVisible(first_time and self._editing is None)

    def _row_for(self, entry: cw.RegistryEntry) -> QWidget:
        row = QWidget(self)
        row.setObjectName("formBuilder.ownClassRow.%s" % entry.class_name)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        pick = QPushButton(entry.label, row)
        pick.setObjectName("formBuilder.ownClassPick")
        pick.setAccessibleName(entry.label)
        pick.setFlat(True)
        pick.setStyleSheet("text-align: left;")
        pick.clicked.connect(lambda _checked=False, item=entry: self._pick(item))
        layout.addWidget(pick, 1)
        more = QToolButton(row)
        more.setObjectName("formBuilder.ownClassMore")
        more.setText("⋯")
        more.setAccessibleName("More for %s" % entry.class_name)
        menu = QMenu(more)
        menu.addAction("Edit…").triggered.connect(lambda _checked=False, item=entry: self._edit(item))
        menu.addAction("Remove from this list").triggered.connect(
            lambda _checked=False, item=entry: self._forget(item)
        )
        more.setMenu(menu)
        more.setPopupMode(getattr(QToolButton, "ToolButtonPopupMode", QToolButton).InstantPopup)
        layout.addWidget(more, 0)
        return row

    def _pick(self, entry: cw.RegistryEntry) -> None:
        self._class.setText(entry.class_name)
        self._module.setText(entry.module)
        self._holds.setChecked(entry.container)
        self.update_check()
        self._class.setFocus()

    def _forget(self, entry: cw.RegistryEntry) -> None:
        self._port.remove(entry.class_name)
        self._refill_rows()

    def _edit(self, entry: cw.RegistryEntry) -> None:
        self._editing = entry
        self._title.setText("Edit %s" % entry.class_name)
        self._class.setText(entry.class_name)
        self._class.setReadOnly(True)
        self._module.setText(entry.module)
        self._holds.setVisible(cw.is_container_base(entry.extends))
        self._holds.setChecked(entry.container)
        self._based.setText(class_words(entry.extends).friendly)
        self._description.setText(entry.description)
        width, height = entry.size or (0, 0)
        self._width.setValue(width)
        self._height.setValue(height)
        self._edit_box.show()
        self._list_box.hide()
        self._saved.hide()
        self._use.setText("Save")
        self._module.setFocus()
        self.update_check()

    def _typed(self, _text: str = "") -> None:
        self._timer.start()

    def _enter_in_module(self) -> None:
        self.update_check()
        if self._use.isEnabled():
            self.accept()

    def update_check(self) -> None:
        """The check line, never importing (UX-CUST-003)."""
        class_name = self._class.text().strip()
        module = self._module.text().strip()
        expected = self._editing.extends if self._editing is not None else self._base
        check = cw.check_module(self._port.project_root, module, class_name, expected)
        self._state = check.state
        sentence = cw.check_sentence(
            check, class_name, module, class_words(expected).friendly, lambda name: class_words(name).friendly
        )
        self._check.setText(sentence)
        self._check.setStyleSheet("color: %s;" % self._ink(check.state))
        self._use.setText("Save" if self._editing is not None else ("Use %s" % class_name if class_name else "Use"))
        self._use.setEnabled(bool(class_name) and bool(module) and check.state not in cw.BLOCKING)

    # ----------------------------------------------------------------- finish

    def accept(self) -> None:
        if self._closed:
            return
        self.update_check()
        if not self._use.isEnabled():
            return
        class_name = self._class.text().strip()
        module = self._module.text().strip()
        if self._editing is not None:
            self._save_edit(class_name, module)
            return
        known = {entry.class_name: entry for entry in self._port.entries()}.get(class_name)
        container = self._holds.isChecked() and cw.is_container_base(self._base)
        entry = known if known is not None else cw.RegistryEntry(class_name, module, self._base)
        entry = replace(entry, module=module, extends=self._base, container=container)
        names = tuple(self._name_of(node_id) for node_id in self._ids)
        try:
            self._session.log.execute(
                UseOwnClass(self._ids, class_name, module, self._base, container, entry.size, names)
            )
        except CommandRejected as exc:
            self._check.setText(str(exc))
            self._check.setStyleSheet("color: %s;" % self._chrome.error)
            return
        self._port.upsert(entry)
        self._finish("Used %s." % class_name)

    def _save_edit(self, class_name: str, module: str) -> None:
        assert self._editing is not None
        size = (self._width.value(), self._height.value())
        entry = replace(
            self._editing,
            module=module,
            container=self._holds.isChecked() and cw.is_container_base(self._editing.extends),
            description=self._description.text().strip(),
            size=size if size[0] > 0 and size[1] > 0 else None,
        )
        self._port.upsert(entry)
        self._editing = None
        self._finish("Saved %s." % class_name)

    def cancel(self) -> None:
        if not self._closed:
            self._finish("")

    def _name_of(self, node_id: NodeId) -> str:
        node = self._session.document.get(node_id)
        return node.object_name if isinstance(node, WidgetNode) else ""

    def _finish(self, sentence: str) -> None:
        self._closed = True
        self._timer.stop()
        self.close()
        self.deleteLater()
        if sentence and self._on_done is not None:
            self._on_done(sentence)

    def keyPressEvent(self, event: QEvent) -> None:  # type: ignore[override]
        if event.key() == getattr(Qt, "Key_Escape", None):  # type: ignore[attr-defined]
            event.accept()  # type: ignore[attr-defined]
            self.cancel()
            return
        super().keyPressEvent(event)  # type: ignore[arg-type]

    def sizeHint(self) -> QSize:  # noqa: N802
        hint = super().sizeHint()
        return QSize(_WIDTH, hint.height())


def _compatible(entry: cw.RegistryEntry, base: str) -> bool:
    return entry.extends == base or base in cw.qt_chain(entry.extends)


def _screen() -> Optional[QRect]:
    app = QGuiApplication.instance()
    if app is None:
        return None
    screen = app.primaryScreen()
    return None if screen is None else screen.availableGeometry()


__all__ = ["OBJECT_NAME", "OwnClassPopover", "OwnClassPort", "SAVED_NOTE", "open_popover", "widget_base"]
