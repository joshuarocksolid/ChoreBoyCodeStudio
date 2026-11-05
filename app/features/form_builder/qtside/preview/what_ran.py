"""The Preview window when Run behavior is on: the form, Window values, and What ran.

Colours come from ``FormChrome``. This module does not import the shell.
"""

from __future__ import annotations

import re
import time
from typing import Dict, Mapping, Optional, Sequence, Tuple

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
from app.features.form_builder.qtside.theme.info_bar import TabInfoBar
from app.features.form_builder.qtside.theme.items import polish_item_view
from app.features.form_builder.qtside.theme.metrics import ROW, S2, TOOLBAR, TYPE_FINE
from app.features.form_builder.qtside.theme.section_header import SectionHeader
from app.qt.QtCore import Qt, Signal
from app.qt.QtGui import QBrush, QColor, QFont, QFontMetrics, QPalette, QPainter
from app.qt.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)
from app.qt.qt_compat import enum_value

_SOURCE_CAP = 240
_COUNT_SUFFIX = re.compile(r"^(?P<body>.*) \((?P<count>\d+ values?)\)$")
_WHAT_RAN_MIN = 360


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
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._header = SectionHeader(self, "What ran", object_name="preview.whatRan.title")
        self._header.set_pad(S2)
        self._header.setFocusPolicy(Qt.NoFocus)
        self._clear = self._header.add_action("reset", "Clear", "Clear")
        self._clear.setObjectName("preview.whatRan.clear")
        self._copy = self._header.add_action("copy", "Copy", "Copy")
        self._copy.setObjectName("preview.whatRan.copy")
        layout.addWidget(self._header)
        self._list = QTreeWidget(self)
        self._list.setObjectName("preview.whatRan.list")
        self._list.setColumnCount(3)
        self._list.setHeaderLabels(["Time", "What ran", "Source"])
        self._list.setRootIsDecorated(True)
        self._list.setTextElideMode(_elide_right())
        self._list.setItemDelegateForColumn(1, _SentenceDelegate(self._list))
        header = self._list.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, _header_mode("ResizeToContents"))
        header.setSectionResizeMode(1, _header_mode("Stretch"))
        header.setSectionResizeMode(2, _header_mode("ResizeToContents"))
        header.setSectionHidden(2, True)
        self.setMinimumWidth(_WHAT_RAN_MIN)
        self._list.itemClicked.connect(self._clicked)
        layout.addWidget(self._list, 1)
        self._clear.clicked.connect(self.clear)
        self._copy.clicked.connect(self.copy)
        self._lines: list[TryLine] = []
        self._names: Dict[str, str] = {}
        self._chrome = fallback_chrome()
        self._time_font = QFont()
        self._time_font.setPixelSize(TYPE_FINE)
        self._time_font.setStyleHint(QFont.Monospace)

    def set_names(self, names: Mapping[str, str]) -> None:
        """Object name to display name, sent with the preview start."""
        self._names = {str(key): value for key, value in names.items() if value}

    def add(self, lines: Sequence[TryLine], ts_ms: int) -> None:
        stamp = time.strftime("%H:%M:%S", time.localtime(ts_ms / 1000.0))
        for line in lines:
            if self._absorb_rule(line):
                continue
            item = QTreeWidgetItem([stamp, line.sentence, _shown_source(line, self._names)])
            item.setFont(0, self._time_font)
            item.setForeground(0, QBrush(QColor(self._chrome.muted)))
            item.setTextAlignment(0, Qt.AlignLeft | Qt.AlignVCenter)
            item.setData(0, _user_role(), line)
            item.setToolTip(1, line.sentence)
            item.setToolTip(2, _source_tip(line, self._names))
            if line.kind == "sql":
                full = QTreeWidgetItem(["", line.sentence, ""])
                full.setToolTip(1, line.sentence)
                full.setData(0, _user_role(), TryLine(line.sentence, line.ref, line.source, "sql"))
                item.addChild(full)
                for value in line.details:
                    child = QTreeWidgetItem(["", value, ""])
                    child.setToolTip(1, value)
                    child.setData(0, _user_role(), TryLine(value, "", source_of(""), "sql"))
                    item.addChild(child)
            else:
                for ref in line.details:
                    child = QTreeWidgetItem(["", source_label(ref, self._names), ""])
                    child.setToolTip(1, ref)
                    child.setToolTip(2, ref)
                    child.setData(
                        0,
                        _user_role(),
                        TryLine(source_label(ref, self._names), ref, source_of(ref), "rule"),
                    )
                    item.addChild(child)
            self._list.addTopLevelItem(item)
            self._lines.append(line)
        self._fit_columns()
        self._sync_source_column()
        if lines:
            self._list.scrollToItem(self._list.topLevelItem(self._list.topLevelItemCount() - 1))

    def expand_all(self) -> None:
        """Open every row so a screenshot shows the values."""

        for index in range(self._list.topLevelItemCount()):
            self._list.topLevelItem(index).setExpanded(True)

    def clear(self) -> None:
        self._list.clear()
        self._lines = []
        self._list.header().setSectionHidden(2, True)

    def _absorb_rule(self, line: TryLine) -> bool:
        """Fold the next identical Rules ran row into the one above it.

        Four refreshes of the same two rules become one row, ``Rules ran (2) ×4``.
        The children stay the rules of that one row. A check, a step, or a
        different rule list breaks the run.
        """
        if line.kind != "rule" or not line.sentence.startswith("Rules ran ("):
            return False
        count = self._list.topLevelItemCount()
        if count <= 0:
            return False
        item = self._list.topLevelItem(count - 1)
        prev = item.data(0, _user_role())
        if not isinstance(prev, TryLine) or prev.kind != "rule" or prev.details != line.details:
            return False
        base = _rule_base(prev.sentence)
        if base != line.sentence and base != _rule_base(line.sentence):
            return False
        if not base.startswith("Rules ran ("):
            return False
        times = _rule_times(item.text(1), base) + 1
        sentence = "%s \u00d7%d" % (base, times)
        merged = TryLine(sentence, prev.ref, prev.source, "rule", prev.method, prev.details)
        item.setText(1, sentence)
        item.setToolTip(1, sentence)
        item.setData(0, _user_role(), merged)
        if self._lines:
            self._lines[-1] = merged
        self._sync_source_column()
        return True

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

    def _sync_source_column(self) -> None:
        """Hide Source when every row's source cell is empty."""

        present = False
        for index in range(self._list.topLevelItemCount()):
            item = self._list.topLevelItem(index)
            if item.text(2).strip():
                present = True
                break
            for child_index in range(item.childCount()):
                if item.child(child_index).text(2).strip():
                    present = True
                    break
            if present:
                break
        self._list.header().setSectionHidden(2, not present)

    def apply_chrome(self, chrome: FormChrome) -> None:
        self._chrome = chrome
        _paint(self, chrome.panel, chrome.text)
        self._header.apply_chrome(chrome)
        polish_item_view(self._list, chrome)
        self._list.setStyleSheet(
            self._list.styleSheet()
            + (
                "QTreeWidget#preview\\.whatRan\\.list QHeaderView::section {"
                " background: %s; color: %s; border: none; border-bottom: 1px solid %s;"
                " padding: 0 4px; font-size: %dpx; font-weight: 600; }"
                % (chrome.panel, chrome.muted, chrome.border, TYPE_FINE)
            )
        )
        header = self._list.header()
        font = header.font()
        font.setPixelSize(TYPE_FINE)
        font.setWeight(QFont.DemiBold)
        header.setFont(font)
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)

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
        self.setVisible(False)

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
        """Window values sit with the form, on the light palette, not the editor theme."""

        del chrome
        from app.features.form_builder.qtside.theme.runtime import pin_runtime_look

        pin_runtime_look(self)


