"""The Preview window when Run behavior is on: the form, Window values, and What ran.

Colours come from ``FormChrome``. This module does not import the shell.
"""

from __future__ import annotations

import time
from typing import Dict, Optional, Sequence

from app.features.form_builder.qtside.preview.try_log import TryLine, source_label, source_of
from app.features.form_builder.qtside.preview.try_plan import value_to_wire, wire_to_value
from app.features.form_builder.qtside.theme.chrome import (
    FALLBACK_ACCENT,
    FALLBACK_BORDER,
    FALLBACK_FAINT,
    FALLBACK_MUTED,
    FALLBACK_PANEL,
    FALLBACK_TEXT,
    FormChrome,
    chrome_from_values,
)
from app.qt.QtCore import Qt, Signal
from app.qt.QtGui import QColor, QPalette
from app.qt.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

_SOURCE_CAP = 240


def fallback_chrome() -> FormChrome:
    """Light chrome for the preview child, which has no shell theme."""
    return chrome_from_values(
        window=FALLBACK_PANEL,
        panel=FALLBACK_PANEL,
        text=FALLBACK_TEXT,
        muted=FALLBACK_MUTED,
        faint=FALLBACK_FAINT,
        border=FALLBACK_BORDER,
        accent=FALLBACK_ACCENT,
        row_hover=FALLBACK_BORDER,
        input_bg=FALLBACK_PANEL,
        error=FALLBACK_ACCENT,
        focus_width=1,
    )


class WhatRan(QWidget):
    """Time, sentence, and source. Clear and Copy sit above the list."""

    activated = Signal(object)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("preview.whatRan")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        title = QLabel("What ran", self)
        title.setObjectName("preview.whatRan.title")
        layout.addWidget(title)
        buttons = QHBoxLayout()
        self._clear = QPushButton("Clear", self)
        self._clear.setObjectName("preview.whatRan.clear")
        self._copy = QPushButton("Copy", self)
        self._copy.setObjectName("preview.whatRan.copy")
        buttons.addWidget(self._clear)
        buttons.addWidget(self._copy)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        self._list = QTreeWidget(self)
        self._list.setObjectName("preview.whatRan.list")
        self._list.setColumnCount(3)
        self._list.setHeaderLabels(["Time", "What ran", "Source"])
        self._list.setRootIsDecorated(True)
        self._list.setTextElideMode(_elide_right())
        header = self._list.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, _header_mode("ResizeToContents"))
        header.setSectionResizeMode(1, _header_mode("Stretch"))
        header.setSectionResizeMode(2, _header_mode("ResizeToContents"))
        self._list.itemClicked.connect(self._clicked)
        layout.addWidget(self._list, 1)
        self._clear.clicked.connect(self.clear)
        self._copy.clicked.connect(self.copy)
        self._lines: list[TryLine] = []

    def add(self, lines: Sequence[TryLine], ts_ms: int) -> None:
        stamp = time.strftime("%H:%M:%S", time.localtime(ts_ms / 1000.0))
        for line in lines:
            item = QTreeWidgetItem([stamp, line.sentence, _shown_source(line)])
            item.setData(0, _user_role(), line)
            item.setToolTip(1, line.sentence)
            item.setToolTip(2, _source_tip(line))
            for ref in line.details:
                child = QTreeWidgetItem(["", source_label(ref), ""])
                child.setToolTip(1, ref)
                child.setToolTip(2, ref)
                child.setData(
                    0,
                    _user_role(),
                    TryLine(source_label(ref), ref, source_of(ref), "rule"),
                )
                item.addChild(child)
            self._list.addTopLevelItem(item)
            self._lines.append(line)
        self._fit_columns()
        if lines:
            self._list.scrollToItem(self._list.topLevelItem(self._list.topLevelItemCount() - 1))

    def clear(self) -> None:
        self._list.clear()
        self._lines = []

    def copy(self) -> None:
        from app.qt.QtWidgets import QApplication

        board = QApplication.clipboard()
        if board is not None:
            board.setText(self.copy_text())

    def copy_text(self) -> str:
        rows = []
        for index in range(self._list.topLevelItemCount()):
            item = self._list.topLevelItem(index)
            line = item.data(0, _user_role())
            if isinstance(line, TryLine):
                source = ", ".join(line.details) if line.details else line.ref
                rows.append("%s\t%s\t%s" % (item.text(0), line.sentence, source))
            else:
                rows.append("\t".join(item.text(column) for column in range(3)))
        return "\n".join(rows)

    def _fit_columns(self) -> None:
        header = self._list.header()
        self._list.resizeColumnToContents(0)
        self._list.resizeColumnToContents(2)
        if self._list.columnWidth(2) > _SOURCE_CAP:
            header.setSectionResizeMode(2, _header_mode("Interactive"))
            self._list.setColumnWidth(2, _SOURCE_CAP)

    def apply_chrome(self, chrome: FormChrome) -> None:
        width = int(chrome.focus_width or 1)
        _paint(self, chrome.panel, chrome.text)
        self.setStyleSheet(
            """
            background: %s; color: %s;
            QLabel { color: %s; background: transparent; }
            QTreeWidget { background: %s; color: %s; border: 1px solid %s; }
            QTreeWidget:focus { border: %dpx solid %s; }
            QHeaderView::section { background: %s; color: %s; }
            QPushButton { background: %s; color: %s; border: 1px solid %s; }
            QPushButton:focus { border: %dpx solid %s; }
            """
            % (
                chrome.panel,
                chrome.text,
                chrome.text,
                chrome.input or chrome.panel,
                chrome.text,
                chrome.border,
                width,
                chrome.accent,
                chrome.panel,
                chrome.text,
                chrome.panel,
                chrome.text,
                chrome.border,
                width,
                chrome.accent,
            )
        )

    def _clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        line = item.data(0, _user_role())
        if isinstance(line, TryLine):
            self.activated.emit(line)


