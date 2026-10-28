"""The New form tab. A centred column, then cards, then recent forms."""

from __future__ import annotations

import os
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from app.qt.QtCore import Qt, Signal
from app.qt.QtGui import (
    QColor,
    QFont,
    QKeyEvent,
    QMouseEvent,
    QPaintEvent,
    QPainter,
    QPalette,
    QPen,
)
from app.qt.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.qt.qt_compat import enum_value

from app.features.form_builder.engine.project.fs import OsFileSystem
from app.features.form_builder.engine.project.names import (
    creation_caption,
    name_row_reason,
    unique_form_stem,
)
from app.features.form_builder.engine.project.recents import EMPTY_RECENT_TEXT
from app.features.form_builder.engine.project.templates import (
    GROUP_BLANK,
    GROUP_FROM_EXISTING,
    GROUP_TEMPLATES,
    FormTemplate,
    template_catalog,
    template_for,
)
from app.features.form_builder.qtside.start.cards import CARD_WIDTH, StartCard
from app.features.form_builder.qtside.start.wizard import WIZARD_CARD, WIZARD_KEY

from app.features.form_builder.qtside.theme.chrome import FormChrome

_GROUP_TITLES = (
    (GROUP_TEMPLATES, "Templates"),
    (GROUP_BLANK, "Start blank"),
    (GROUP_FROM_EXISTING, "From what you have"),
)
_COLUMN_MAX = 960
_CARD_GAP = 12


def _catalog() -> Tuple[FormTemplate, ...]:
    """Engine cards, with the Wizard card after Dialog (R3-121)."""
    found = []
    for spec in template_catalog():
        found.append(spec)
        if spec.key == "dialog":
            found.append(WIZARD_CARD)
    return tuple(found)


def _template_for(key: str):  # type: ignore[no-untyped-def]
    if key == WIZARD_KEY:
        return WIZARD_CARD
    return template_for(key)


