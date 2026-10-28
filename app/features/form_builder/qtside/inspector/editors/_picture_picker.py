"""Picture picker grid (UX-PED-100). Thumbnails load when a cell is painted."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

from app.features.form_builder.engine.project.pictures import (
    PictureIndex,
    QrcPicture,
    file_name_of,
    index_for_document,
    is_missing,
    load_pictures,
    stored_for_file,
)
from app.features.form_builder.qtside.inspector.api import EditorHost
from app.features.form_builder.qtside.theme.chrome import FormChrome
from app.features.form_builder.qtside.visual.common import token_color
from app.qt.QtCore import QEvent, QObject, QRect, Qt
from app.qt.QtGui import QColor, QFontMetrics, QImageReader, QPainter, QPen, QPixmap
from app.qt.QtWidgets import (
    QFileDialog,
    QFrame,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

_CELL_W = 56
_CELL_H = 64
_THUMB = 48
_HEADER_H = 22
_NO_RESOURCE = (
    "This form uses no resource file yet. Pictures from files may be missing when the app is packaged."
)
_THUMBS: Dict[Tuple[str, int, int], QPixmap] = {}

OnPick = Callable[[str], None]


def form_directory(host: EditorHost) -> str:
    """The form file's directory, read from the inspector session that owns the row."""
    widget: Optional[QWidget] = host.row_widget
    while widget is not None:
        services = getattr(widget, "_services", None)
        session = getattr(services, "session", None)
        path = getattr(session, "path", "") if session is not None else ""
        if isinstance(path, str) and path:
            return os.path.dirname(os.path.abspath(path))
        widget = widget.parentWidget()
    # An unsaved form has no folder. Never guess one (the process folder is
    # not the form's); file paths are then stored absolute.
    return ""


def cached_thumbnail(disk_path: str, side: int) -> QPixmap:
    """A square thumbnail keyed by absolute path and mtime. Empty when unread."""
    if not disk_path or not os.path.isfile(disk_path):
        return QPixmap()
    try:
        mtime = os.stat(disk_path).st_mtime_ns
    except OSError:
        return QPixmap()
    key = (disk_path, mtime, side)
    found = _THUMBS.get(key)
    if found is not None:
        return found
    scaled = _read_scaled(disk_path, side)
    _THUMBS[key] = scaled
    return scaled


def _read_scaled(disk_path: str, side: int) -> QPixmap:
    """Decode at thumbnail size. A huge picture is never decoded whole for a 48 px cell."""
    reader = QImageReader(disk_path)
    size = reader.size()
    if size.isValid() and size.width() > 0 and size.height() > 0:
        if size.width() > side or size.height() > side:
            reader.setScaledSize(size.scaled(side, side, getattr(getattr(Qt, "AspectRatioMode", Qt), "KeepAspectRatio")))
    image = reader.read()
    if image.isNull():
        return QPixmap()
    if image.width() > side or image.height() > side:
        mode = getattr(getattr(Qt, "AspectRatioMode", Qt), "KeepAspectRatio")
        smooth = getattr(getattr(Qt, "TransformationMode", Qt), "SmoothTransformation")
        image = image.scaled(side, side, mode, smooth)
    return QPixmap.fromImage(image)


def _ask_file(parent: QWidget) -> str:
    name, _selected = QFileDialog.getOpenFileName(
        parent,
        "Choose a picture",
        "",
        "Images (*.png *.jpg *.jpeg *.gif *.bmp *.svg *.webp *.ico *.xpm)",
    )
    return name or ""


def _key(name: str) -> object:
    return getattr(getattr(Qt, "Key", Qt), name)


def _focus(name: str) -> object:
    return getattr(getattr(Qt, "FocusPolicy", Qt), name)


def _elide_mode(name: str) -> object:
    return getattr(getattr(Qt, "TextElideMode", Qt), name)


def _align(*names: str) -> object:
    flag = getattr(Qt, "AlignmentFlag", Qt)
    combined: object = None
    for name in names:
        value = getattr(flag, name)
        combined = value if combined is None else combined | value
    return combined


def _event(name: str) -> object:
    return getattr(getattr(QEvent, "Type", QEvent), name)


@dataclass
class _Slot:
    kind: str
    text: str
    picture: Optional[QrcPicture]
    x: int
    y: int
    w: int
    h: int
    cell_index: int


