"""Start screen and the build-from-table dialog."""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QRectF, QSettings, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGraphicsScene,
    QGraphicsView,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from spikes.form_builder.icons import icon, paint_glyph, pixmap
from spikes.form_builder.kit import Card, kbd, label, overline, qcolor
from spikes.form_builder.mapping import list_tables, plan_table
from spikes.form_builder.model import blank_widget, make_layout
from spikes.form_builder.templates import (
    blank_main_window,
    data_entry,
    dialog_buttons,
    from_columns,
    list_detail,
    table_search,
)
from spikes.form_builder.theme import current, runtime_font, runtime_palette

WIDGET_CHOICES = [
    ("QLineEdit", "Line edit"),
    ("QPlainTextEdit", "Plain text"),
    ("QSpinBox", "Whole number"),
    ("QDoubleSpinBox", "Decimal number"),
    ("QCheckBox", "Check box"),
    ("QDateEdit", "Date"),
    ("QDateTimeEdit", "Date and time"),
    ("QComboBox", "Drop-down"),
]


# ------------------------------------------------------------------ thumbnails
def _bar(p, x, y, w, h, color, alpha=255, radius=2.5):
    p.setPen(Qt.NoPen)
    p.setBrush(qcolor(color, alpha))
    p.drawRoundedRect(QRectF(x, y, w, h), radius, radius)


def _field(p, x, y, w, h, t):
    p.setPen(QPen(QColor(t.border_strong), 1))
    p.setBrush(QColor(t.surface))
    p.drawRoundedRect(QRectF(x, y, w, h), 3, 3)


def _window(p, rect, t):
    """A tiny window card inside the thumbnail."""
    inner = QRectF(rect).adjusted(18, 14, -18, -10)
    p.setPen(QPen(QColor(t.border_strong), 1))
    p.setBrush(QColor(t.surface))
    p.drawRoundedRect(inner, 6, 6)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(t.border))
    p.drawRoundedRect(QRectF(inner.left(), inner.top(), inner.width(), 10), 6, 6)
    p.drawRect(QRectF(inner.left(), inner.top() + 5, inner.width(), 5))
    for index in range(3):
        p.setBrush(QColor(t.border_strong))
        p.drawEllipse(QRectF(inner.left() + 6 + index * 7, inner.top() + 3, 4, 4))
    return inner.adjusted(10, 18, -10, -8)


def thumb_data_entry(p, rect, t):
    body = _window(p, rect, t)
    row_h = min(12, body.height() / 5)
    for index in range(3):
        y = body.top() + index * (row_h + 6)
        _bar(p, body.left(), y + row_h / 2 - 2, body.width() * 0.22, 4, t.faint, 160)
        _field(p, body.left() + body.width() * 0.3, y, body.width() * 0.7, row_h, t)
    y = body.bottom() - row_h
    _bar(p, body.right() - 64, y, 30, row_h, t.border_strong, 255, 3)
    _bar(p, body.right() - 30, y, 30, row_h, t.accent, 255, 3)


def thumb_list_detail(p, rect, t):
    body = _window(p, rect, t)
    split = body.left() + body.width() * 0.36
    _field(p, body.left(), body.top(), split - body.left() - 5, body.height(), t)
    for index in range(4):
        _bar(p, body.left() + 5, body.top() + 6 + index * 9, (split - body.left()) * 0.6, 4, t.accent if index == 1 else t.faint, 200 if index == 1 else 120)
    for index in range(3):
        y = body.top() + index * 16
        _bar(p, split + 4, y + 4, body.width() * 0.14, 4, t.faint, 160)
        _field(p, split + 4 + body.width() * 0.18, y, body.right() - split - 8 - body.width() * 0.18, 11, t)


def thumb_table(p, rect, t):
    body = _window(p, rect, t)
    _field(p, body.left(), body.top(), body.width() * 0.55, 11, t)
    paint_glyph(p, "search", QRectF(body.left() + 2, body.top() + 1.5, 8, 8), t.faint)
    grid = QRectF(body.left(), body.top() + 17, body.width(), body.height() - 17)
    _field(p, grid.left(), grid.top(), grid.width(), grid.height(), t)
    p.setPen(QPen(QColor(t.border), 1))
    rows = 4
    for index in range(1, rows):
        y = grid.top() + index * grid.height() / rows
        p.drawLine(grid.left(), y, grid.right(), y)
    for index in (1, 2):
        x = grid.left() + index * grid.width() / 3
        p.drawLine(x, grid.top(), x, grid.bottom())
    _bar(p, grid.left() + 1, grid.top() + 1, grid.width() - 2, grid.height() / rows - 1, t.accent, 30, 2)