class DataStrip(QWidget):
    """The line under Window values. Reset data copies the SQLite file again."""

    reset_clicked = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("preview.dataStrip")
        self.setVisible(False)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 8)
        self._label = QLabel("", self)
        self._label.setObjectName("preview.dataStrip.label")
        self._label.setWordWrap(True)
        layout.addWidget(self._label, 1)
        self._reset = QPushButton("Reset data", self)
        self._reset.setObjectName("preview.dataStrip.reset")
        self._reset.setVisible(False)
        self._reset.setFlat(False)
        self._reset.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self._reset.clicked.connect(self.reset_clicked.emit)
        layout.addWidget(self._reset, 0)

    def set_text(self, text: str, reset: bool) -> None:
        self._label.setText(text)
        shown = bool(text)
        self.setVisible(shown)
        self._reset.setVisible(shown and reset)
        if reset:
            self.setAccessibleName("%s [Reset data]" % text)
        else:
            self.setAccessibleName(text)

    def apply_chrome(self, chrome: FormChrome) -> None:
        width = int(chrome.focus_width or 1)
        self.setAutoFillBackground(False)
        self._label.setFrameShape(QFrame.NoFrame)
        self.setStyleSheet(
            "QWidget#preview\\.dataStrip { background: transparent; color: %s; border: none; }"
            "QLabel#preview\\.dataStrip\\.label { color: %s; background: transparent; border: none; }"
            % (chrome.text, chrome.text)
        )
        self._reset.setStyleSheet(
            "QPushButton#preview\\.dataStrip\\.reset { color: %s; background: %s; border: 1px solid %s;"
            " padding: 4px 12px; border-radius: 3px; }"
            "QPushButton#preview\\.dataStrip\\.reset:focus { border: %dpx solid %s; }"
            % (chrome.text, chrome.panel, chrome.muted or chrome.border, width, chrome.accent)
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
        self._toolbar.setFixedHeight(TOOLBAR)
        bar = QHBoxLayout(self._toolbar)
        bar.setContentsMargins(S2, 0, S2, 0)
        self.run_behavior = QToolButton(self._toolbar)
        self.run_behavior.setObjectName("preview.runBehavior")
        self.run_behavior.setText("Run behavior")
        self.run_behavior.setAccessibleName("Run behavior")
        self.run_behavior.setToolTip(
            "Starts checked. Runs checks, steps, and rules, and undoes database changes. Uncheck to see the layout only."
        )
        self.run_behavior.setCheckable(True)
        self.run_behavior.setChecked(True)
        self.run_behavior.setAutoRaise(True)
        self.run_behavior.setToolButtonStyle(getattr(getattr(Qt, "ToolButtonStyle", Qt), "ToolButtonTextOnly"))
        self.run_behavior.toggled.connect(self.run_toggled.emit)
        bar.addWidget(self.run_behavior)
        bar.addStretch(1)
        root.addWidget(self._toolbar)
        self._banner = TabInfoBar(self)
        self._banner.setObjectName("preview.banner")
        self._banner.set_glyph("info")
        self._banner.set_text("")
        root.addWidget(self._banner)
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
        self.data_strip = DataStrip(left)
        left_layout.addWidget(self._form_parent, 1)
        left_layout.addWidget(self.values, 0)
        left_layout.addWidget(self.data_strip, 0)
        self.what_ran = WhatRan(self._splitter)
        self._splitter.addWidget(left)
        self._splitter.addWidget(self.what_ran)
        self._splitter.setStretchFactor(0, 3)
        self._splitter.setStretchFactor(1, 2)
        self._splitter.setChildrenCollapsible(False)
        self._splitter.setHandleWidth(6)
        root.addWidget(self._splitter, 1)
        from app.qt.QtWidgets import QApplication

        app = QApplication.instance()
        self._native = QPalette(app.palette() if app is not None else self.palette())
        self._chrome = fallback_chrome()
        self.apply_chrome(self._chrome)

    def showEvent(self, event: object) -> None:  # noqa: N802
        super().showEvent(event)  # type: ignore[arg-type]
        self._share_what_ran()

    def _share_what_ran(self) -> None:
        """What ran starts at about 40% of the window, and at least 360 px."""

        total = self._splitter.width()
        if total < _WHAT_RAN_MIN + 80:
            return
        right = max(_WHAT_RAN_MIN, int(total * 0.4))
        if right > total - 80:
            right = total - 80
        self._splitter.setSizes([total - right, right])

    def form_parent(self) -> QWidget:
        return self._form_parent

    def adopt(self, form: QWidget) -> None:
        form.setParent(self._form_parent)
        self._form_layout.addWidget(form)
        self._keep_form_style()

    def apply_chrome(self, chrome: FormChrome) -> None:
        self._chrome = chrome
        focus = int(chrome.focus_width or 1)
        _paint(self, chrome.window, chrome.text)
        _paint(self._toolbar, chrome.panel, chrome.text)
        chosen = chrome.selected or chrome.row_hover
        self._toolbar.setStyleSheet(
            "QWidget#preview\\.toolbar { background: %s; color: %s; border-bottom: 1px solid %s; }"
            "QToolButton#preview\\.runBehavior { background: transparent; color: %s; border: none; padding: 2px 8px; }"
            "QToolButton#preview\\.runBehavior:checked { background: %s; color: %s; }"
            "QToolButton#preview\\.runBehavior:focus { border: %dpx solid %s; }"
            % (chrome.panel, chrome.text, chrome.border, chrome.text, chosen, chrome.text, focus, chrome.accent)
        )
        self._column.setStyleSheet("")
        self._form_parent.setStyleSheet("")
        self._splitter.setStyleSheet(
            "QSplitter#preview\\.splitter::handle { background: %s; border: none; margin: 0px 2px; }"
            % chrome.border
        )
        self.what_ran.apply_chrome(chrome)
        self.values.apply_chrome(chrome)
        self.data_strip.apply_chrome(chrome)
        self._banner.apply_chrome(chrome)
        self._keep_form_style()

    def set_try_data(self, text: str, banner: str, reset: bool) -> None:
        """The data strip under Window values, and the rollback banner."""

        self.data_strip.set_text(text, reset)
        self._banner.set_text(banner)
        if banner:
            self._banner.setAccessibleName(banner)

    def _keep_form_style(self) -> None:
        """The person's form keeps the light runtime look. Only the chrome is themed."""

        from app.features.form_builder.qtside.theme.runtime import pin_runtime_look

        self.values.apply_chrome(self._chrome)
        host = self._form_layout.itemAt(0)
        form = host.widget() if host is not None else None
        if form is None:
            return
        pin_runtime_look(form)


def _shown_source(line: TryLine, names: Mapping[str, str]) -> str:
    if line.kind == "rule" and line.details:
        return "%d rules" % len(line.details)
    if line.kind in ("rule", "check", "step"):
        return source_label(line.ref, names)
    return line.ref


def _source_tip(line: TryLine, names: Mapping[str, str]) -> str:
    if line.details:
        return "\n".join("%s (%s)" % (source_label(ref, names), ref) for ref in line.details)
    if line.kind in ("rule", "check", "step"):
        return "%s (%s)" % (source_label(line.ref, names), line.ref)
    return line.ref


def _rule_base(sentence: str) -> str:
    mark = " \u00d7"
    if mark in sentence:
        head, _, tail = sentence.rpartition(mark)
        if tail.isdigit() and head.startswith("Rules ran ("):
            return head
    return sentence


def _rule_times(shown: str, base: str) -> int:
    if shown == base:
        return 1
    mark = " \u00d7"
    if shown.startswith(base + mark):
        tail = shown[len(base) + len(mark) :]
        if tail.isdigit():
            return int(tail)
    return 1


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


def _split_count(text: str) -> Tuple[str, str]:
    """Separate a trailing ``(6 values)`` so only the statement is elided."""

    match = _COUNT_SUFFIX.match(text)
    if match is None:
        return text, ""
    return match.group("body"), "(%s)" % match.group("count")


def _advance(metrics: QFontMetrics, text: str) -> int:
    method = getattr(metrics, "horizontalAdvance", None)
    if method is None:
        return int(metrics.width(text))  # type: ignore[attr-defined]
    return int(method(text))


class _SentenceDelegate(QStyledItemDelegate):
    """Elide the statement on the right and keep ``(n values)`` in full."""

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: object) -> None:
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        body, count = _split_count(opt.text or "")
        opt.text = ""
        widget = opt.widget
        style = widget.style() if widget is not None else None
        painter.save()
        if style is None:
            painter.restore()
            super().paint(painter, option, index)  # type: ignore[arg-type]
            return
        parent = index.parent() if hasattr(index, "parent") else None
        expanded = parent is not None and parent.isValid()
        style.drawPrimitive(QStyle.PE_PanelItemViewItem, opt, painter, widget)
        metrics = QFontMetrics(opt.font)
        suffix = (" " + count) if count else ""
        rect = style.subElementRect(QStyle.SE_ItemViewItemText, opt, widget)
        if rect.width() <= 0:
            rect = opt.rect
        if expanded:
            shown = body
        else:
            room = max(0, rect.width() - (_advance(metrics, suffix) if suffix else 0))
            shown = metrics.elidedText(body, _elide_right(), room)
        selected = bool(enum_value(opt.state) & enum_value(QStyle.State_Selected))
        color = opt.palette.highlightedText().color() if selected else opt.palette.text().color()
        painter.setPen(color)
        painter.setFont(opt.font)
        painter.drawText(rect, int(enum_value(Qt.AlignLeft) | enum_value(Qt.AlignVCenter)), shown + suffix)
        painter.restore()


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