class PictureGrid(QWidget):
    """One painted grid. Cells are not widgets, so 300 pictures stay cheap to open."""

    def __init__(self, parent: QWidget, on_pick: OnPick, on_activate: OnPick) -> None:
        super().__init__(parent)
        self._on_pick = on_pick
        self._on_activate = on_activate
        self._slots: List[_Slot] = []
        self._cells: List[_Slot] = []
        self._selected = -1
        self._chrome: Optional[FormChrome] = None
        self.setObjectName("formBuilder.pictureGrid")
        self.setAccessibleName("Picture: pictures")
        self.setFocusPolicy(_focus("StrongFocus"))  # type: ignore[arg-type]
        self.setProperty("fbEnterStays", True)
        self.setMouseTracking(True)
        self._query = ""
        self._pictures: Tuple[QrcPicture, ...] = ()

    def set_tokens(self, chrome: FormChrome) -> None:
        self._chrome = chrome
        self.update()

    def set_pictures(self, pictures: Tuple[QrcPicture, ...], query: str) -> None:
        self._pictures = pictures
        self._query = query
        self._reflow()
        self._selected = 0 if self._cells else -1
        self._describe()
        self.update()

    def count(self) -> int:
        return len(self._cells)

    def selected_picture(self) -> Optional[QrcPicture]:
        if self._selected < 0 or self._selected >= len(self._cells):
            return None
        return self._cells[self._selected].picture

    def move_by(self, dx: int, dy: int) -> None:
        if not self._cells:
            return
        columns = max(1, max(self.width(), _CELL_W) // _CELL_W)
        index = 0 if self._selected < 0 else self._selected
        if dx:
            index += dx
        if dy:
            index += dy * columns
        self._selected = max(0, min(len(self._cells) - 1, index))
        self._describe()
        self._reveal()
        self.update()

    def select_path(self, stored: str) -> None:
        for slot in self._cells:
            picture = slot.picture
            if picture is not None and picture.resource_path == stored:
                self._selected = slot.cell_index
                self._describe()
                self._reveal()
                self.update()
                return

    def resizeEvent(self, event: QEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._reflow()

    def keyPressEvent(self, event: QEvent) -> None:  # noqa: N802
        key = event.key()  # type: ignore[attr-defined]
        if key == _key("Key_Left"):
            self.move_by(-1, 0)
        elif key == _key("Key_Right"):
            self.move_by(1, 0)
        elif key == _key("Key_Up"):
            self.move_by(0, -1)
        elif key == _key("Key_Down"):
            self.move_by(0, 1)
        elif key in (_key("Key_Return"), _key("Key_Enter")):
            picture = self.selected_picture()
            if picture is not None:
                self._on_activate(picture.resource_path)
        else:
            super().keyPressEvent(event)
            return
        event.accept()  # type: ignore[attr-defined]

    def mousePressEvent(self, event: QEvent) -> None:  # noqa: N802
        pos = event.position() if hasattr(event, "position") else event.pos()  # type: ignore[attr-defined]
        x, y = int(pos.x()), int(pos.y())
        for slot in self._cells:
            if QRect(slot.x, slot.y, slot.w, slot.h).contains(x, y) and slot.picture is not None:
                self._selected = slot.cell_index
                self.setFocus()
                self.update()
                self._on_pick(slot.picture.resource_path)
                event.accept()  # type: ignore[attr-defined]
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QEvent) -> None:  # noqa: N802
        picture = self._at(event)
        if picture is None:
            self.setToolTip("")
        elif is_missing(picture):
            self.setToolTip("%s\nCode Studio can't find %s." % (picture.resource_path, picture.disk_path))
        else:
            self.setToolTip(picture.resource_path)
        super().mouseMoveEvent(event)

    def _at(self, event: QEvent) -> Optional[QrcPicture]:
        pos = event.position() if hasattr(event, "position") else event.pos()  # type: ignore[attr-defined]
        x, y = int(pos.x()), int(pos.y())
        for slot in self._cells:
            if slot.picture is not None and QRect(slot.x, slot.y, slot.w, slot.h).contains(x, y):
                return slot.picture
        return None

    def _describe(self) -> None:
        picture = self.selected_picture()
        self.setAccessibleDescription("" if picture is None else picture.resource_path)

    def paintEvent(self, event: QEvent) -> None:  # noqa: N802
        chrome = self._chrome
        if chrome is None:
            return
        painter = QPainter(self)
        text = token_color(chrome.text)
        muted = token_color(chrome.muted)
        accent = token_color(chrome.accent)
        error = token_color(chrome.error)
        checker_a = token_color(chrome.fb.checker_a)
        checker_b = token_color(chrome.fb.checker_b)
        border = token_color(chrome.fb.swatch_border)
        clip = event.rect()  # type: ignore[attr-defined]
        for slot in self._slots:
            rect = QRect(slot.x, slot.y, slot.w, slot.h)
            if not rect.intersects(clip):
                continue
            if slot.kind == "header":
                painter.setPen(muted)
                painter.drawText(rect.adjusted(2, 0, -2, 0), _align("AlignVCenter", "AlignLeft"), slot.text)
                continue
            picture = slot.picture
            if picture is None:
                continue
            thumb = QRect(
                slot.x + (_CELL_W - _THUMB) // 2,
                slot.y + 2,
                _THUMB,
                _THUMB,
            )
            _paint_checker(painter, thumb, checker_a, checker_b)
            missing = is_missing(picture)
            if not missing:
                pixmap = cached_thumbnail(picture.disk_path, _THUMB)
                if not pixmap.isNull():
                    px = thumb.x() + (thumb.width() - pixmap.width()) // 2
                    py = thumb.y() + (thumb.height() - pixmap.height()) // 2
                    painter.drawPixmap(px, py, pixmap)
            painter.setPen(QPen(border))
            painter.drawRect(thumb.adjusted(0, 0, -1, -1))
            if slot.cell_index == self._selected:
                painter.setPen(QPen(accent, 2))
                painter.drawRect(rect.adjusted(1, 1, -2, -2))
            painter.setPen(error if missing else text)
            name = QFontMetrics(self.font()).elidedText(
                picture.file_name, _elide_mode("ElideMiddle"), _CELL_W - 4
            )
            painter.drawText(
                QRect(slot.x, thumb.bottom() + 1, _CELL_W, 14),
                _align("AlignHCenter", "AlignTop"),
                name,
            )
        painter.end()

    def _reflow(self) -> None:
        query = self._query.casefold().strip()
        columns = max(1, max(self.width(), _CELL_W) // _CELL_W)
        slots: List[_Slot] = []
        cells: List[_Slot] = []
        y = 0
        column = 0
        current: Optional[Tuple[str, str]] = None
        for picture in self._pictures:
            if query and query not in picture.file_name.casefold() and query not in picture.resource_path.casefold():
                continue
            group = (picture.qrc_name, picture.prefix)
            if group != current:
                if column:
                    y += _CELL_H
                    column = 0
                current = group
                label = picture.qrc_name if not picture.prefix else "%s · %s" % (picture.qrc_name, picture.prefix)
                slots.append(_Slot("header", label, None, 0, y, columns * _CELL_W, _HEADER_H, -1))
                y += _HEADER_H
            slot = _Slot("cell", picture.file_name, picture, column * _CELL_W, y, _CELL_W, _CELL_H, len(cells))
            slots.append(slot)
            cells.append(slot)
            column += 1
            if column >= columns:
                column = 0
                y += _CELL_H
        if column:
            y += _CELL_H
        self._slots = slots
        self._cells = cells
        self.setMinimumHeight(max(y, _CELL_H))
        self.updateGeometry()

    def _reveal(self) -> None:
        if self._selected < 0 or self._selected >= len(self._cells):
            return
        slot = self._cells[self._selected]
        self.scroll(0, 0)
        scroll = _enclosing_scroll(self)
        if scroll is not None:
            scroll.ensureVisible(slot.x, slot.y + slot.h // 2, 8, 8)


def _enclosing_scroll(widget: QWidget) -> Optional[QScrollArea]:
    parent = widget.parentWidget()
    while parent is not None:
        if isinstance(parent, QScrollArea):
            return parent
        parent = parent.parentWidget()
    return None


def _paint_checker(painter: QPainter, rect: QRect, first: QColor, second: QColor) -> None:
    painter.fillRect(rect, first)
    cell = 8
    row = 0
    y = rect.top()
    while y < rect.bottom():
        x = rect.left()
        column = 0
        while x < rect.right():
            if (row + column) % 2:
                painter.fillRect(QRect(x, y, cell, cell).intersected(rect), second)
            x += cell
            column += 1
        y += cell
        row += 1


class _SearchKeys(QObject):
    """Down from the search field moves onto the current picture. It does not skip it."""

    def __init__(self, picker: "PicturePicker") -> None:
        super().__init__(picker)
        self._picker = picker

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() != _event("KeyPress"):
            return False
        key = event.key()  # type: ignore[attr-defined]
        del watched
        if key == _key("Key_Down"):
            self._picker.focus_grid()
            return True
        return False


class PicturePicker(QWidget):
    """Search, resource grid, and "From a file…" (UX-PED-100)."""

    def __init__(
        self,
        parent: QWidget,
        host: EditorHost,
        on_pick: OnPick,
        *,
        on_close: Optional[Callable[[], None]] = None,
        grid_height: int = 220,
    ) -> None:
        super().__init__(parent)
        self._host = host
        self._on_pick = on_pick
        self._on_close = on_close
        self._form_dir = form_directory(host)
        self._index = PictureIndex((), (), {})
        self._locations: Tuple[str, ...] = ()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self._search = QLineEdit(self)
        self._search.setObjectName("formBuilder.pictureSearch")
        self._search.setAccessibleName("Picture: search")
        self._search.setPlaceholderText("Search pictures")
        self._search.textChanged.connect(self._search_changed)
        self._search.returnPressed.connect(self._activate_current)
        layout.addWidget(self._search)
        self._grid = PictureGrid(self, self._pick, self._activate)
        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setFocusPolicy(_focus("NoFocus"))  # type: ignore[arg-type]
        self._scroll.setWidget(self._grid)
        self._grid_height = grid_height
        policy = getattr(QSizePolicy, "Policy", QSizePolicy)
        self._scroll.setSizePolicy(policy.Expanding, policy.Preferred)
        layout.addWidget(self._scroll)
        self._issue = QLabel(self)
        self._issue.setObjectName("formBuilder.pictureIssue")
        self._issue.setWordWrap(True)
        self._issue.hide()
        layout.addWidget(self._issue)
        self._empty = QLabel(_NO_RESOURCE, self)
        self._empty.setObjectName("formBuilder.pictureNoResource")
        self._empty.setWordWrap(True)
        self._empty.setAccessibleName("Picture: no resource file")
        self._empty.hide()
        layout.addWidget(self._empty)
        self._file = QPushButton("From a file\u2026", self)
        self._file.setObjectName("formBuilder.pictureFromFile")
        self._file.setAccessibleName("Picture: from a file")
        self._file.clicked.connect(self._from_file)
        layout.addWidget(self._file)
        self._keys = _SearchKeys(self)
        self._search.installEventFilter(self._keys)
        self.set_tokens(host.chrome)
        self.reload()

    @property
    def search(self) -> QLineEdit:
        return self._search

    @property
    def grid(self) -> PictureGrid:
        return self._grid

    def set_tokens(self, chrome: FormChrome) -> None:
        self._grid.set_tokens(chrome)
        self._issue.setStyleSheet("color: %s;" % chrome.error)
        self._empty.setStyleSheet("color: %s;" % chrome.muted)

    def reload(self) -> None:
        try:
            document = self._host.document()
        except (AttributeError, RuntimeError, TypeError):
            document = None
        if document is None:
            self._index = load_pictures((), self._form_dir)
            self._locations = ()
        else:
            self._index = index_for_document(document, self._form_dir)
            from app.features.form_builder.engine.project.pictures import resource_locations

            self._locations = resource_locations(document)
        self._issue.setText(self._index.issues[0].sentence if self._index.issues else "")
        self._issue.setVisible(bool(self._index.issues))
        self._empty.setVisible(not self._locations)
        self._grid.set_pictures(self._index.pictures, self._search.text())
        has_pictures = bool(self._index.pictures)
        self._search.setVisible(has_pictures)
        self._scroll.setVisible(has_pictures)
        # A scroll area's own size hint is about one row. Size it to the grid
        # (four columns fit the popover at every scale) up to the cap.
        per_group: Dict[Tuple[str, str], int] = {}
        for picture in self._index.pictures:
            key = (picture.qrc_name, picture.prefix)
            per_group[key] = per_group.get(key, 0) + 1
        rows = sum((count + 3) // 4 for count in per_group.values())
        needed = rows * _CELL_H + len(per_group) * _HEADER_H
        self._scroll.setFixedHeight(max(_CELL_H + _HEADER_H, min(self._grid_height, needed)))

    def focus_first(self) -> None:
        """The search field, or "From a file…" when there is nothing to search."""
        if self._index.pictures:
            self._search.setFocus()
        else:
            self._file.setFocus()

    def focus_grid(self) -> None:
        if self._grid.count() == 0:
            return
        self._grid.setFocus()

    def select_path(self, stored: str) -> None:
        self._grid.select_path(stored)

    def choose(self, absolute: str) -> str:
        """Record ``absolute`` the way "From a file…" does, without the dialog."""
        stored = stored_for_file(absolute, self._form_dir, self._index)
        self._on_pick(stored)
        return stored

    def _search_changed(self, _text: str) -> None:
        self._grid.set_pictures(self._index.pictures, self._search.text())

    def _pick(self, stored: str) -> None:
        self._on_pick(stored)

    def _activate(self, stored: str) -> None:
        self._on_pick(stored)
        if self._on_close is not None:
            self._on_close()

    def _activate_current(self) -> None:
        picture = self._grid.selected_picture()
        if picture is None:
            return
        self._activate(picture.resource_path)

    def _from_file(self) -> None:
        chosen = _ask_file(self)
        if not chosen:
            return
        self.choose(chosen)
        if self._on_close is not None:
            self._on_close()


def displayed_name(stored: str, missing: bool, *, mixed: bool) -> str:
    if mixed:
        return "Mixed"
    if not stored:
        return "None"
    name = file_name_of(stored)
    if missing:
        return "%s (missing)" % name
    return name