def thumb_dialog(p, rect, t):
    body = _window(p, QRectF(rect).adjusted(30, 8, -30, 0), t)
    _bar(p, body.left(), body.top() + 4, body.width() * 0.2, 4, t.faint, 160)
    _field(p, body.left() + body.width() * 0.26, body.top(), body.width() * 0.74, 12, t)
    y = body.bottom() - 12
    _bar(p, body.right() - 58, y, 27, 12, t.border_strong, 255, 3)
    _bar(p, body.right() - 27, y, 27, 12, t.accent, 255, 3)


def thumb_blank(p, rect, t):
    body = _window(p, rect, t)
    pen = QPen(qcolor(t.accent, 150), 1, Qt.DashLine)
    pen.setDashPattern([3, 3])
    p.setPen(pen)
    p.setBrush(qcolor(t.accent, 14))
    p.drawRoundedRect(body, 4, 4)
    paint_glyph(p, "plus", QRectF(body.center().x() - 7, body.center().y() - 7, 14, 14), t.accent)


def thumb_main_window(p, rect, t):
    body = _window(p, rect, t)
    _bar(p, body.left() - 10, body.top() - 8, body.width() + 20, 1, t.border, 255, 0)
    for index, width in enumerate((14, 14, 18)):
        _bar(p, body.left() + index * 22, body.top() - 5, width, 4, t.faint, 170)
    _bar(p, body.left() - 10, body.top() + 3, body.width() + 20, 1, t.border, 255, 0)
    for index in range(4):
        _bar(p, body.left() + index * 12, body.top() + 6, 8, 8, t.border_strong, 255, 2)
    _field(p, body.left(), body.top() + 19, body.width(), body.height() - 26, t)
    _bar(p, body.left() - 10, body.bottom() - 2, body.width() + 20, 1, t.border, 255, 0)


def thumb_dialog_blank(p, rect, t):
    body = _window(p, QRectF(rect).adjusted(30, 8, -30, 0), t)
    pen = QPen(qcolor(t.accent, 150), 1, Qt.DashLine)
    pen.setDashPattern([3, 3])
    p.setPen(pen)
    p.setBrush(qcolor(t.accent, 14))
    p.drawRoundedRect(body.adjusted(0, 0, 0, -16), 4, 4)
    _bar(p, body.right() - 27, body.bottom() - 11, 27, 11, t.accent, 255, 3)


def thumb_table_flow(p, rect, t):
    r = QRectF(rect)
    cy = r.center().y()
    paint_glyph(p, "database", QRectF(r.left() + 26, cy - 22, 44, 44), t.accent)
    p.setPen(QPen(qcolor(t.faint, 200), 1.5, Qt.DashLine))
    p.drawLine(r.left() + 82, cy, r.left() + 122, cy)
    paint_glyph(p, "chevron-right", QRectF(r.left() + 116, cy - 7, 14, 14), t.faint)
    body = QRectF(r.left() + 140, r.top() + 14, r.width() - 160, r.height() - 28)
    p.setPen(QPen(QColor(t.border_strong), 1))
    p.setBrush(QColor(t.surface))
    p.drawRoundedRect(body, 6, 6)
    for index in range(4):
        y = body.top() + 10 + index * 15
        if y + 10 > body.bottom():
            break
        _bar(p, body.left() + 10, y + 3, 26, 4, t.faint, 160)
        _field(p, body.left() + 44, y, body.width() - 54, 10, t)


def thumb_open(p, rect, t):
    r = QRectF(rect)
    paint_glyph(p, "folder", QRectF(r.center().x() - 24, r.center().y() - 24, 48, 48), t.muted)


