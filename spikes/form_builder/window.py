"""Workbench shell."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import time
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMenu,
    QMessageBox,
    QSlider,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from spikes.form_builder.canvas import Canvas, start_drag
from spikes.form_builder.catalog import CATALOG, fuzzy
from spikes.form_builder.commands import (
    Delete,
    History,
    InsertItem,
    SetTabStops,
    Unwrap,
    Wrap,
    delete_targets,
    duplicate_item,
    resolve_layout_item,
)
from spikes.form_builder.generate import generate_ui
from spikes.form_builder.inspector import Inspector, SignalsPanel
from spikes.form_builder.model import (
    Layout,
    Widget,
    clone_widget,
    find_node,
    form_class_name,
    iter_widgets,
    layout_items,
    locate,
    make_item,
    problems,
    widget_layout,
)
from spikes.form_builder.outline import Outline, QuickInsert
from spikes.form_builder.perf import log_sample
from spikes.form_builder.screens import StartScreen, TableDialog
from spikes.form_builder.theme import apply_theme
from spikes.form_builder.xmlio import load_path, save_path

WRAPS = (
    ("Vertical box", "QWidget", "QVBoxLayout"),
    ("Horizontal box", "QWidget", "QHBoxLayout"),
    ("Grid", "QWidget", "QGridLayout"),
    ("Form", "QWidget", "QFormLayout"),
    ("Group box", "QGroupBox", "QVBoxLayout"),
    ("Frame", "QFrame", "QVBoxLayout"),
)


class WidgetBox(QWidget):
    def __init__(self):
        super().__init__()
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filter widgets")
        self.list = QListWidget()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        layout.addWidget(self.filter)
        layout.addWidget(self.list)
        self.filter.textChanged.connect(self.refresh)
        self.list.mouseMoveEvent = self._drag
        self.refresh("")

    def refresh(self, text):
        self.list.clear()
        for entry in CATALOG:
            if fuzzy(text, entry.label) or fuzzy(text, entry.class_name):
                self.list.addItem(entry.label)
                self.list.item(self.list.count() - 1).setData(Qt.UserRole, entry)

    def _drag(self, event):
        item = self.list.currentItem()
        if event.buttons() & Qt.LeftButton and item is not None:
            start_drag(self.list, item.data(Qt.UserRole))
            return
        QListWidget.mouseMoveEvent(self.list, event)


class MainWindow(QMainWindow):
    def __init__(self, theme_name: str):
        super().__init__()
        self.setWindowTitle("Form builder")
        self.theme_name = theme_name
        self.doc = None
        self.history = None
        self.path = None
        self.clipboard = []
        self.previews = []
        self._syncing = False
        self.last_open = None
        self.last_edit = None
        self.last_save = None
        self.stack = QStackedWidget()
        self.start = StartScreen()
        self.start.opened.connect(self._start_choice)
        self.work = self._workbench()
        self.stack.addWidget(self.start)
        self.stack.addWidget(self.work)
        self.setCentralWidget(self.stack)
        self._menus()
        self._status()
        self.quick = QuickInsert()
        self.quick.chosen.connect(self.outline.insert_entry)

    def _workbench(self):
        self.canvas = Canvas()
        self.canvas.setObjectName("canvasHost")
        self.canvas.selection_changed.connect(self._canvas_selected)
        self.canvas.status_text.connect(self._insert_status)
        self.canvas.timed.connect(self._timed)
        self.outline = Outline()
        self.outline.selection_made.connect(self._outline_selected)
        self.box = WidgetBox()
        self.inspector = Inspector()
        self.signals = SignalsPanel()
        self.signals.hide()
        left = QWidget()
        left.setObjectName("panel")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)
        outline_label = QLabel("  Outline")
        outline_label.setObjectName("section")
        left_layout.addWidget(outline_label)
        split = QSplitter(Qt.Vertical)
        split.addWidget(self.outline)
        split.addWidget(self.box)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        left_layout.addWidget(split)
        right = QWidget()
        right.setObjectName("panel")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(self.inspector)
        right_layout.addWidget(self.signals)
        panes = QSplitter()
        panes.addWidget(left)
        panes.addWidget(self.canvas)
        panes.addWidget(right)
        panes.setStretchFactor(1, 1)
        panes.setSizes([280, 720, 300])
        host = QWidget()
        layout = QVBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._toolbar())
        layout.addWidget(panes, 1)
        return host

    def _toolbar(self):
        bar = QToolBar()
        bar.setMovable(False)
        self.mode_actions = {}
        for mode, label in (("widgets", "Widgets"), ("buddy", "Buddy"), ("tab", "Tab order"), ("signals", "Signals")):
            action = QAction(label, self)
            action.setCheckable(True)
            action.triggered.connect(lambda _checked=False, name=mode: self.set_mode(name))
            bar.addAction(action)
            self.mode_actions[mode] = action
        self.mode_actions["widgets"].setChecked(True)
        bar.addSeparator()
        reset = QAction("Reset tab order", self)
        reset.triggered.connect(self._reset_tabs)
        bar.addAction(reset)
        bar.addSeparator()
        self.zoom = QSlider(Qt.Horizontal)
        self.zoom.setRange(50, 200)
        self.zoom.setValue(100)
        self.zoom.setFixedWidth(140)
        self.zoom.valueChanged.connect(lambda value: self.canvas.set_zoom(value / 100))
        bar.addWidget(QLabel(" Zoom "))
        bar.addWidget(self.zoom)
        widths = QAction("Two widths", self)
        widths.setCheckable(True)
        widths.triggered.connect(lambda checked: self.canvas.set_two_widths(checked))
        bar.addAction(widths)
        self.width_box = QComboBox()
        self.width_box.addItems(["420", "640", "960"])
        self.width_box.setCurrentText("640")
        self.width_box.currentTextChanged.connect(lambda text: self.canvas.set_width(int(text)))
        bar.addWidget(self.width_box)
        return bar

    def _menus(self):
        file_menu = self.menuBar().addMenu("File")
        file_menu.addAction("New", self.show_start)
        file_menu.addAction("Open...", self.open_ui)
        save = file_menu.addAction("Save", self.save)
        save.setShortcut(QKeySequence.Save)
        file_menu.addAction("Save as...", self.save_as)
        file_menu.addSeparator()
        file_menu.addAction("Create window class", self.create_window_class)
        preview = file_menu.addAction("Preview", self.preview)
        preview.setShortcut(QKeySequence("Ctrl+R"))
        edit = self.menuBar().addMenu("Edit")
        undo = edit.addAction("Undo", self.undo)
        undo.setShortcut(QKeySequence.Undo)
        redo = edit.addAction("Redo", self.redo)
        redo.setShortcut(QKeySequence.Redo)
        edit.addSeparator()
        edit.addAction("Copy", self.copy_selection).setShortcut(QKeySequence.Copy)
        edit.addAction("Paste", self.paste_selection).setShortcut(QKeySequence.Paste)
        edit.addAction("Duplicate", self.duplicate_selection).setShortcut(QKeySequence("Ctrl+D"))
        edit.addAction("Delete", self.delete_selection).setShortcut(QKeySequence.Delete)
        wrap_mod = Qt.MetaModifier if sys.platform == "darwin" else Qt.ControlModifier
        edit.addAction("Wrap in...", self.wrap_menu).setShortcut(QKeySequence(wrap_mod | Qt.Key_G))
        edit.addAction("Unwrap", self.unwrap_selection).setShortcut(QKeySequence(wrap_mod | Qt.ShiftModifier | Qt.Key_G))
        edit.addAction("Select parent", self.select_parent).setShortcut(QKeySequence(Qt.Key_Escape))
        view = self.menuBar().addMenu("View")
        for name, label in (("light", "Light"), ("dark", "Dark"), ("hc-light", "High contrast light"), ("hc-dark", "High contrast dark")):
            action = view.addAction(label, lambda _checked=False, theme=name: self.set_theme(theme))
            action.setCheckable(True)
            if name == self.theme_name:
                action.setChecked(True)

    def _status(self):
        bar = QStatusBar()
        self.insert_label = QLabel("Insert into: the form")
        self.problem_label = QLabel("0 problems")
        self.perf_label = QLabel("open -   edit -   save -")
        bar.addWidget(self.insert_label, 1)
        bar.addPermanentWidget(self.problem_label)
        bar.addPermanentWidget(self.perf_label)
        self.setStatusBar(bar)

    def show_start(self):
        self.stack.setCurrentWidget(self.start)

    def _start_choice(self, choice):
        if choice == "open":
            self.open_ui()
            return
        if choice == "table":
            self.open_table()
            return
        self.load_document(choice(), None)

    def open_table(self):
        dialog = TableDialog(self)
        if dialog.exec() == QDialog.Accepted and dialog.tables.currentText():
            self.load_document(dialog.document(), None)

    def open_ui(self):
        path, _selected = QFileDialog.getOpenFileName(self, "Open form", "", "Qt forms (*.ui)")
        if path:
            self.load_document(load_path(path), path)

    def load_document(self, doc, path):
        self.doc = doc
        self.history = History(doc)
        self.history.listeners.append(self._on_edit)
        self.path = path
        self.canvas.set_document(doc, self.history)
        self.outline.set_document(doc, self.history)
        self.inspector.set_session(doc, self.history, self.canvas)
        self.signals.set_session(doc, self.history)
        self.inspector.show_selection([])
        self.stack.setCurrentWidget(self.work)
        self._refresh_status()
        title = Path(path).name if path else form_class_name(doc)
        self.setWindowTitle(title + " - Form builder")

    def _on_edit(self, command):
        self.canvas.on_command(command)
        self.outline.rebuild()
        self.inspector.show_selection(self.canvas.selection)
        if self.canvas.mode == "signals":
            self.signals.refresh()
        self._refresh_status()

    def _canvas_selected(self, ids):
        if self._syncing:
            return
        self._syncing = True
        self.outline.select_ids(ids)
        self.inspector.show_selection(ids)
        self._syncing = False
        self._refresh_status()

    def _outline_selected(self, ids):
        if self._syncing:
            return
        self._syncing = True
        self.canvas.set_selection(ids)
        self.inspector.show_selection(ids)
        self._syncing = False

    def set_mode(self, mode):
        for name, action in self.mode_actions.items():
            action.setChecked(name == mode)
        self.canvas.set_mode(mode)
        self.signals.setVisible(mode == "signals")
        self.inspector.setVisible(mode != "signals")
        if mode == "signals":
            self.signals.refresh()

    def set_theme(self, name):
        self.theme_name = name
        tokens = apply_theme(QApplication.instance(), name)
        self.canvas.set_tokens(tokens)

    def _timed(self, kind, milliseconds):
        if kind == "open":
            self.last_open = milliseconds
        elif kind == "edit":
            self.last_edit = milliseconds
        log_sample(kind, milliseconds, self.path or "")
        self._refresh_status()

    def _insert_status(self, path):
        self.insert_label.setText("Insert into: " + (path or "the form"))

    def _refresh_status(self):
        count = len(problems(self.doc)) if self.doc is not None else 0
        word = "problem" if count == 1 else "problems"
        self.problem_label.setText(f"{count} {word}")
        self.perf_label.setText("open " + _ms(self.last_open) + "   edit " + _ms(self.last_edit) + "   save " + _ms(self.last_save))

    def undo(self):
        if self.history is not None:
            self.history.undo()

    def redo(self):
        if self.history is not None:
            self.history.redo()

    def delete_selection(self):
        if self.doc is None or not self.canvas.selection:
            return
        self.history.execute(Delete(delete_targets(self.doc, self.canvas.selection)))

    def copy_selection(self):
        self.clipboard = []
        if self.doc is None:
            return
        for node_id in self.canvas.selection:
            node = find_node(self.doc, node_id)
            if isinstance(node, Widget):
                self.clipboard.append(node)

    def paste_selection(self):
        if self.doc is None or self.history is None or not self.clipboard:
            return
        parent_id, index = self._paste_slot()
        if parent_id is None:
            return
        for offset, widget in enumerate(self.clipboard):
            cloned = clone_widget(self.doc, widget)
            self.history.execute(InsertItem(parent_id, index + offset, make_item(self.doc, cloned)))

    def _paste_slot(self):
        ids = self.canvas.selection
        if not ids:
            layout = widget_layout(self.doc.root)
            if layout is None:
                return None, 0
            return layout.id, len(layout_items(layout))
        node = find_node(self.doc, ids[0])
        if isinstance(node, Layout):
            return node.id, len(layout_items(node))
        item = resolve_layout_item(self.doc, ids[0])
        if item is None:
            layout = widget_layout(self.doc.root)
            return (layout.id, len(layout_items(layout))) if layout else (None, 0)
        located = locate(self.doc, item.id)
        if located is None or not isinstance(located[0], Layout):
            return None, 0
        return located[0].id, layout_items(located[0]).index(item)

    def duplicate_selection(self):
        if self.doc is None:
            return
        for node_id in list(self.canvas.selection):
            item = resolve_layout_item(self.doc, node_id)
            if item is None:
                continue
            command = duplicate_item(self.doc, item.id)
            if command is not None:
                self.history.execute(command)

    def wrap_menu(self):
        menu = QMenu(self)
        for label, container, layout in WRAPS:
            menu.addAction(label, lambda _checked=False, c=container, lay=layout: self._wrap(c, lay))
        menu.exec(self.mapToGlobal(self.rect().center()))

    def _wrap(self, container, layout):
        if self.doc is None:
            return
        item_ids = []
        for node_id in self.canvas.selection:
            item = resolve_layout_item(self.doc, node_id)
            if item is not None:
                item_ids.append(item.id)
        if item_ids:
            self.history.execute(Wrap(item_ids, container, layout))

    def unwrap_selection(self):
        if self.doc is None:
            return
        for node_id in self.canvas.selection:
            node = find_node(self.doc, node_id)
            if isinstance(node, Widget) and widget_layout(node) is not None:
                self.history.execute(Unwrap(node.id))
                return

    def select_parent(self):
        if self.doc is None or not self.canvas.selection:
            return
        located = locate(self.doc, self.canvas.selection[0])
        if located is None:
            return
        parent = located[0]
        if isinstance(parent, Layout):
            for widget in iter_widgets(self.doc):
                layout = widget_layout(widget)
                if layout is not None and layout.id == parent.id:
                    self._select([widget.id])
                    return
        if getattr(parent, "id", None):
            self._select([parent.id])

    def _select(self, ids):
        self.canvas.set_selection(ids)
        self.outline.select_ids(ids)
        self.inspector.show_selection(ids)

    def _reset_tabs(self):
        if self.history is not None:
            self.history.execute(SetTabStops(None))

    def open_quick_insert(self):
        self.quick.popup_at(self.outline.mapToGlobal(self.outline.rect().topLeft()))

    def keyPressEvent(self, event):
        focus = QApplication.focusWidget()
        if event.text() == "/" and not isinstance(focus, (QLineEdit, QComboBox)):
            self.open_quick_insert()
            return
        super().keyPressEvent(event)

    def save(self):
        if self.doc is None:
            return
        if not self.path:
            self.save_as()
            return
        self._write(self.path)

    def save_as(self):
        if self.doc is None:
            return
        path, _selected = QFileDialog.getSaveFileName(self, "Save form", self.path or "form.ui", "Qt forms (*.ui)")
        if not path:
            return
        if not path.endswith(".ui"):
            path += ".ui"
        self.path = path
        self._write(path)

    def _write(self, path):
        started = time.perf_counter()
        save_path(self.doc, path)
        ui_path = Path(path).with_name("ui_" + Path(path).stem + ".py")
        ui_path.write_text(generate_ui(self.doc, Path(path).name), encoding="utf-8")
        self.last_save = (time.perf_counter() - started) * 1000
        log_sample("save", self.last_save, path)
        self.history.mark_clean()
        self._refresh_status()
        self.setWindowTitle(Path(path).name + " - Form builder")

    def create_window_class(self):
        if self.doc is None:
            return
        if not self.path:
            QMessageBox.information(self, "Save first", "Save the .ui file before creating the window class.")
            return
        stem = Path(self.path).stem
        destination = Path(self.path).with_name(stem + "_window.py")
        if destination.exists():
            QMessageBox.information(self, "Already exists", destination.name + " was left untouched.")
            return
        class_name = form_class_name(self.doc)
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

    def preview(self):
        if self.doc is None:
            return
        folder = Path(tempfile.mkdtemp(prefix="cbcs_form_"))
        module_path = folder / "ui_preview.py"
        module_path.write_text(generate_ui(self.doc, "preview.ui"), encoding="utf-8")
        spec = importlib.util.spec_from_file_location("cbcs_ui_preview", module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        ui_class = getattr(module, "Ui_" + form_class_name(self.doc))
        widgets = __import__("PySide6.QtWidgets", fromlist=[_base_class(self.doc.root.class_name)])
        window = getattr(widgets, _base_class(self.doc.root.class_name))()
        ui = ui_class()
        ui.setupUi(window)
        window.setWindowTitle("Preview")
        window.resize(640, 480)
        window.show()
        self.previews.append(window)


def _base_class(class_name: str) -> str:
    if class_name == "QMainWindow":
        return "QMainWindow"
    if class_name == "QDialog":
        return "QDialog"
    return "QWidget"


def _ms(value):
    if value is None:
        return "-"
    return f"{value:.1f} ms"