class NewFormPanel(QWidget):
    """Name row, template cards, and the recent-forms list."""

    create_requested = Signal(str)
    from_table_requested = Signal()
    adopt_requested = Signal()
    open_recent_requested = Signal(str)

    def __init__(
        self,
        *,
        project_root: str,
        directory: str,
        fs: OsFileSystem,
        chrome: FormChrome,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.newForm")
        self._project_root = os.path.abspath(project_root)
        self._fs = fs
        self._chrome = chrome
        self._name_touched = False
        self._adjusting = False
        self._cards: List[StartCard] = []
        self._card_by_key: Dict[str, StartCard] = {}
        self._recent_rows: List[QWidget] = []
        self._build()
        self.set_folder_choices(_default_folders(self._project_root, directory))
        self.apply_chrome(chrome)
        self._refresh_name_state()

    def apply_chrome(self, chrome: FormChrome) -> None:
        self._chrome = chrome
        self.setStyleSheet(
            "QWidget#formBuilder\\.newForm { background: %s; color: %s; }"
            "QLabel { color: %s; background: transparent; }"
            "QScrollArea#formBuilder\\.newForm\\.scroll { background: %s; border: none; }"
            "QScrollArea#formBuilder\\.newForm\\.scroll > QWidget > QWidget { background: %s; }"
            "QLineEdit { background: %s; color: %s; border: 1px solid %s; padding: 4px; }"
            "QComboBox { background: %s; color: %s; border: 1px solid %s; padding: 4px; }"
            % (
                chrome.window,
                chrome.text,
                chrome.text,
                chrome.window,
                chrome.window,
                chrome.input,
                chrome.text,
                chrome.border,
                chrome.input,
                chrome.text,
                chrome.border,
            )
        )
        self._sentence.setStyleSheet("color: %s;" % chrome.muted)
        self._caption.setStyleSheet("color: %s;" % chrome.muted)
        self._error.setStyleSheet("color: %s;" % chrome.error)
        self._status.setStyleSheet("color: %s;" % chrome.muted)
        self._empty.setStyleSheet("color: %s;" % chrome.faint)
        self._fill_page(chrome.window)
        for label in self._group_labels:
            label.setStyleSheet("color: %s; font-weight: 600;" % chrome.text)
        for card in self._cards:
            card.set_chrome(chrome)
        self._paint_recent_rows()

    def focus_name(self) -> None:
        self._name.setFocus()
        self._name.selectAll()

    def focus_card(self, key: str) -> None:
        """Window-kind rows (UX-CAT-015): the card is focused and the name row holds a free name."""
        card = self._card_by_key.get(key)
        if not self._name_touched:
            self._apply_default_name()
        if card is not None:
            card.setFocus()

    def set_directory(self, directory: Optional[str]) -> None:
        if not directory:
            return
        absolute = os.path.abspath(directory)
        choices = list(self.folder_choices())
        if not any(path == absolute for _display, path in choices):
            choices.append((_display_for(self._project_root, absolute), absolute))
        self.set_folder_choices(tuple(choices), selected=absolute)

    def set_folder_choices(
        self,
        choices: Sequence[Tuple[str, str]],
        selected: Optional[str] = None,
    ) -> None:
        self._adjusting = True
        self._folder.clear()
        for display, path in choices:
            self._folder.addItem(display, path)
        if selected:
            index = self._index_for(os.path.abspath(selected))
            if index >= 0:
                self._folder.setCurrentIndex(index)
        self._adjusting = False
        if not self._name_touched:
            self._apply_default_name()
        else:
            self._refresh_name_state()

    def folder_choices(self) -> Tuple[Tuple[str, str], ...]:
        found = []
        for index in range(self._folder.count()):
            found.append((self._folder.itemText(index), str(self._folder.itemData(index))))
        return tuple(found)

    def directory(self) -> str:
        data = self._folder.currentData()
        if not data:
            return os.path.join(self._project_root, "forms")
        return str(data)

    def folder_display(self) -> str:
        text = self._folder.currentText()
        if text:
            return text
        if os.path.abspath(self.directory()) == self._project_root:
            return "(project root)"
        return "forms/"

    def stem(self) -> str:
        return self._name.text()

    def set_stem(self, stem: str) -> None:
        self._name_touched = True
        self._adjusting = True
        self._name.setText(stem)
        self._adjusting = False
        self._refresh_name_state()

    def name_reason(self) -> Optional[str]:
        return name_row_reason(self.stem(), folder=self.directory(), fs=self._fs)

    def show_status(self, text: str) -> None:
        self._status.setText(text)
        self._status.setVisible(bool(text))

    def set_recents(self, entries: Sequence[Tuple[str, str, str]]) -> None:
        """``entries`` is ``(file name, folder, relative path)``."""
        while self._recent_list.count():
            item = self._recent_list.takeAt(0)
            widget = item.widget()
            if widget is not None and widget is not self._empty:
                widget.setParent(None)
                widget.deleteLater()
        self._recent_rows = []
        self._empty.setVisible(not entries)
        if self._empty.parent() is not self._recent_host:
            self._empty.setParent(self._recent_host)
        if self._recent_list.indexOf(self._empty) < 0:
            self._recent_list.addWidget(self._empty)
        for name, folder, relative in entries:
            row = _RecentRow(name, folder, relative, self.open_recent_requested.emit, self._recent_host)
            self._recent_list.addWidget(row)
            self._recent_rows.append(row)
        self._paint_recent_rows()

    def card(self, key: str) -> StartCard:
        return self._card_by_key[key]

    def columns(self) -> int:
        width = self._column.width()
        if width <= 0:
            width = _COLUMN_MAX
        return max(1, min(4, (width + _CARD_GAP) // (CARD_WIDTH + _CARD_GAP)))

    def move_card(self, key: str, dx: int, dy: int) -> None:
        rows = self._card_rows()
        found = None
        for row_index, row in enumerate(rows):
            for col_index, card in enumerate(row):
                if card.key == key:
                    found = (row_index, col_index)
                    break
            if found is not None:
                break
        if found is None:
            return
        row_index, col_index = found
        if dx:
            group = self._group_of(key)
            flat = []
            for row in rows:
                if row and self._group_of(row[0].key) == group:
                    flat.extend(row)
            index = next(pos for pos, card in enumerate(flat) if card.key == key)
            step = 1 if dx > 0 else -1
            cursor = index + step
            while 0 <= cursor < len(flat):
                if flat[cursor].isEnabled():
                    flat[cursor].setFocus()
                    return
                cursor += step
            return
        step = 1 if dy > 0 else -1
        cursor_row = row_index + step
        while 0 <= cursor_row < len(rows):
            row = rows[cursor_row]
            col = min(col_index, len(row) - 1)
            if row[col].isEnabled():
                row[col].setFocus()
                return
            cursor_row += step

    def _group_of(self, key: str) -> str:
        spec = _template_for(key)
        if spec is None:
            return ""
        return spec.group

    def _card_rows(self) -> List[List[StartCard]]:
        columns = max(1, self.columns())
        rows: List[List[StartCard]] = []
        for group, _title in _GROUP_TITLES:
            cards = []
            for card in self._cards:
                spec = _template_for(card.key)
                if spec is not None and spec.group == group:
                    cards.append(card)
            for start in range(0, len(cards), columns):
                chunk = cards[start:start + columns]
                if chunk:
                    rows.append(chunk)
        return rows

    def resizeEvent(self, event: object) -> None:  # type: ignore[override]
        super().resizeEvent(event)  # type: ignore[arg-type]
        self._fit_column()
        self._reflow()

    def _fill_page(self, color: str) -> None:
        paint = QColor(color)
        for widget in (self, self._scroll, self._scroll.viewport(), self._host, self._column):
            palette = widget.palette()
            palette.setColor(QPalette.Window, paint)
            widget.setPalette(palette)
            widget.setAutoFillBackground(True)

    def _fit_column(self) -> None:
        """The centred column uses the width it has, up to 960 px."""
        available = self.width() - 48
        if available < CARD_WIDTH:
            available = CARD_WIDTH
        target = min(_COLUMN_MAX, available)
        if self._column.width() == target and self._column.maximumWidth() == target:
            return
        self._column.setFixedWidth(target)

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(self)
        scroll.setObjectName("formBuilder.newForm.scroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        outer.addWidget(scroll)
        self._scroll = scroll
        host = QWidget()
        host.setObjectName("formBuilder.newForm.host")
        scroll.setWidget(host)
        self._host = host
        host_layout = QHBoxLayout(host)
        host_layout.setContentsMargins(24, 32, 24, 24)
        host_layout.addStretch(1)
        self._column = QWidget(host)
        self._column.setMaximumWidth(_COLUMN_MAX)
        self._column.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        host_layout.addWidget(self._column, 1)
        host_layout.addStretch(1)
        column = QVBoxLayout(self._column)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(12)

        hero = QLabel("New form", self._column)
        hero.setObjectName("formBuilder.newForm.hero")
        hero_font = hero.font()
        hero_font.setPixelSize(22)
        hero_font.setWeight(QFont.DemiBold)
        hero.setFont(hero_font)
        column.addWidget(hero)

        self._sentence = QLabel(
            "Every starting point is already laid out, so it resizes with the window.",
            self._column,
        )
        self._sentence.setObjectName("formBuilder.newForm.sentence")
        self._sentence.setWordWrap(True)
        column.addWidget(self._sentence)

        name_row = QHBoxLayout()
        self._name = QLineEdit(self._column)
        self._name.setObjectName("formBuilder.newForm.name")
        self._name.textChanged.connect(self._on_name_changed)
        name_label = QLabel("Name", self._column)
        name_label.setBuddy(self._name)
        name_row.addWidget(name_label)
        name_row.addWidget(self._name, 1)
        name_row.addWidget(QLabel("in", self._column))
        self._folder = QComboBox(self._column)
        self._folder.setObjectName("formBuilder.newForm.folder")
        self._folder.currentIndexChanged.connect(self._on_folder_changed)
        name_row.addWidget(self._folder, 1)
        column.addLayout(name_row)

        self._error = QLabel("", self._column)
        self._error.setObjectName("formBuilder.newForm.nameError")
        self._error.setWordWrap(True)
        column.addWidget(self._error)

        self._caption = QLabel("", self._column)
        self._caption.setObjectName("formBuilder.newForm.caption")
        self._caption.setWordWrap(True)
        column.addWidget(self._caption)

        self._grids: Dict[str, QWidget] = {}
        self._group_labels: List[QLabel] = []
        catalog = _catalog()
        for group, title in _GROUP_TITLES:
            label = QLabel(title, self._column)
            label.setObjectName("formBuilder.newForm.group." + group)
            self._group_labels.append(label)
            column.addWidget(label)
            grid_host = QWidget(self._column)
            grid_host.setObjectName("formBuilder.newForm.grid." + group)
            QVBoxLayout(grid_host)  # replaced on reflow by a fresh layout
            self._grids[group] = grid_host
            column.addWidget(grid_host)
            for spec in catalog:
                if spec.group != group:
                    continue
                self._add_card(spec)

        recent_title = QLabel("Recent forms", self._column)
        recent_title.setObjectName("formBuilder.newForm.recentTitle")
        self._group_labels.append(recent_title)
        column.addWidget(recent_title)
        self._recent_host = QWidget(self._column)
        self._recent_host.setObjectName("formBuilder.newForm.recent")
        self._recent_list = QVBoxLayout(self._recent_host)
        self._recent_list.setContentsMargins(0, 0, 0, 0)
        self._empty = QLabel(EMPTY_RECENT_TEXT, self._recent_host)
        self._empty.setObjectName("formBuilder.newForm.recentEmpty")
        self._recent_list.addWidget(self._empty)
        column.addWidget(self._recent_host)

        self._status = QLabel("", self._column)
        self._status.setObjectName("formBuilder.newForm.status")
        self._status.setWordWrap(True)
        self._status.setVisible(False)
        column.addWidget(self._status)
        column.addStretch(1)
        self._reflow()

    def _add_card(self, spec: FormTemplate) -> None:
        card = StartCard(spec.key, spec.title, spec.description, self._chrome, self._grids[spec.group])
        card.activated.connect(self._on_card)
        card.move_requested.connect(self.move_card)
        self._cards.append(card)
        self._card_by_key[spec.key] = card

    def _reflow(self) -> None:
        columns = self.columns()
        for group, _title in _GROUP_TITLES:
            host = self._grids[group]
            layout = host.layout()
            if not isinstance(layout, QVBoxLayout):
                continue
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget()
                if widget is None:
                    continue
                for card in self._cards:
                    if card.parent() is widget:
                        card.setParent(host)
                widget.setParent(None)
                widget.deleteLater()
            cards = []
            for card in self._cards:
                spec = _template_for(card.key)
                if spec is not None and spec.group == group:
                    cards.append(card)
            for start in range(0, len(cards), columns):
                row = QWidget(host)
                row_layout = QHBoxLayout(row)
                row_layout.setContentsMargins(0, 0, 0, 0)
                row_layout.setSpacing(_CARD_GAP)
                for card in cards[start:start + columns]:
                    card.setParent(row)
                    row_layout.addWidget(card)
                row_layout.addStretch(1)
                layout.addWidget(row)

    def _on_card(self, key: str) -> None:
        spec = _template_for(key)
        if spec is None:
            return
        if key == "from_table":
            self.from_table_requested.emit()
            return
        if key == "adopt":
            self.adopt_requested.emit()
            return
        if self.name_reason() is not None:
            return
        self.create_requested.emit(key)

    def _on_name_changed(self, _text: str) -> None:
        if self._adjusting:
            return
        self._name_touched = True
        self._refresh_name_state()

    def _on_folder_changed(self, _index: int) -> None:
        if self._adjusting:
            return
        if not self._name_touched:
            self._apply_default_name()
            return
        self._refresh_name_state()

    def _apply_default_name(self) -> None:
        stem = unique_form_stem(self.directory(), self._fs)
        self._adjusting = True
        self._name.setText(stem)
        self._adjusting = False
        self._refresh_name_state()

    def _refresh_name_state(self) -> None:
        reason = self.name_reason()
        self._error.setText(reason or "")
        self._error.setVisible(reason is not None)
        self._caption.setText(creation_caption(self.folder_display(), self.stem()))
        blocked = reason is not None
        for card in self._cards:
            spec = _template_for(card.key)
            if spec is not None and spec.creates_immediately:
                card.setEnabled(not blocked)

    def _index_for(self, absolute: str) -> int:
        for index in range(self._folder.count()):
            if os.path.abspath(str(self._folder.itemData(index))) == absolute:
                return index
        return -1

    def _paint_recent_rows(self) -> None:
        chrome = self._chrome
        for row in self._recent_rows:
            row.set_chrome(chrome)
            name = row.findChild(QLabel, "formBuilder.newForm.recentName")
            folder = row.findChild(QLabel, "formBuilder.newForm.recentFolder")
            if name is not None:
                name.setStyleSheet("color: %s;" % chrome.text)
            if folder is not None:
                folder.setStyleSheet("color: %s;" % chrome.faint)


class _RecentRow(QWidget):
    def __init__(
        self,
        name: str,
        folder: str,
        relative: str,
        open_path: Callable[[str], None],
        parent: QWidget,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.newForm.recentRow")
        self._relative = relative
        self._open_path = open_path
        self._chrome: Optional[FormChrome] = None
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAccessibleName(name)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        self._name = QLabel(name, self)
        self._name.setObjectName("formBuilder.newForm.recentName")
        self._folder = QLabel(folder, self)
        self._folder.setObjectName("formBuilder.newForm.recentFolder")
        for label in (self._name, self._folder):
            label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(self._name)
        layout.addWidget(self._folder)
        layout.addStretch(1)

    def set_chrome(self, chrome: FormChrome) -> None:
        self._chrome = chrome
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if enum_value(event.button()) == enum_value(Qt.LeftButton):
            self._open_path(self._relative)
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        key = enum_value(event.key())
        if key in (enum_value(Qt.Key_Return), enum_value(Qt.Key_Enter)):
            self._open_path(self._relative)
            event.accept()
            return
        super().keyPressEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        super().paintEvent(event)
        chrome = self._chrome
        if chrome is None or not self.hasFocus():
            return
        width = max(2, chrome.focus_width)
        painter = QPainter(self)
        pen = QPen(QColor(chrome.accent))
        pen.setWidth(width)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(width // 2, width // 2, self.width() - width, self.height() - width)
        painter.end()


def _display_for(project_root: str, folder: str) -> str:
    rel = os.path.relpath(os.path.abspath(folder), os.path.abspath(project_root))
    rel = rel.replace(os.sep, "/")
    if rel in (".", ""):
        return "(project root)"
    if not rel.endswith("/"):
        rel += "/"
    return rel


def _default_folders(project_root: str, preferred: str) -> Tuple[Tuple[str, str], ...]:
    forms = os.path.join(os.path.abspath(project_root), "forms")
    paths = [forms]
    absolute = os.path.abspath(preferred) if preferred else forms
    if absolute not in paths:
        paths.append(absolute)
    return tuple((_display_for(project_root, path), path) for path in paths)