# ------------------------------------------------------------------ start screen
class StartScreen(QWidget):
    opened = Signal(object)

    def __init__(self):
        super().__init__()
        self.setObjectName("StartScreen")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        outer.addWidget(scroll)
        page = QWidget()
        page.setObjectName("StartScreen")
        scroll.setWidget(page)
        center = QHBoxLayout(page)
        center.setContentsMargins(40, 28, 40, 28)
        column_host = QWidget()
        column_host.setMaximumWidth(1160)
        center.addStretch(1)
        center.addWidget(column_host, 100)
        center.addStretch(1)
        column = QVBoxLayout(column_host)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)

        brand = QHBoxLayout()
        brand.setSpacing(8)
        mark = QLabel()
        mark.setPixmap(pixmap("design", current().accent, 18))
        brand.addWidget(mark)
        brand.addWidget(label("ChoreBoy Form Builder", "Small"))
        brand.addStretch(1)
        column.addLayout(brand)
        column.addSpacing(18)
        column.addWidget(label("What are you building?", "Hero"))
        column.addSpacing(6)
        column.addWidget(
            label(
                "Every starting point is already laid out, so it resizes with the window. "
                "Saving writes a standard .ui file and the ui_ module your code imports.",
                "Muted",
                wrap=True,
            )
        )
        column.addSpacing(24)

        body = QHBoxLayout()
        body.setSpacing(24)
        column.addLayout(body)
        main = QVBoxLayout()
        main.setSpacing(10)
        body.addLayout(main, 1)

        main.addWidget(overline("Templates"))
        grid = QGridLayout()
        grid.setSpacing(12)
        templates = (
            ("Data-entry form", "Labels, fields and OK / Cancel.", thumb_data_entry, data_entry),
            ("List and detail", "A list beside one record.", thumb_list_detail, list_detail),
            ("Table with search", "A search box above a table.", thumb_table, table_search),
            ("Dialog", "One field and OK / Cancel.", thumb_dialog, dialog_buttons),
        )
        for position, (title, text, thumb, factory) in enumerate(templates):
            card = Card(title, text, thumb, height=104)
            card.clicked.connect(lambda factory=factory: self.opened.emit(factory))
            grid.addWidget(card, 0, position)
        main.addLayout(grid)
        main.addSpacing(14)

        main.addWidget(overline("Start blank"))
        blank = QGridLayout()
        blank.setSpacing(12)
        blanks = (
            ("Widget", "An empty window with a vertical layout.", thumb_blank, blank_page),
            ("Main window", "Menu bar, toolbar, status bar.", thumb_main_window, blank_main_window),
            ("Dialog", "An empty dialog with a layout.", thumb_dialog_blank, blank_dialog),
        )
        for position, (title, text, thumb, factory) in enumerate(blanks):
            card = Card(title, text, thumb, height=78)
            card.clicked.connect(lambda factory=factory: self.opened.emit(factory))
            blank.addWidget(card, 0, position)
        blank.setColumnStretch(3, 1)
        for position in range(3):
            blank.setColumnStretch(position, 1)
        main.addLayout(blank)
        main.addSpacing(14)

        main.addWidget(overline("From what you have"))
        data_row = QHBoxLayout()
        data_row.setSpacing(12)
        table_card = Card(
            "Build a form from a table",
            "Pick a SQLite table. Each column becomes a labelled field of the right kind, with buddies and tab order set.",
            thumb_table_flow,
            glyph="database",
            height=84,
        )
        table_card.setStyleSheet(f"QFrame#Card {{ border: 1px solid {current().accent}; }}")
        table_card.clicked.connect(lambda: self.opened.emit("table"))
        open_card = Card("Open a .ui file", "Any Qt Designer form. Unknown parts are kept exactly.", thumb_open, glyph="folder", height=84)
        open_card.clicked.connect(lambda: self.opened.emit("open"))
        data_row.addWidget(table_card, 2)
        data_row.addWidget(open_card, 1)
        main.addLayout(data_row)
        main.addStretch(1)

        rail = QFrame()
        rail.setObjectName("Rail")
        rail.setFixedWidth(276)
        rail_layout = QVBoxLayout(rail)
        rail_layout.setContentsMargins(16, 16, 16, 16)
        rail_layout.setSpacing(8)
        rail_layout.addWidget(overline("Recent"))
        self.recent_host = QVBoxLayout()
        self.recent_host.setSpacing(2)
        rail_layout.addLayout(self.recent_host)
        rail_layout.addSpacing(12)
        rail_layout.addWidget(overline("Keys worth knowing"))
        for keys, words in (
            ("/", "Insert a widget"),
            ("Tab", "Nest into the box above"),
            ("⌥ ↑ ↓", "Move up or down"),
            ("F2", "Edit text or rename"),
            ("Ctrl G", "Wrap in a layout"),
            ("Esc", "Select the parent"),
        ):
            row = QHBoxLayout()
            row.setSpacing(8)
            row.addWidget(label(words, "Small"), 1)
            row.addWidget(kbd(keys))
            rail_layout.addLayout(row)
        rail_layout.addStretch(1)
        body.addWidget(rail, 0, Qt.AlignTop)
        self.refresh_recent()

    def refresh_recent(self):
        while self.recent_host.count():
            item = self.recent_host.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        paths = [path for path in recent_files() if Path(path).exists()][:6]
        if not paths:
            empty = label("Forms you open or save show up here.", "Faint", wrap=True)
            self.recent_host.addWidget(empty)
            return
        for path in paths:
            button = QPushButton(f"{Path(path).name}   ·   {Path(path).parent.name}")
            button.setObjectName("Ghost")
            button.setIcon(icon("file", current().muted))
            button.setToolTip(path)
            button.setStyleSheet("text-align: left; padding-left: 6px;")
            button.clicked.connect(lambda _checked=False, path=path: self.opened.emit(("path", path)))
            self.recent_host.addWidget(button)