class WindowValues(QWidget):
    """One box per ``window.m()``. ``changed`` carries the method and the wire text."""

    changed = Signal(str, str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("preview.windowValues")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(8, 4, 8, 8)
        self._title = QLabel("Window values", self)
        self._title.setObjectName("preview.windowValues.title")
        self._layout.addWidget(self._title)
        self._rows: Dict[str, QWidget] = {}
        self._annotations: Dict[str, str] = {}

    def set_methods(
        self,
        specs: Sequence[tuple],
        values: Dict[str, object],
    ) -> None:
        while self._layout.count() > 1:
            item = self._layout.takeAt(1)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._rows = {}
        self._annotations = {}
        self.setVisible(bool(specs))
        for name, annotation in specs:
            self._annotations[name] = annotation or ""
            row = QWidget(self)
            row.setObjectName("preview.windowValueRow.%s" % name)
            across = QHBoxLayout(row)
            across.setContentsMargins(0, 0, 0, 0)
            label = QLabel("%s()" % name, row)
            label.setObjectName("preview.windowValueLabel.%s" % name)
            across.addWidget(label)
            editor = _editor(row, name, annotation or "", values.get(name))
            editor.setObjectName("preview.windowValue.%s" % name)
            across.addWidget(editor, 1)
            self._rows[name] = editor
            self._layout.addWidget(row)
            _connect(editor, name, annotation or "", self.changed.emit)

    def apply_chrome(self, chrome: FormChrome) -> None:
        width = int(chrome.focus_width or 1)
        _paint(self, chrome.panel, chrome.text)
        self.setStyleSheet(
            """
            background: %s; color: %s;
            QLabel { color: %s; background: %s; }
            QLineEdit, QComboBox { background: %s; color: %s; border: 1px solid %s; }
            QLineEdit:focus, QComboBox:focus { border: %dpx solid %s; }
            """
            % (
                chrome.panel,
                chrome.text,
                chrome.text,
                chrome.panel,
                chrome.input or chrome.panel,
                chrome.text,
                chrome.border,
                width,
                chrome.accent,
            )
        )


class TryChrome(QWidget):
    """Toolbar, the form, Window values, and What ran."""

    run_toggled = Signal(bool)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.previewShell")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self._toolbar = QWidget(self)
        self._toolbar.setObjectName("preview.toolbar")
        bar = QHBoxLayout(self._toolbar)
        bar.setContentsMargins(8, 4, 8, 4)
        self.run_behavior = QToolButton(self._toolbar)
        self.run_behavior.setObjectName("preview.runBehavior")
        self.run_behavior.setText("Run behavior")
        self.run_behavior.setAccessibleName("Run behavior")
        self.run_behavior.setCheckable(True)
        self.run_behavior.setChecked(True)
        self.run_behavior.setAutoRaise(True)
        self.run_behavior.setToolButtonStyle(getattr(getattr(Qt, "ToolButtonStyle", Qt), "ToolButtonTextOnly"))
        self.run_behavior.toggled.connect(self.run_toggled.emit)
        bar.addWidget(self.run_behavior)
        bar.addStretch(1)
        root.addWidget(self._toolbar)
        self._splitter = QSplitter(self)
        self._splitter.setObjectName("preview.splitter")
        self._splitter.setOrientation(Qt.Horizontal)
        left = QWidget(self._splitter)
        left.setObjectName("preview.column")
        self._column = left
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self._form_parent = QWidget(left)
        self._form_parent.setObjectName("preview.form")
        self._form_layout = QVBoxLayout(self._form_parent)
        self._form_layout.setContentsMargins(0, 0, 0, 0)
        self.values = WindowValues(left)
        left_layout.addWidget(self._form_parent, 1)
        left_layout.addWidget(self.values, 0)
        self.what_ran = WhatRan(self._splitter)
        self._splitter.addWidget(left)
        self._splitter.addWidget(self.what_ran)
        self._splitter.setStretchFactor(0, 3)
        self._splitter.setStretchFactor(1, 2)
        root.addWidget(self._splitter, 1)
        from app.qt.QtWidgets import QApplication

        app = QApplication.instance()
        self._native = QPalette(app.palette() if app is not None else self.palette())
        self.apply_chrome(fallback_chrome())

    def form_parent(self) -> QWidget:
        return self._form_parent

    def adopt(self, form: QWidget) -> None:
        form.setParent(self._form_parent)
        self._form_layout.addWidget(form)

    def apply_chrome(self, chrome: FormChrome) -> None:
        width = int(chrome.focus_width or 1)
        _paint(self, chrome.window, chrome.text)
        _paint(self._toolbar, chrome.panel, chrome.text)
        self._toolbar.setStyleSheet(
            "background: %s; color: %s; border-bottom: 1px solid %s;"
            "QToolButton { background: transparent; color: %s; border: none; padding: 2px 8px; }"
            "QToolButton:checked { border: %dpx solid %s; }"
            "QToolButton:focus { border: %dpx solid %s; }"
            % (chrome.panel, chrome.text, chrome.border, chrome.text, width, chrome.accent, width, chrome.accent)
        )
        self._column.setStyleSheet("")
        self._form_parent.setStyleSheet("")
        self._splitter.setStyleSheet("QSplitter::handle { background: %s; }" % chrome.border)
        self.what_ran.apply_chrome(chrome)
        self.values.apply_chrome(chrome)
        self._keep_form_style()

    def _keep_form_style(self) -> None:
        """The person's form keeps the style it opened with. Only the chrome is themed."""
        native = self._native
        for widget in (self._column, self._form_parent):
            widget.setPalette(native)
            widget.setAutoFillBackground(True)
        host = self._form_layout.itemAt(0)
        form = host.widget() if host is not None else None
        if form is None:
            return
        form.setPalette(native)
        form.setAutoFillBackground(True)
        for child in form.findChildren(QWidget):
            child.setPalette(native)


def _shown_source(line: TryLine) -> str:
    if line.kind == "rule" and line.details:
        return "%d rules" % len(line.details)
    if line.kind in ("rule", "check", "step"):
        return source_label(line.ref)
    return line.ref


def _source_tip(line: TryLine) -> str:
    if line.details:
        return "\n".join("%s (%s)" % (source_label(ref), ref) for ref in line.details)
    if line.kind in ("rule", "check", "step"):
        return "%s (%s)" % (source_label(line.ref), line.ref)
    return line.ref


def _paint(widget: QWidget, background: str, foreground: str) -> None:
    widget.setAutoFillBackground(True)
    palette = widget.palette()
    fill = QColor(background)
    ink = QColor(foreground)
    palette.setColor(QPalette.Window, fill)
    palette.setColor(QPalette.WindowText, ink)
    widget.setPalette(palette)


def _elide_right():  # type: ignore[no-untyped-def]
    value = getattr(Qt, "ElideRight", None)
    if value is None:
        value = getattr(Qt.TextElideMode, "ElideRight")
    return value


def _header_mode(name: str):  # type: ignore[no-untyped-def]
    value = getattr(QHeaderView, name, None)
    if value is None:
        value = getattr(QHeaderView.ResizeMode, name)
    return value


def _user_role() -> int:
    role = getattr(Qt, "UserRole", None)
    if role is None:
        role = getattr(Qt.ItemDataRole, "UserRole")
    return int(role)


def _editor(parent: QWidget, name: str, annotation: str, value: object) -> QWidget:
    if annotation == "bool":
        box = QComboBox(parent)
        box.setAccessibleName("%s()" % name)
        box.blockSignals(True)
        box.addItems(["", "Yes", "No"])
        if value is True:
            box.setCurrentIndex(1)
        elif value is False:
            box.setCurrentIndex(2)
        else:
            box.setCurrentIndex(0)
        box.blockSignals(False)
        return box
    edit = QLineEdit(parent)
    edit.setAccessibleName("%s()" % name)
    shown = "" if value is None else value_to_wire(value, annotation)
    edit.setText(shown)
    return edit


def _connect(editor: QWidget, name: str, annotation: str, emit) -> None:
    if isinstance(editor, QComboBox):
        def on_combo(index: int, _name: str = name) -> None:
            if index <= 0:
                emit(_name, "")
            elif index == 1:
                emit(_name, "true")
            else:
                emit(_name, "false")

        editor.currentIndexChanged.connect(on_combo)
        return

    def on_text(text: str, _name: str = name, _annotation: str = annotation) -> None:
        del _annotation
        emit(_name, text)

    editor.textChanged.connect(on_text)  # type: ignore[attr-defined]


def current_value(editor: QWidget, annotation: str) -> object:
    """The live box as a formula value. ``None`` is unset."""
    if isinstance(editor, QComboBox):
        wire = {0: "", 1: "true"}.get(editor.currentIndex(), "false")
        if editor.currentIndex() <= 0:
            wire = ""
        return wire_to_value(wire, "bool")
    text = editor.text() if isinstance(editor, QLineEdit) else ""
    return wire_to_value(text, annotation)
