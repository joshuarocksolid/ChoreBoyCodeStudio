"""Workbench shell: top bar, outline and palette, canvas, inspector, status bar."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import time
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from spikes.form_builder import sizing
from spikes.form_builder.canvas import Canvas, class_default, content_for, start_drag
from spikes.form_builder.catalog import CATALOG, fuzzy
from spikes.form_builder.commands import (
    Compound,
    Delete,
    History,
    SetProperty,
    SetTabStops,
    Unwrap,
    Wrap,
    delete_targets,
    duplicate_item,
    insert_near,
    remove_action_ref_command,
    RemoveLayout,
    resolve_layout_item,
)
from spikes.form_builder.generate import generate_ui
from spikes.form_builder.icons import icon, pixmap
from spikes.form_builder.inspector import Inspector
from spikes.form_builder.kit import IconButton, SegmentedControl, Toast, hairline, label, overline
from spikes.form_builder.model import (
    Action,
    ActionRef,
    Layout,
    Spacer,
    Widget,
    child_widgets,
    clone_widget,
    find_node,
    form_class_name,
    get_property,
    iter_widgets,
    layout_items,
    locate,
    problems,
    prop_string,
    widget_layout,
)
from spikes.form_builder.outline import Outline, QuickInsert
from spikes.form_builder.perf import log_sample
from spikes.form_builder.screens import StartScreen, TableDialog, remember_file
from spikes.form_builder.theme import apply_theme, current, system_theme
from spikes.form_builder.xmlio import load_path, save_path

WRAPS = (
    ("Vertical", "QWidget", "QVBoxLayout", "QVBoxLayout"),
    ("Horizontal", "QWidget", "QHBoxLayout", "QHBoxLayout"),
    ("Grid", "QWidget", "QGridLayout", "QGridLayout"),
    ("Form", "QWidget", "QFormLayout", "QFormLayout"),
    ("Group box", "QGroupBox", "QVBoxLayout", "QGroupBox"),
    ("Frame", "QFrame", "QVBoxLayout", "QFrame"),
)
TEXT_PROPS = ("text", "title", "placeholderText", "plainText", "windowTitle")
CATEGORIES = ("Layouts", "Input", "Buttons", "Display", "Containers", "Item views")
SHORT_LABELS = {
    "Vertical layout": "Vertical",
    "Horizontal layout": "Horizontal",
    "Grid layout": "Grid",
    "Form layout": "Form",
    "Horizontal spacer": "H spacer",
    "Vertical spacer": "V spacer",
    "Dialog button box": "OK / Cancel",
    "Double spin box": "Decimal",
    "Spin box": "Number",
    "Date and time": "Date time",
    "Stacked widget": "Stack",
    "Scroll area": "Scroll area",
}


class PaletteTile(QToolButton):
    """A widget-box tile: drag it to the canvas, or double-click to insert after the selection."""

    def __init__(self, entry, on_insert):
        super().__init__()
        self.entry = entry
        self.on_insert = on_insert
        self.setText(SHORT_LABELS.get(entry.label, entry.label))
        self.setToolTip(f"{entry.label} · {entry.class_name}\nDrag onto the form, or double-click to insert.")
        self.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.setIconSize(QSize(20, 20))
        self.setFixedSize(74, 58)
        self.setCursor(Qt.OpenHandCursor)
        self.setStyleSheet("QToolButton { font-size: 11px; padding: 4px 2px; }")
        self._press = None
        self.refresh()

    def refresh(self):
        tokens = current()
        color = tokens.layout if self.entry.kind == "layout" else (tokens.gap if self.entry.kind == "spacer" else tokens.muted)
        self.setIcon(icon(self.entry.class_name, color, 20))

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == event.Type.PaletteChange:
            self.refresh()

    def mousePressEvent(self, event):
        self._press = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._press is not None and (event.position().toPoint() - self._press).manhattanLength() > 6:
            self._press = None
            self.setDown(False)
            start_drag(self, self.entry)
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._press = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, _event):
        self.on_insert(self.entry)


class Palette(QWidget):
    def __init__(self, on_insert):
        super().__init__()
        self.on_insert = on_insert
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 6, 8)
        layout.setSpacing(6)
        self.filter = QLineEdit()
        self.filter.setObjectName("Search")
        self.filter.setPlaceholderText("Filter widgets")
        self.filter.addAction(icon("search", current().faint), QLineEdit.LeadingPosition)
        layout.addWidget(self.filter)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        layout.addWidget(self.scroll, 1)
        self.filter.textChanged.connect(self.refresh)
        self.refresh("")

    def refresh(self, text: str = ""):
        body = QWidget()
        body.setObjectName("Panel")
        column = QVBoxLayout(body)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(4)
        for category in CATEGORIES:
            entries = [entry for entry in CATALOG if entry.category == category and (fuzzy(text, entry.label) or fuzzy(text, entry.class_name))]
            if not entries:
                continue
            column.addWidget(overline(category))
            grid = QGridLayout()
            grid.setContentsMargins(0, 0, 0, 6)
            grid.setSpacing(2)
            for position, entry in enumerate(entries):
                grid.addWidget(PaletteTile(entry, self.on_insert), position // 3, position % 3)
            grid.setColumnStretch(3, 1)
            column.addLayout(grid)
        column.addStretch(1)
        old = self.scroll.takeWidget()
        if old is not None:
            old.deleteLater()
        self.scroll.setWidget(body)


class TopBar(QWidget):
    def __init__(self, window):
        super().__init__()
        self.setObjectName("TopBar")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(48)
        row = QHBoxLayout(self)
        row.setContentsMargins(8, 0, 10, 0)
        row.setSpacing(6)
        self.back = IconButton("chevron-left", "Back to the start screen", text="Start")
        self.back.clicked.connect(window.show_start)
        row.addWidget(self.back)
        row.addWidget(hairline(vertical=True))
        self.file_mark = QLabel()
        self.file_mark.setPixmap(pixmap("file", current().muted, 16))
        row.addWidget(self.file_mark)
        self.file_name = label("Untitled", "FileName")
        row.addWidget(self.file_name)
        self.dirty = label("", "Faint")
        row.addWidget(self.dirty)
        row.addStretch(1)
        self.modes = SegmentedControl(
            [("design", "Design", "design", "Design (Ctrl+1)"), ("tab", "Tab order", "order", "Tab order (Ctrl+2)"), ("buddy", "Buddies", "link", "Buddies (Ctrl+3)")],
            "design",
        )
        self.modes.changed.connect(window.set_mode)
        row.addWidget(self.modes)
        row.addStretch(1)
        self.undo = IconButton("undo", "Undo (Ctrl+Z)")
        self.undo.clicked.connect(window.undo)
        self.redo = IconButton("redo", "Redo (Ctrl+Shift+Z)")
        self.redo.clicked.connect(window.redo)
        row.addWidget(self.undo)
        row.addWidget(self.redo)
        row.addWidget(hairline(vertical=True))
        zoom_out = IconButton("minus", "Zoom out (Ctrl+-)")
        zoom_out.clicked.connect(lambda: window.set_zoom_value(window.zoom_value / 1.25))
        self.zoom_label = QPushButton("100%")
        self.zoom_label.setObjectName("Ghost")
        self.zoom_label.setStyleSheet("padding: 4px 2px;")
        self.zoom_label.setFixedWidth(52)
        self.zoom_label.setToolTip("Reset to 100% (Ctrl+0)")
        self.zoom_label.clicked.connect(lambda: window.set_zoom_value(1.0))
        zoom_in = IconButton("plus", "Zoom in (Ctrl+=)")
        zoom_in.clicked.connect(lambda: window.set_zoom_value(window.zoom_value * 1.25))
        row.addWidget(zoom_out)
        row.addWidget(self.zoom_label)
        row.addWidget(zoom_in)
        row.addWidget(hairline(vertical=True))
        self.text_size = SegmentedControl(
            [("s", "S", "", "Preview small text"), ("m", "M", "", "Preview normal text"), ("l", "L", "", "Preview large text: check the form still fits")],
            "m",
            compact=True,
        )
        self.text_size.setToolTip("Preview text size. Laid-out forms reflow; nothing is saved.")
        self.text_size.changed.connect(window.set_text_size)
        row.addWidget(self.text_size)
        self.widths = IconButton("two-widths", "Show the form at two widths side by side", checkable=True)
        self.widths.toggled.connect(window.set_two_widths)
        row.addWidget(self.widths)
        row.addWidget(hairline(vertical=True))
        self.preview = QPushButton("Preview")
        self.preview.setIcon(icon("play", current().muted))
        self.preview.setToolTip("Run the form from its generated module (Ctrl+R)")
        self.preview.clicked.connect(window.preview)
        self.save = QPushButton("Save")
        self.save.setObjectName("Primary")
        self.save.setToolTip("Save the .ui file and regenerate ui_<name>.py (Ctrl+S)")
        self.save.clicked.connect(window.save)
        row.addWidget(self.preview)
        row.addWidget(self.save)


class WrapPopover(QFrame):
    """Wrap the selection: six tiles, arrow keys or 1-6, Enter."""

    def __init__(self, parent, on_pick):
        super().__init__(parent, Qt.Popup)
        self.setObjectName("Popover")
        self.on_pick = on_pick
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        self.title = label("Wrap in…", "Small")
        layout.addWidget(self.title)
        grid = QGridLayout()
        grid.setSpacing(4)
        self.tiles = []
        for position, (words, container, layout_class, glyph) in enumerate(WRAPS):
            tile = QToolButton()
            tile.setText(f"{words}")
            tile.setToolTip(f"{position + 1}: wrap in a {words.lower()}")
            tile.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            tile.setIconSize(QSize(22, 22))
            tile.setFixedSize(84, 62)
            tile.setCheckable(True)
            color = current().layout if container == "QWidget" else current().muted
            tile.setIcon(icon(glyph, color, 22))
            tile.clicked.connect(lambda _checked=False, c=container, lay=layout_class: self._pick(c, lay))
            grid.addWidget(tile, position // 3, position % 3)
            self.tiles.append((tile, container, layout_class))
        layout.addLayout(grid)
        layout.addWidget(label("1–6 or arrows, Enter to wrap · Esc to cancel", "Faint"))
        self.current = 0
        self._mark()

    def _mark(self):
        for position, (tile, _c, _l) in enumerate(self.tiles):
            tile.setChecked(position == self.current)

    def _pick(self, container, layout_class):
        self.close()
        self.on_pick(container, layout_class)

    def keyPressEvent(self, event):
        key = event.key()
        if Qt.Key_1 <= key <= Qt.Key_6:
            _tile, container, layout_class = self.tiles[key - Qt.Key_1]
            self._pick(container, layout_class)
            return
        moves = {Qt.Key_Left: -1, Qt.Key_Right: 1, Qt.Key_Up: -3, Qt.Key_Down: 3}
        if key in moves:
            self.current = max(0, min(len(self.tiles) - 1, self.current + moves[key]))
            self._mark()
            return
        if key in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            _tile, container, layout_class = self.tiles[self.current]
            self._pick(container, layout_class)
            return
        super().keyPressEvent(event)


class MainWindow(QMainWindow):
    def __init__(self, theme_name: str = "light", follow_system: bool = False):
        super().__init__()
        self.setWindowTitle("Form Builder")
        self.theme_name = theme_name
        self.follow_system = follow_system
        self.doc = None
        self.history = None
        self.path = None
        self.clipboard = []
        self.previews = []
        self._syncing = False
        self.last_open = None
        self.last_edit = None
        self.last_save = None
        self.zoom_value = 1.0
        self.saved_note = ""
        apply_theme(QApplication.instance(), theme_name, [self])
        self.stack = QStackedWidget()
        self.start = StartScreen()
        self.start.opened.connect(self._start_choice)
        self.work = self._workbench()
        self.stack.addWidget(self.start)
        self.stack.addWidget(self.work)
        self.setCentralWidget(self.stack)
        self._actions()
        self._menus()
        self._status()
        self.quick = QuickInsert(self)
        self.quick.chosen.connect(self.insert_entry)
        self.toast = Toast(self.canvas)
        app = QApplication.instance()
        app.styleHints().colorSchemeChanged.connect(self._system_scheme_changed)

    # ------------------------------------------------------------------ layout
    def _workbench(self):
        self.canvas = Canvas()
        self.canvas.selection_changed.connect(self._canvas_selected)
        self.canvas.status_text.connect(self._hint)
        self.canvas.timed.connect(self._timed)
        self.canvas.context_requested.connect(self._context_menu)
        self.canvas.text_edit_requested.connect(self.edit_text)
        self.outline = Outline()
        self.outline.selection_made.connect(self._outline_selected)
        self.outline.context_requested.connect(self._context_menu)
        self.outline.quick_insert.connect(self.open_quick_insert)
        self.outline.status.connect(self._hint)
        self.palette = Palette(self.insert_entry)
        self.inspector = Inspector()
        self.inspector.select_request.connect(self._select)
        self.inspector.status.connect(self._hint)
        self.inspector.remove_layout.connect(self.remove_layout)
        left = QWidget()
        left.setObjectName("Panel")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)
        outline_head = QHBoxLayout()
        outline_head.setContentsMargins(14, 10, 8, 4)
        outline_head.addWidget(overline("Outline"))
        outline_head.addStretch(1)
        insert = IconButton("plus", "Insert a widget after the selection ( / )")
        insert.clicked.connect(self.open_quick_insert)
        outline_head.addWidget(insert)
        left_layout.addLayout(outline_head)
        split = QSplitter(Qt.Vertical)
        split.setChildrenCollapsible(False)
        outline_host = QWidget()
        outline_box = QVBoxLayout(outline_host)
        outline_box.setContentsMargins(6, 0, 4, 0)
        outline_box.addWidget(self.outline)
        palette_host = QWidget()
        palette_box = QVBoxLayout(palette_host)
        palette_box.setContentsMargins(0, 0, 0, 0)
        palette_box.setSpacing(0)
        palette_head = QHBoxLayout()
        palette_head.setContentsMargins(14, 10, 8, 0)
        palette_head.addWidget(overline("Insert"))
        palette_head.addStretch(1)
        palette_box.addLayout(palette_head)
        palette_box.addWidget(self.palette, 1)
        split.addWidget(outline_host)
        split.addWidget(palette_host)
        split.setStretchFactor(0, 5)
        split.setStretchFactor(1, 4)
        left_layout.addWidget(split, 1)
        panes = QSplitter()
        panes.setChildrenCollapsible(False)
        panes.addWidget(left)
        panes.addWidget(self.canvas)
        panes.addWidget(self.inspector)
        panes.setStretchFactor(1, 1)
        left.setMinimumWidth(240)
        self.inspector.setMinimumWidth(300)
        panes.setSizes([262, 690, 338])
        host = QWidget()
        layout = QVBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.top = TopBar(self)
        layout.addWidget(self.top)
        layout.addWidget(panes, 1)
        return host

    def _status(self):
        bar = QStatusBar()
        bar.setSizeGripEnabled(False)
        self.insert_label = QLabel("")
        self.problem_button = QPushButton("No problems")
        self.problem_button.setObjectName("Ghost")
        self.problem_button.setStyleSheet("font-size: 12px; padding: 1px 8px;")
        self.problem_button.clicked.connect(self._show_problems)
        self.problem_button.hide()
        self.save_label = QLabel("")
        self.perf_label = QLabel("")
        self.perf_label.setObjectName("Faint")
        bar.addWidget(self.insert_label, 1)
        bar.addPermanentWidget(self.problem_button)
        bar.addPermanentWidget(self.save_label)
        bar.addPermanentWidget(self.perf_label)
        self.setStatusBar(bar)

    # ------------------------------------------------------------------ actions
    def _act(self, text, slot, shortcut=None, context=Qt.WindowShortcut):
        action = QAction(text, self)
        action.triggered.connect(slot)
        if shortcut is not None:
            if isinstance(shortcut, (list, tuple)):
                action.setShortcuts([QKeySequence(item) for item in shortcut])
            else:
                action.setShortcut(QKeySequence(shortcut))
            action.setShortcutContext(context)
        self.addAction(action)
        return action

    def _actions(self):
        control = Qt.MetaModifier if sys.platform == "darwin" else Qt.ControlModifier
        self.a = {
            "new": self._act("New…", self.show_start, QKeySequence.New),
            "open": self._act("Open…", self.open_ui, QKeySequence.Open),
            "save": self._act("Save", self.save, QKeySequence.Save),
            "save_as": self._act("Save as…", self.save_as, QKeySequence.SaveAs),
            "window_class": self._act("Create window class", self.create_window_class),
            "preview": self._act("Preview", self.preview, "Ctrl+R"),
            "undo": self._act("Undo", self.undo, QKeySequence.Undo),
            "redo": self._act("Redo", self.redo, ["Ctrl+Shift+Z", "Ctrl+Y"]),
            "cut": self._act("Cut", self.cut_selection, QKeySequence.Cut),
            "copy": self._act("Copy", self.copy_selection, QKeySequence.Copy),
            "paste": self._act("Paste", self.paste_selection, QKeySequence.Paste),
            "duplicate": self._act("Duplicate", self.duplicate_selection, "Ctrl+D"),
            "delete": self._act("Delete", self.delete_selection, [QKeySequence(Qt.Key_Delete), QKeySequence(Qt.Key_Backspace)]),
            "wrap": self._act("Wrap in…", self.wrap_menu, QKeySequence(control | Qt.Key_G)),
            "unwrap": self._act("Unwrap", self.unwrap_selection, QKeySequence(control | Qt.ShiftModifier | Qt.Key_G)),
            "parent": self._act("Select parent", self.escape, Qt.Key_Escape),
            "edit_text": self._act("Edit text", self._f2, "F2"),
            "rename": self._act("Rename", self.rename_selection, "Shift+F2"),
            "insert": self._act("Insert widget…", self.open_quick_insert, "/"),
            "move_up": self._act("Move up", lambda: self.move_selection(-1), "Alt+Up"),
            "move_down": self._act("Move down", lambda: self.move_selection(1), "Alt+Down"),
            "design": self._act("Design", lambda: self.set_mode("design"), "Ctrl+1"),
            "tab": self._act("Tab order", lambda: self.set_mode("tab"), "Ctrl+2"),
            "buddy": self._act("Buddies", lambda: self.set_mode("buddy"), "Ctrl+3"),
            "zoom_in": self._act("Zoom in", lambda: self.set_zoom_value(self.zoom_value * 1.25), ["Ctrl+=", "Ctrl++"]),
            "zoom_out": self._act("Zoom out", lambda: self.set_zoom_value(self.zoom_value / 1.25), "Ctrl+-"),
            "zoom_reset": self._act("Actual size", lambda: self.set_zoom_value(1.0), "Ctrl+0"),
            "remove_layout": self._act("Remove layout…", lambda: self.remove_layout(self.canvas.selection[0]) if self.canvas.selection else None),
            "reset_tabs": self._act("Reset tab order to reading order", self._reset_tabs),
            "pair": self._act("Pair labels with fields", lambda: self.inspector._pair()),
        }

    def _f2(self):
        """F2 renames in the outline and edits the visible text on the canvas."""
        if self.outline.hasFocus() and self.outline.currentItem() is not None:
            self.outline.editItem(self.outline.currentItem(), 0)
            return
        if self.canvas.selection:
            self.edit_text(self.canvas.selection[0])

    def _menus(self):
        bar = self.menuBar()
        file_menu = bar.addMenu("File")
        for key in ("new", "open", None, "save", "save_as", None, "window_class", "preview"):
            file_menu.addSeparator() if key is None else file_menu.addAction(self.a[key])
        edit = bar.addMenu("Edit")
        for key in ("undo", "redo", None, "cut", "copy", "paste", "duplicate", "delete", None, "edit_text", "rename", "insert"):
            edit.addSeparator() if key is None else edit.addAction(self.a[key])
        form = bar.addMenu("Form")
        for key in ("wrap", "unwrap", "remove_layout", None, "move_up", "move_down", "parent", None, "reset_tabs", "pair"):
            form.addSeparator() if key is None else form.addAction(self.a[key])
        view = bar.addMenu("View")
        for key in ("design", "tab", "buddy", None, "zoom_in", "zoom_out", "zoom_reset"):
            view.addSeparator() if key is None else view.addAction(self.a[key])
        view.addSeparator()
        appearance = view.addMenu("Appearance")
        group = QActionGroup(self)
        for name, words in (("system", "Follow the system"), ("light", "Light"), ("dark", "Dark"), ("hc-light", "High contrast light"), ("hc-dark", "High contrast dark")):
            action = appearance.addAction(words, lambda _checked=False, theme=name: self.set_theme(theme))
            action.setCheckable(True)
            action.setChecked(name == ("system" if self.follow_system else self.theme_name))
            group.addAction(action)

    # ------------------------------------------------------------------ start
    def show_start(self):
        self.start.refresh_recent()
        self.stack.setCurrentWidget(self.start)
        self.setWindowTitle("Form Builder")
        self.insert_label.setText("")
        self.problem_button.hide()
        self.save_label.setText("")
        self.perf_label.setText("")

    def _start_choice(self, choice):
        if choice == "open":
            self.open_ui()
            return
        if choice == "table":
            self.open_table()
            return
        if isinstance(choice, tuple) and choice[0] == "path":
            self.load_document(load_path(choice[1]), choice[1])
            return
        self.load_document(choice(), None)

    def open_table(self):
        dialog = TableDialog(self)
        if dialog.exec() == QDialog.Accepted and dialog.table_name:
            self.load_document(dialog.document(), None)
            self.toast.show_message("Form laid out from the table. Labels are buddied and tab order is set.")

    def open_ui(self):
        path, _selected = QFileDialog.getOpenFileName(self, "Open form", "", "Qt forms (*.ui)")
        if path:
            self.load_document(load_path(path), path)
            remember_file(path)

    def load_document(self, doc, path):
        self.doc = doc
        self.history = History(doc)
        self.history.listeners.append(self._on_edit)
        self.path = path
        self.saved_note = ""
        self.set_mode("design")
        self.canvas.set_document(doc, self.history)
        self.outline.set_document(doc, self.history)
        self.inspector.set_session(doc, self.history, self.canvas, path)
        self.inspector.show_selection([])
        self.stack.setCurrentWidget(self.work)
        self._refresh_chrome()

    # ------------------------------------------------------------------ edits
    def _on_edit(self, command):
        self.canvas.on_command(command)
        self.outline.rebuild()
        self.inspector.show_selection(self.canvas.selection)
        self._refresh_chrome()

    def _canvas_selected(self, ids):
        if self._syncing:
            return
        self._syncing = True
        self.outline.select_ids(ids)
        self.inspector.show_selection(ids)
        self._syncing = False
        self._refresh_chrome()

    def _outline_selected(self, ids):
        if self._syncing:
            return
        self._syncing = True
        self.canvas.set_selection(ids)
        self.inspector.show_selection(ids)
        self._syncing = False

    def _select(self, ids):
        self.canvas.set_selection(ids)
        self.outline.select_ids(ids)
        self.inspector.show_selection(ids)

    def set_mode(self, mode):
        self.top.modes.set_current(mode)
        self.canvas.set_mode(mode)
        hints = {
            "design": "",
            "tab": "Tab order: click fields in order. Shift-click to start from a field. Esc when done.",
            "buddy": "Buddies: drag from a label to its field. Esc when done.",
        }
        self._hint(hints.get(mode, ""))

    def set_theme(self, name):
        app = QApplication.instance()
        self.follow_system = name == "system"
        self.theme_name = system_theme(app) if self.follow_system else name
        tokens = apply_theme(app, self.theme_name, [self])
        self.canvas.set_tokens(tokens)
        self.top.file_mark.setPixmap(pixmap("file", tokens.muted, 16))
        self.top.preview.setIcon(icon("play", tokens.muted))
        if self.doc is not None:
            self.inspector.show_selection(self.canvas.selection)
            self.outline.viewport().update()
        self.palette.refresh(self.palette.filter.text())

    def _system_scheme_changed(self, _scheme):
        if self.follow_system:
            self.set_theme("system")

    def set_zoom_value(self, value: float):
        self.zoom_value = max(0.25, min(4.0, value))
        self.canvas.set_zoom(self.zoom_value)
        self.top.zoom_label.setText(f"{round(self.zoom_value * 100)}%")

    def set_text_size(self, key):
        base = QApplication.font().pointSizeF()
        size = {"s": base * 0.85, "m": base, "l": base * 1.3}.get(key, base)
        self.canvas.set_text_size(size)
        if key != "m":
            self._hint("Text-size preview only. The file is unchanged; a laid-out form reflows.")

    def set_two_widths(self, enabled):
        self.canvas.set_two_widths(enabled)

    def _timed(self, kind, milliseconds):
        if kind == "open":
            self.last_open = milliseconds
        elif kind == "edit":
            self.last_edit = milliseconds
        log_sample(kind, milliseconds, self.path or "")
        if self.last_edit is not None:
            self.perf_label.setText(f"{kind} {milliseconds:.1f} ms")

    def _hint(self, text):
        self.insert_label.setText(text or self._default_hint())

    def _default_hint(self) -> str:
        if self.doc is None:
            return ""
        if self.canvas.mode == "design" and self.canvas.selection:
            return "Tab nests · Shift+Tab un-nests · Alt+↑↓ moves · / inserts after · Ctrl+G wraps · F2 edits text"
        return "Drag from Insert, or press / . Click to select, Esc for the parent."

    def _refresh_chrome(self):
        if self.doc is None:
            return
        self.problem_button.show()
        count = len(problems(self.doc))
        tokens = current()
        if count:
            self.problem_button.setText(f"{count} problem{'s' if count != 1 else ''}")
            self.problem_button.setIcon(icon("warning", tokens.warn))
        else:
            self.problem_button.setText("No problems")
            self.problem_button.setIcon(icon("check-mark", tokens.ok))
        dirty = self.history is not None and self.history.dirty
        name = Path(self.path).name if self.path else f"{form_class_name(self.doc)}.ui"
        self.top.file_name.setText(name)
        self.top.dirty.setText("● edited" if dirty else ("" if self.path else "not saved yet"))
        self.top.undo.setEnabled(bool(self.history and self.history.undo_stack))
        self.top.redo.setEnabled(bool(self.history and self.history.redo_stack))
        if dirty:
            self.save_label.setText("Unsaved changes")
        else:
            self.save_label.setText(self.saved_note)
        self.setWindowTitle(("• " if dirty else "") + name + " — Form Builder")
        self._hint("")

    def _show_problems(self):
        self._select([])
        self.inspector.show_tab("properties")

    # ------------------------------------------------------------------ commands
    def undo(self):
        if self.history is not None and self.history.undo():
            self._prune_selection()

    def redo(self):
        if self.history is not None and self.history.redo():
            self._prune_selection()

    def _prune_selection(self):
        ids = [node_id for node_id in self.canvas.selection if find_node(self.doc, node_id) is not None]
        self._select(ids)

    def _ids(self):
        return list(self.canvas.selection)

    def delete_selection(self):
        if self.doc is None or not self.canvas.selection:
            return
        ids = [node_id for node_id in self._ids() if node_id != self.doc.root.id]
        actions = [node_id for node_id in ids if isinstance(find_node(self.doc, node_id), Action)]
        if actions:
            self._delete_actions(actions)
            return
        targets = delete_targets(self.doc, ids)
        if not targets:
            return
        self.outline._after_delete(ids)
        count = len(targets)
        self.history.execute(Delete(targets))
        self.toast.show_message(f"Deleted {count} item{'s' if count != 1 else ''}", "Undo", self.undo)

    def _delete_actions(self, ids):
        steps = []
        for node_id in ids:
            action = find_node(self.doc, node_id)
            for widget in iter_widgets(self.doc):
                command = remove_action_ref_command(self.doc, widget.id, action.name)
                if command is not None:
                    steps.append(command)
        steps.append(Delete(ids))
        self.history.execute(Compound(steps))

    def copy_selection(self):
        self.clipboard = []
        if self.doc is None:
            return
        for node_id in self._ids():
            node = find_node(self.doc, node_id)
            if isinstance(node, Widget) and node is not self.doc.root:
                self.clipboard.append(clone_widget(self.doc, node))
        if self.clipboard:
            self._hint(f"Copied {len(self.clipboard)}. Select a widget or a layout and paste: it goes right after, inside the same layout.")

    def cut_selection(self):
        self.copy_selection()
        if self.clipboard:
            self.delete_selection()

    def paste_selection(self):
        """Paste goes into the layout. There is never a break-layout step (pain 3)."""
        if self.doc is None or self.history is None or not self.clipboard:
            return
        anchor = self._ids()
        pasted = []
        for widget in self.clipboard:
            cloned = clone_widget(self.doc, widget)
            command = insert_near(self.doc, anchor, cloned)
            if command is None:
                continue
            self.history.execute(command)
            pasted.append(cloned.id)
            anchor = [cloned.id]
        if pasted:
            self._select(pasted)

    def duplicate_selection(self):
        if self.doc is None:
            return
        made = []
        for node_id in self._ids():
            item = resolve_layout_item(self.doc, node_id)
            if item is None:
                continue
            command = duplicate_item(self.doc, item.id)
            if command is not None:
                self.history.execute(command)
                made.append(command.item.body[0].id)
        if made:
            self._select(made)

    def insert_entry(self, entry):
        if self.doc is None or self.history is None:
            return
        content = content_for(self.doc, entry)
        command = insert_near(self.doc, self._ids(), content)
        if command is None:
            self._hint("Select a layout or a widget inside one first.")
            return
        self.history.execute(command)
        self._select([content.id])
        self.outline.setFocus()

    def open_quick_insert(self):
        if self.doc is None:
            return
        where = "Goes at the end of the form."
        ids = self._ids()
        if ids:
            node = find_node(self.doc, ids[0])
            name = getattr(node, "object_name", "") or getattr(node, "name", "")
            if isinstance(node, Layout) or (isinstance(node, Widget) and widget_layout(node) is not None):
                where = f"Goes inside {name}, in its next free slot."
            else:
                where = f"Goes right after {name}."
        if self.outline.hasFocus() and self.outline.currentItem() is not None:
            rect = self.outline.visualItemRect(self.outline.currentItem())
            point = self.outline.viewport().mapToGlobal(QPoint(rect.left() + 24, rect.bottom() + 4))
        else:
            point = self.canvas.mapToGlobal(QPoint(self.canvas.width() // 2 - 150, 60))
        self.quick.popup_at(point, where)

    def wrap_menu(self):
        if self.doc is None or not self._wrap_targets():
            self._hint("Select one or more widgets that sit in the same layout, then wrap them.")
            return
        popover = WrapPopover(self, self._wrap)
        count = len(self._wrap_targets())
        popover.title.setText(f"Wrap {count} item{'s' if count != 1 else ''} in…")
        rect = self._selection_global_rect()
        point = rect.bottomLeft() + QPoint(0, 8) if rect is not None else self.canvas.mapToGlobal(QPoint(40, 40))
        popover.move(point)
        popover.show()
        popover.setFocus()

    def _selection_global_rect(self):
        if not self.canvas.selection:
            return None
        surface = self.canvas.primary
        rect = surface.index.rect_of.get(self.canvas.selection[0])
        if rect is None:
            return None
        view = surface.to_view(rect).toRect()
        return QRect(surface.mapToGlobal(view.topLeft()), view.size())

    def _wrap_targets(self):
        item_ids = []
        for node_id in self._ids():
            item = resolve_layout_item(self.doc, node_id)
            if item is not None:
                item_ids.append(item.id)
        if not item_ids:
            return []
        parents = {locate(self.doc, item_id)[0].id for item_id in item_ids}
        return item_ids if len(parents) == 1 else []

    def _wrap(self, container, layout_class):
        item_ids = self._wrap_targets()
        if not item_ids:
            return
        command = Wrap(item_ids, container, layout_class)
        self.history.execute(command)
        self._select([command.container.id])
        self.toast.show_message(f"Wrapped in {command.container.object_name}", "Undo", self.undo)

    def unwrap_selection(self):
        if self.doc is None:
            return
        for node_id in self._ids():
            node = find_node(self.doc, node_id)
            if isinstance(node, Widget) and widget_layout(node) is not None and node is not self.doc.root and resolve_layout_item(self.doc, node.id):
                children = [child.id for child in _contents(widget_layout(node))]
                self.history.execute(Unwrap(node.id))
                self._select(children)
                self.toast.show_message(f"Unwrapped {node.object_name}", "Undo", self.undo)
                return
        self._hint("Unwrap needs a container inside a layout, such as a group box or a nested box.")

    def remove_layout(self, owner_id):
        node = find_node(self.doc, owner_id)
        if not isinstance(node, Widget) or widget_layout(node) is None:
            return
        answer = QMessageBox.question(
            self,
            "Remove layout?",
            f"{node.object_name}'s children stay, but stop following the window size. Undo puts the layout back.",
            QMessageBox.Cancel | QMessageBox.Ok,
            QMessageBox.Cancel,
        )
        if answer != QMessageBox.Ok:
            return
        self.history.execute(RemoveLayout(node.id))

    def move_selection(self, delta):
        ids = self._ids()
        if ids:
            self.outline.move_selection(ids[0], delta)

    def escape(self):
        focus = QApplication.focusWidget()
        if isinstance(focus, QLineEdit) and self.inspector.isAncestorOf(focus):
            self.canvas.primary.setFocus()
            return
        if self.quick.isVisible():
            self.quick.close()
            return
        if self.canvas.mode != "design":
            self.set_mode("design")
            return
        self.select_parent()

    def select_parent(self):
        if self.doc is None or not self.canvas.selection:
            return
        node_id = self.canvas.selection[0]
        located = locate(self.doc, node_id)
        if located is None:
            return
        parent = located[0]
        if parent.__class__.__name__ == "LayoutItem":
            located = locate(self.doc, parent.id)
            parent = located[0] if located else None
        if isinstance(parent, Layout):
            for widget in iter_widgets(self.doc):
                if widget_layout(widget) is parent:
                    self._select([widget.id])
                    return
            self._select([parent.id])
            return
        if getattr(parent, "id", None):
            self._select([parent.id])

    def rename_selection(self):
        if self.outline.hasFocus() and self.outline.currentItem() is not None:
            self.outline.editItem(self.outline.currentItem(), 0)
            return
        self.inspector.focus_name()

    def edit_text(self, node_id):
        """F2 or double-click on the canvas: edit the visible text in place."""
        node = find_node(self.doc, node_id) if self.doc else None
        if not isinstance(node, Widget):
            return
        prop_name = next((name for name in TEXT_PROPS if get_property(node, name) is not None), None)
        if prop_name is None:
            prop_name = {"QLineEdit": "placeholderText", "QGroupBox": "title"}.get(node.class_name)
            widget = self.canvas.primary.realization.widgets.get(node.id)
            if prop_name is None and widget is not None and widget.metaObject().indexOfProperty("text") >= 0:
                prop_name = "text"
        if prop_name is None:
            self.rename_selection()
            return
        surface = self.canvas.primary
        if surface.index_dirty:
            surface.rebuild_index()
        rect = surface.index.rect_of.get(node.id)
        if rect is None:
            return
        current_prop = get_property(node, prop_name)
        text = current_prop.body.text if current_prop is not None else ""
        view = surface.to_view(rect)
        if view.height() > 40:
            view.setHeight(28)
        view.setWidth(max(view.width(), 140))

        def commit(value, node_id=node.id, prop_name=prop_name):
            if value != text:
                self.history.execute(SetProperty(node_id, prop_name, prop_string(prop_name, value)))

        surface.editor.open(view, text, commit, prop_name)
        self._hint(f"Editing {prop_name}. Enter to keep, Esc to cancel.")

    def _context_menu(self, global_pos):
        if self.doc is None:
            return
        menu = QMenu(self)
        tokens = current()
        menu.addAction(self.a["edit_text"])
        menu.addAction(self.a["rename"])
        menu.addAction(self.a["insert"])
        menu.addSeparator()
        wrap = menu.addMenu(icon("wrap", tokens.muted), "Wrap in")
        for words, container, layout_class, glyph in WRAPS:
            wrap.addAction(icon(glyph, tokens.layout if container == "QWidget" else tokens.muted), words, lambda c=container, lay=layout_class: self._wrap(c, lay))
        wrap.setEnabled(bool(self._wrap_targets()))
        menu.addAction(self.a["unwrap"])
        ids = self._ids()
        node = find_node(self.doc, ids[0]) if ids else None
        if isinstance(node, Widget) and resolve_layout_item(self.doc, node.id) is not None:
            size = menu.addMenu("Size")
            default = class_default(self.doc, node.class_name)
            for axis, word in (("h", "Width"), ("v", "Height")):
                for mode in ("hug", "fill"):
                    size.addAction(f"{word}: {sizing.WORDS[mode]}", lambda a=axis, m=mode, n=node: self._size(n, a, m, default))
        menu.addSeparator()
        for key in ("cut", "copy", "paste", "duplicate", "delete"):
            menu.addAction(self.a[key])
        menu.addSeparator()
        menu.addAction(self.a["parent"])
        menu.exec(global_pos)

    def _size(self, node, axis, mode, default):
        command = sizing.set_axis(node, axis, mode, default)
        if command is not None:
            self.history.execute(command)

    def _reset_tabs(self):
        if self.history is not None:
            self.history.execute(SetTabStops(None))

    def keyPressEvent(self, event):
        surface_focus = QApplication.focusWidget() in (self.canvas.primary, self.canvas.secondary)
        if surface_focus and event.key() in (Qt.Key_Up, Qt.Key_Down, Qt.Key_Left, Qt.Key_Right):
            self._walk_siblings(1 if event.key() in (Qt.Key_Down, Qt.Key_Right) else -1)
            return
        if surface_focus and event.key() in (Qt.Key_Return, Qt.Key_Enter) and self.canvas.selection:
            node = find_node(self.doc, self.canvas.selection[0])
            layout = widget_layout(node) if isinstance(node, Widget) else node if isinstance(node, Layout) else None
            children = _contents(layout) if layout is not None else []
            if children:
                self._select([children[0].id])
            return
        super().keyPressEvent(event)

    def _walk_siblings(self, delta):
        if not self.canvas.selection:
            return
        item = resolve_layout_item(self.doc, self.canvas.selection[0])
        if item is None:
            return
        layout = locate(self.doc, item.id)[0]
        items = layout_items(layout)
        if layout.class_name in ("QFormLayout", "QGridLayout"):
            items = sorted(items, key=lambda it: (int(it.attrib.get("row", "0") or 0), int(it.attrib.get("column", "0") or 0)))
        position = items.index(item) + delta
        if 0 <= position < len(items):
            content = items[position].body[0] if items[position].body else None
            if content is not None and hasattr(content, "id"):
                self._select([content.id])

    # ------------------------------------------------------------------ files
    def save(self):
        if self.doc is None:
            return
        if not self.path:
            self.save_as()
            return
        self._write(self.path)
        remember_file(self.path)

    def save_as(self):
        if self.doc is None:
            return
        suggestion = self.path or f"{form_class_name(self.doc).lower()}.ui"
        path, _selected = QFileDialog.getSaveFileName(self, "Save form", suggestion, "Qt forms (*.ui)")
        if not path:
            return
        if not path.endswith(".ui"):
            path += ".ui"
        self.path = path
        self.inspector.path = path
        self._write(path)
        remember_file(path)

    def _write(self, path):
        started = time.perf_counter()
        save_path(self.doc, path)
        ui_path = Path(path).with_name("ui_" + Path(path).stem + ".py")
        ui_path.write_text(generate_ui(self.doc, Path(path).name), encoding="utf-8")
        self.last_save = (time.perf_counter() - started) * 1000
        log_sample("save", self.last_save, path)
        self.history.mark_clean()
        self.saved_note = f"Saved · {ui_path.name} written"
        self.perf_label.setText(f"save {self.last_save:.1f} ms")
        self._refresh_chrome()

    def create_window_class(self):
        if self.doc is None:
            return
        if not self.path:
            QMessageBox.information(self, "Save first", "Save the .ui file before creating the window class.")
            return
        stem = Path(self.path).stem
        destination = Path(self.path).with_name(stem + "_window.py")
        if destination.exists():
            self.toast.show_message(f"{destination.name} already exists and was left untouched.")
            return
        from spikes.form_builder.generate import _py_name

        class_name = _py_name(form_class_name(self.doc))
        base = _base_class(self.doc.root.class_name)
        destination.write_text(
            "\n".join(
                [
                    "from PySide6.QtWidgets import " + base,
                    "",
                    "from ui_" + stem + " import Ui_" + class_name,
                    "",
                    "",
                    "class " + class_name + "Window(" + base + "):",
                    "    def __init__(self):",
                    "        super().__init__()",
                    "        self.ui = Ui_" + class_name + "()",
                    "        self.ui.setupUi(self)",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        self.toast.show_message(f"Created {destination.name}. It is yours; saves never touch it.")

    def preview(self):
        if self.doc is None:
            return
        from spikes.form_builder.generate import _py_name

        try:
            folder = Path(tempfile.mkdtemp(prefix="cbcs_form_"))
            module_path = folder / "ui_preview.py"
            module_path.write_text(generate_ui(self.doc, "preview.ui"), encoding="utf-8")
            spec = importlib.util.spec_from_file_location("cbcs_ui_preview", module_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            ui_class = getattr(module, "Ui_" + _py_name(form_class_name(self.doc)))
            widgets = __import__("PySide6.QtWidgets", fromlist=[_base_class(self.doc.root.class_name)])
            window = getattr(widgets, _base_class(self.doc.root.class_name))()
            ui = ui_class()
            ui.setupUi(window)
        except Exception as exc:  # noqa: BLE001 - show the error, keep the editor alive
            self.toast.show_message(f"Preview failed: {type(exc).__name__}: {exc}", ms=6000)
            return
        window.setWindowTitle("Preview — " + (window.windowTitle() or form_class_name(self.doc)))
        window.show()
        self.previews.append(window)


def _contents(layout):
    if layout is None:
        return []
    return [item.body[0] for item in layout_items(layout) if item.body and isinstance(item.body[0], (Widget, Layout, Spacer))]


def _base_class(class_name: str) -> str:
    if class_name == "QMainWindow":
        return "QMainWindow"
    if class_name == "QDialog":
        return "QDialog"
    return "QWidget"