def recent_files() -> list[str]:
    settings = QSettings("ChoreBoy", "FormBuilder")
    value = settings.value("recent", [])
    if isinstance(value, str):
        return [value]
    return list(value or [])


def remember_file(path: str) -> None:
    settings = QSettings("ChoreBoy", "FormBuilder")
    paths = [entry for entry in recent_files() if entry != path]
    settings.setValue("recent", [path] + paths[:9])


# ------------------------------------------------------------------ preview
class FormPreview(QGraphicsView):
    """A read-only preview of a document, drawn with the runtime palette."""

    def __init__(self):
        super().__init__()
        scene = QGraphicsScene(self)
        scene.setPalette(runtime_palette())
        scene.setFont(runtime_font())
        self.setScene(scene)
        self.setFrameShape(QFrame.NoFrame)
        self.setInteractive(False)
        self.setRenderHint(QPainter.Antialiasing)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.proxy = None
        self.realization = None

    def show_document(self, doc):
        from spikes.form_builder.realize import Realization

        self.scene().clear()
        self.realization = Realization()
        self.realization.connect_signals = False
        form = self.realization.build(doc)
        hint = form.sizeHint()
        form.resize(max(360, hint.width()), max(hint.height(), 120))
        self.proxy = self.scene().addWidget(form)
        self.scene().setSceneRect(self.proxy.boundingRect().adjusted(-12, -12, 12, 12))
        self._fit()

    def _fit(self):
        if self.proxy is None:
            return
        self.resetTransform()
        rect = self.scene().sceneRect()
        scale = min(self.viewport().width() / max(rect.width(), 1), self.viewport().height() / max(rect.height(), 1), 1.0)
        self.scale(scale, scale)
        self.centerOn(rect.center())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit()

    def drawBackground(self, painter, rect):
        painter.fillRect(rect, QColor(current().canvas))


# ------------------------------------------------------------------ from a table
class TableDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Build a form from a table")
        self.resize(1080, 620)
        self.plans = []
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(14)
        outer.addWidget(label("Build a form from a table", "Heading"))
        outer.addWidget(label("Choose a table, check how each column will appear, and the form is laid out for you.", "Muted"))

        source = QHBoxLayout()
        source.setSpacing(8)
        mark = QLabel()
        mark.setPixmap(pixmap("database", current().accent, 16))
        source.addWidget(mark)
        self.path = QLineEdit()
        self.path.setReadOnly(True)
        sample = Path(__file__).resolve().parent / "samples" / "shop.sqlite"
        if sample.exists():
            self.path.setText(str(sample))
        browse = QPushButton("Choose database…")
        browse.clicked.connect(self._browse)
        source.addWidget(self.path, 1)
        source.addWidget(browse)
        outer.addLayout(source)

        body = QHBoxLayout()
        body.setSpacing(16)
        left = QVBoxLayout()
        left.setSpacing(6)
        left.addWidget(overline("Table"))
        self.tables = QListWidget()
        self.tables.setFixedWidth(180)
        self.tables.setIconSize(QSize(16, 16))
        self.tables.currentTextChanged.connect(self._preview_table)
        left.addWidget(self.tables)
        body.addLayout(left)

        middle = QVBoxLayout()
        middle.setSpacing(6)
        middle.addWidget(overline("Columns"))
        self.mapping = QTableWidget(0, 5)
        self.mapping.setHorizontalHeaderLabels(["", "Column", "Type", "Shows as", "Label"])
        self.mapping.verticalHeader().hide()
        self.mapping.setShowGrid(False)
        self.mapping.setSelectionMode(QAbstractItemView.NoSelection)
        self.mapping.setFocusPolicy(Qt.NoFocus)
        header = self.mapping.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.resizeSection(0, 34)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        header.resizeSection(3, 172)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.mapping.verticalHeader().setDefaultSectionSize(36)
        middle.addWidget(self.mapping)
        middle.addWidget(label("Required columns get a * on their label. A foreign key becomes a drop-down.", "Faint"))
        body.addLayout(middle, 3)

        right = QVBoxLayout()
        right.setSpacing(6)
        right.addWidget(overline("Preview"))
        frame = QFrame()
        frame.setObjectName("Rail")
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(1, 1, 1, 1)
        self.preview = FormPreview()
        frame_layout.addWidget(self.preview)
        right.addWidget(frame, 1)
        body.addLayout(right, 2)
        outer.addLayout(body, 1)

        footer = QHBoxLayout()
        self.summary = label("", "Small")
        footer.addWidget(self.summary)
        footer.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        self.create = QPushButton("Create form")
        self.create.setObjectName("Primary")
        self.create.setDefault(True)
        self.create.clicked.connect(self.accept)
        footer.addWidget(cancel)
        footer.addWidget(self.create)
        outer.addLayout(footer)
        if self.path.text():
            self._load_tables()

    def _browse(self):
        path, _selected = QFileDialog.getOpenFileName(self, "SQLite database", self.path.text(), "SQLite (*.sqlite *.db *.sqlite3)")
        if path:
            self.path.setText(path)
            self._load_tables()

    def _load_tables(self):
        self.tables.clear()
        path = self.path.text()
        if not path or not Path(path).exists():
            return
        with sqlite3.connect(path) as connection:
            for name in list_tables(connection):
                count = len(connection.execute(f'PRAGMA table_info("{name}")').fetchall())
                item = QListWidgetItem(icon("QTableWidget", current().muted), f"{name}")
                item.setToolTip(f"{count} columns")
                item.setData(Qt.UserRole, name)
                self.tables.addItem(item)
        if self.tables.count():
            self.tables.setCurrentRow(0)

    @property
    def table_name(self) -> str:
        item = self.tables.currentItem()
        return item.data(Qt.UserRole) if item is not None else ""

    def _preview_table(self, _text):
        table = self.table_name
        self.mapping.setRowCount(0)
        path = self.path.text()
        if not table or not path or not Path(path).exists():
            return
        with sqlite3.connect(path) as connection:
            self.plans = plan_table(connection, table)
        self.mapping.setRowCount(len(self.plans))
        for row, plan in enumerate(self.plans):
            include = QCheckBox()
            include.setChecked(plan.name != "id")
            include.toggled.connect(lambda _on: self._refresh())
            holder = QWidget()
            holder_layout = QHBoxLayout(holder)
            holder_layout.setContentsMargins(10, 0, 0, 0)
            holder_layout.addWidget(include)
            self.mapping.setCellWidget(row, 0, holder)
            name = QTableWidgetItem(plan.name + (" *" if plan.required_marker else ""))
            name.setFlags(Qt.ItemIsEnabled)
            self.mapping.setItem(row, 1, name)
            kind = QTableWidgetItem(plan.declared_type or "-")
            kind.setFlags(Qt.ItemIsEnabled)
            kind.setForeground(QColor(current().faint))
            self.mapping.setItem(row, 2, kind)
            combo = QComboBox()
            for class_name, words in WIDGET_CHOICES:
                combo.addItem(icon(class_name, current().muted), words, class_name)
            combo.setCurrentIndex(max(0, combo.findData(plan.widget)))
            combo.currentIndexChanged.connect(lambda _index: self._refresh())
            self.mapping.setCellWidget(row, 3, combo)
            caption = QLineEdit(plan.name.replace("_", " ").capitalize())
            caption.editingFinished.connect(self._refresh)
            self.mapping.setCellWidget(row, 4, caption)
        self._refresh()

    def _chosen(self):
        plans = []
        labels = {}
        for row, plan in enumerate(self.plans):
            holder = self.mapping.cellWidget(row, 0)
            include = holder.findChild(QCheckBox) if holder is not None else None
            if include is None or not include.isChecked():
                continue
            combo = self.mapping.cellWidget(row, 3)
            caption = self.mapping.cellWidget(row, 4)
            plans.append(replace(plan, widget=combo.currentData()))
            labels[plan.name] = caption.text().strip()
        return plans, labels

    def _refresh(self):
        plans, labels = self._chosen()
        count = len(plans)
        self.create.setText(f"Create form with {count} field{'s' if count != 1 else ''}")
        self.create.setEnabled(count > 0)
        self.summary.setText(f"{self.table_name}: {count} of {len(self.plans)} columns")
        if self.table_name:
            self.preview.show_document(from_columns(self.table_name, plans, labels))

    def document(self):
        plans, labels = self._chosen()
        return from_columns(self.table_name, plans, labels)


def blank_page():
    doc = blank_widget("QWidget", "Form")
    doc.root.body.append(make_layout(doc, "QVBoxLayout", "verticalLayout"))
    return doc


def blank_dialog():
    doc = blank_widget("QDialog", "Dialog")
    doc.root.body.append(make_layout(doc, "QVBoxLayout", "verticalLayout"))
    return doc
