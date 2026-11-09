"""Picture picker grid (UX-PED-100). Thumbnails load when a cell is painted."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from app.features.form_builder.engine.project.fs import ProjectOpError
from app.features.form_builder.engine.project.picture_adopt import (
    PicturePlan,
    default_target,
    include_commands,
    plan_add,
)
from app.features.form_builder.engine.project.project_files import ProjectFileIndex
from app.features.form_builder.qtside.resources.drops import refusal
from app.features.form_builder.engine.project.pictures import (
    PictureIndex,
    ProjectPictures,
    QrcPicture,
    canon_resource,
    dialog_filter,
    file_name_of,
    is_missing,
    load_pictures,
    project_pictures,
    resource_locations,
    stored_for_file,
)
from app.features.form_builder.qtside.inspector.api import EditorHost, EditSession
from app.features.form_builder.qtside.resources import notices
from app.features.form_builder.qtside.theme.chrome import FormChrome
from app.features.form_builder.qtside.visual.common import token_color
from app.qt.QtCore import QEvent, QObject, QRect, Qt
from app.qt.QtGui import QColor, QFont, QFontMetrics, QImageReader, QPainter, QPen, QPixmap
from app.qt.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
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


def form_session(host: EditorHost) -> Optional[object]:
    """The form session behind the row, found through the inspector services on a parent widget."""
    widget: Optional[QWidget] = host.row_widget
    while widget is not None:
        services = getattr(widget, "_services", None)
        session = getattr(services, "session", None)
        path = getattr(session, "path", "") if session is not None else ""
        if isinstance(path, str) and path:
            return session
        widget = widget.parentWidget()
    return None


def form_directory(host: EditorHost) -> str:
    """The form file's directory, read from the inspector session that owns the row."""
    session = form_session(host)
    if session is not None:
        return os.path.dirname(os.path.abspath(getattr(session, "path")))
    # An unsaved form has no folder. Never guess one (the process folder is
    # not the form's); file paths are then stored absolute.
    return ""


def form_project(host: EditorHost) -> Tuple[str, str]:
    """``(form path, project root)``; the root is ``""`` for a form outside a project."""
    session = form_session(host)
    if session is None:
        return "", ""
    scope = getattr(session, "scope", None)
    root = getattr(scope, "project_root", None) if getattr(scope, "generates", False) else None
    return str(getattr(session, "path", "")), str(root or "")


def announce(host: EditorHost, sentence: str) -> None:
    """Show ``sentence`` in the form's toast, when the row sits in a form tab."""
    widget: Optional[QWidget] = host.row_widget
    while widget is not None:
        show = getattr(widget, "show_plain", None)
        if callable(show):
            show(sentence)
            return
        widget = widget.parentWidget()


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


def cell_name(metrics: QFontMetrics, file_name: str, width: int) -> str:
    """A grid cell's caption. Numbered files differ at the end ("img_012.png"),
    so a long name drops its extension first, then elides from the left."""
    if metrics.horizontalAdvance(file_name) <= width:
        return file_name
    stem = file_name.rsplit(".", 1)[0] if "." in file_name[1:] else file_name
    if metrics.horizontalAdvance(stem) <= width:
        return stem
    return metrics.elidedText(stem, _elide_mode("ElideLeft"), width)


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
        self._others: Tuple[QrcPicture, ...] = ()
        self._labels: Dict[str, str] = {}

    def set_tokens(self, chrome: FormChrome) -> None:
        self._chrome = chrome
        self.update()

    def set_pictures(self, pictures: Tuple[QrcPicture, ...], query: str) -> None:
        self.set_sections(pictures, (), query)

    def set_sections(
        self,
        mine: Tuple[QrcPicture, ...],
        others: Tuple[QrcPicture, ...],
        query: str,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        """This form's pictures, then the project's other pictures (UX-RES-001).

        The two headings show only when the project has other pictures; with
        one section a heading would name nothing. ``labels`` maps a ``.qrc``
        path to the name its group header shows.
        """
        self._pictures = mine
        self._others = others
        self._labels = dict(labels or {})
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
        index = 0 if self._selected < 0 else self._selected
        if dx:
            index = max(0, min(len(self._cells) - 1, index + dx))
        if dy and self._selected >= 0:
            index = self._row_neighbour(index, dy)
        self._selected = index
        self._describe()
        self._reveal()
        self.update()

    def _row_neighbour(self, index: int, dy: int) -> int:
        """The cell one painted row up or down, nearest in column. Group headers break rows,
        so index arithmetic would land beside the wrong cell after the first group."""
        here = self._cells[index]
        rows = sorted({slot.y for slot in self._cells})
        at = rows.index(here.y) + (1 if dy > 0 else -1)
        if at < 0 or at >= len(rows):
            return index
        row = [slot for slot in self._cells if slot.y == rows[at]]
        return min(row, key=lambda slot: abs(slot.x - here.x)).cell_index

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
        # The cells are painted, so the grid speaks for the current one: its file and place.
        if picture is None:
            self.setAccessibleName("Picture: pictures")
        else:
            self.setAccessibleName(
                "Picture: %s, %d of %d" % (picture.file_name, self._selected + 1, len(self._cells))
            )
        try:
            from app.qt.QtGui import QAccessible, QAccessibleEvent

            if QAccessible.isActive():
                QAccessible.updateAccessibility(QAccessibleEvent(self, QAccessible.Event.NameChanged))
        except (ImportError, AttributeError, TypeError, RuntimeError):
            pass

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
            if slot.kind in ("header", "section"):
                painter.setPen(muted)
                if slot.kind == "section":
                    bold = QFont(self.font())
                    bold.setBold(True)
                    painter.setFont(bold)
                painter.drawText(rect.adjusted(2, 0, -2, 0), _align("AlignVCenter", "AlignLeft"), slot.text)
                if slot.kind == "section":
                    painter.setFont(self.font())
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
            name = cell_name(QFontMetrics(self.font()), picture.file_name, _CELL_W - 4)
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
        state = {"y": 0, "column": 0}

        def visible(pictures: Tuple[QrcPicture, ...]) -> List[QrcPicture]:
            return [
                picture
                for picture in pictures
                if not query or query in picture.file_name.casefold() or query in picture.resource_path.casefold()
            ]

        def end_row() -> None:
            if state["column"]:
                state["y"] += _CELL_H
                state["column"] = 0

        def lay_out(pictures: List[QrcPicture]) -> None:
            current: Optional[Tuple[str, str]] = None
            for picture in pictures:
                group = (picture.qrc_path, picture.prefix)
                if group != current:
                    end_row()
                    current = group
                    name = self._labels.get(picture.qrc_path, picture.qrc_name)
                    label = name if not picture.prefix else "%s \u00b7 %s" % (name, picture.prefix)
                    slots.append(_Slot("header", label, None, 0, state["y"], columns * _CELL_W, _HEADER_H, -1))
                    state["y"] += _HEADER_H
                slot = _Slot(
                    "cell",
                    picture.file_name,
                    picture,
                    state["column"] * _CELL_W,
                    state["y"],
                    _CELL_W,
                    _CELL_H,
                    len(cells),
                )
                slots.append(slot)
                cells.append(slot)
                state["column"] += 1
                if state["column"] >= columns:
                    state["column"] = 0
                    state["y"] += _CELL_H

        sectioned = bool(self._others)
        for title, pictures in (
            ("THIS FORM'S PICTURES", visible(self._pictures)),
            ("OTHER PICTURES IN THIS PROJECT", visible(self._others)),
        ):
            if not pictures:
                continue
            end_row()
            if sectioned:
                slots.append(_Slot("section", title, None, 0, state["y"], columns * _CELL_W, _HEADER_H, -1))
                state["y"] += _HEADER_H
            lay_out(pictures)
        end_row()
        self._slots = slots
        self._cells = cells
        self.setMinimumHeight(max(state["y"], _CELL_H))
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


paint_checker = _paint_checker


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
    """Search, the two picture sections, and "Add picture…" (UX-PED-100, UX-RES-001, UX-RES-002).

    ``session`` is the popover's edit session. Picking a picture from another
    pictures file, or adding one, runs the include inside that session, so the
    include and the property are one undo step. Without a session (the brush
    page) the include is its own step. A form outside a project has nowhere to
    keep pictures; it keeps M4's "From a file…", which stores a path.
    """

    def __init__(
        self,
        parent: QWidget,
        host: EditorHost,
        on_pick: OnPick,
        *,
        on_close: Optional[Callable[[], None]] = None,
        grid_height: int = 220,
        session: Optional[EditSession] = None,
    ) -> None:
        super().__init__(parent)
        self._host = host
        self._on_pick = on_pick
        self._on_close = on_close
        self._session = session
        self._form_dir = form_directory(host)
        self._ui_path, self._project_root = form_project(host)
        self._files = ProjectFileIndex(self._project_root) if self._project_root else None
        self._shown = ProjectPictures(PictureIndex((), (), {}), PictureIndex((), (), {}), ())
        self._index = self._shown.mine
        self._locations: Tuple[str, ...] = ()
        self._target = ""
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
        in_project = bool(self._project_root and self._ui_path)
        self._file = QPushButton("Add picture\u2026" if in_project else "From a file\u2026", self)
        if in_project:
            self._file.setObjectName("formBuilder.pictureAdd")
            self._file.setAccessibleName("Picture: add picture")
        else:
            self._file.setObjectName("formBuilder.pictureFromFile")
            self._file.setAccessibleName("Picture: from a file")
        # Enter activates it like Space: a plain push button outside a dialog takes only Space.
        self._file.setAutoDefault(True)
        self._file.clicked.connect(self._from_file)
        layout.addWidget(self._file)
        self._target_row = QWidget(self)
        row = QHBoxLayout(self._target_row)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        self._target_caption = QLabel(self._target_row)
        self._target_caption.setObjectName("formBuilder.pictureTarget")
        self._target_caption.setWordWrap(True)
        row.addWidget(self._target_caption, 1)
        self._change = QToolButton(self._target_row)
        self._change.setObjectName("formBuilder.pictureChangeTarget")
        self._change.setText("Change")
        self._change.setAccessibleName("Picture: change pictures file")
        self._change.setPopupMode(getattr(QToolButton, "ToolButtonPopupMode", QToolButton).InstantPopup)
        self._change.setFocusPolicy(_focus("StrongFocus"))  # type: ignore[arg-type]
        self._menu = QMenu(self._change)
        self._change.setMenu(self._menu)
        row.addWidget(self._change, 0)
        self._target_row.hide()
        layout.addWidget(self._target_row)
        self._keys = _SearchKeys(self)
        self._search.installEventFilter(self._keys)
        self.setAcceptDrops(self.in_project)
        self.set_tokens(host.chrome)
        self.reload()

    @property
    def search(self) -> QLineEdit:
        return self._search

    @property
    def grid(self) -> PictureGrid:
        return self._grid

    @property
    def add_button(self) -> QPushButton:
        return self._file

    @property
    def target_caption(self) -> QLabel:
        return self._target_caption

    @property
    def in_project(self) -> bool:
        return bool(self._project_root and self._ui_path)

    def set_tokens(self, chrome: FormChrome) -> None:
        self._grid.set_tokens(chrome)
        self._issue.setStyleSheet("color: %s;" % chrome.error)
        self._empty.setStyleSheet("color: %s;" % chrome.muted)
        self._target_caption.setStyleSheet("color: %s;" % chrome.muted)

    def reload(self) -> None:
        try:
            document = self._host.document()
        except (AttributeError, RuntimeError, TypeError):
            document = None
        if document is None:
            self._locations = ()
        else:
            self._locations = resource_locations(document)
        if self._project_root and self._files is not None:
            self._shown = project_pictures(self._locations, self._form_dir, self._project_root, self._files)
        else:
            self._shown = ProjectPictures(
                load_pictures(self._locations, self._form_dir), PictureIndex((), (), {}), ()
            )
        self._index = self._shown.mine
        issues = self._index.issues + self._shown.others.issues
        self._issue.setText(issues[0].sentence if issues else "")
        self._issue.setVisible(bool(issues))
        self._empty.setVisible(not self._locations and not self.in_project)
        labels = {
            picture.qrc_path: self._qrc_label(picture.qrc_path)
            for picture in self._shown.others.pictures
        } if self._project_root else {}
        self._grid.set_sections(self._index.pictures, self._shown.others.pictures, self._search.text(), labels)
        has_pictures = bool(self._index.pictures or self._shown.others.pictures)
        self._search.setVisible(has_pictures)
        self._scroll.setVisible(has_pictures)
        # A scroll area's own size hint is about one row. Size it to the grid
        # (four columns fit the popover at every scale) up to the cap.
        per_group: Dict[Tuple[str, str], int] = {}
        for picture in self._index.pictures + self._shown.others.pictures:
            key = (picture.qrc_path, picture.prefix)
            per_group[key] = per_group.get(key, 0) + 1
        rows = sum((count + 3) // 4 for count in per_group.values())
        headings = len(per_group) + (2 if self._shown.others.pictures else 0)
        needed = rows * _CELL_H + headings * _HEADER_H
        self._scroll.setFixedHeight(max(_CELL_H + _HEADER_H, min(self._grid_height, needed)))
        self._refresh_target()

    def focus_first(self) -> None:
        """The search field, or "Add picture…" when there is nothing to search."""
        if self._index.pictures or self._shown.others.pictures:
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
        """Record ``absolute`` the way the footer button does, without the dialog."""
        if self.in_project:
            return self.add_pictures([absolute])
        stored = stored_for_file(absolute, self._form_dir, self._index)
        self._on_pick(stored)
        return stored

    def add_pictures(self, sources: Sequence[str]) -> str:
        """UX-RES-002. Returns the resource path set on the row, or ``""`` when the add was refused."""
        try:
            document = self._host.document()
            plan = plan_add(document, self._ui_path, self._project_root, sources, self._target)
        except ProjectOpError as exc:
            self._show_issue(str(exc))
            return ""
        session = self._session or self._host.begin_session(plan.label)
        try:
            session.set_label(plan.label)
            if plan.commands and not self._run(session, plan.commands):
                return ""
            stored = plan.outcome.resource_paths[0]
            self._on_pick(stored)
        finally:
            if self._session is None:
                session.close()
        notices.remember(plan.label, plan.notice)
        announce(self._host, plan.notice)
        self.reload()
        self._grid.select_path(stored)
        return stored

    def target_path(self) -> str:
        """The ``.qrc`` new pictures go into (absolute)."""
        if self._target:
            return self._target
        if not self._project_root:
            return ""
        try:
            return default_target(self._host.document(), self._ui_path, self._project_root)
        except (AttributeError, RuntimeError, TypeError):
            return ""

    def set_target(self, qrc_relative: str) -> None:
        if self._project_root and qrc_relative:
            self._target = os.path.join(self._project_root, *qrc_relative.split("/"))
        self._refresh_target()

    def _qrc_label(self, qrc_path: str) -> str:
        if not self._project_root:
            return os.path.basename(qrc_path)
        return os.path.relpath(qrc_path, self._project_root).replace(os.sep, "/")

    def _refresh_target(self) -> None:
        qrcs = self._shown.qrc_files
        # More than one pictures file: say which one gets new pictures, and let the owner change it.
        show = len(qrcs) > 1 and self.in_project
        self._target_row.setVisible(show)
        if not show:
            return
        target = self.target_path()
        self._target_caption.setText("New pictures go into %s." % self._qrc_label(target))
        self._menu.clear()
        for relative in qrcs:
            action = self._menu.addAction(relative)
            action.triggered.connect(lambda _checked=False, rel=relative: self.set_target(rel))

    def _run(self, session: EditSession, commands: Sequence[object]) -> bool:
        result = session.run(commands)  # type: ignore[arg-type]
        if isinstance(result, tuple):
            return True
        self._show_issue(str(getattr(result, "message", "") or "That change was refused."))
        return False

    def _show_issue(self, sentence: str) -> None:
        self._issue.setText(sentence)
        self._issue.show()

    def dragEnterEvent(self, event: QEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():  # type: ignore[attr-defined]
            event.acceptProposedAction()  # type: ignore[attr-defined]

    def dropEvent(self, event: QEvent) -> None:  # noqa: N802
        """UX-RES-003: picture files from the file manager are added as "Add picture…" does."""
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]  # type: ignore[attr-defined]
        wrong = refusal(paths)
        if wrong:
            self._show_issue(wrong)
            event.ignore()  # type: ignore[attr-defined]
            return
        event.acceptProposedAction()  # type: ignore[attr-defined]
        if self.add_pictures(paths) and self._on_close is not None:
            self._on_close()

    def _search_changed(self, _text: str) -> None:
        self._grid.set_sections(
            self._index.pictures,
            self._shown.others.pictures,
            self._search.text(),
            {p.qrc_path: self._qrc_label(p.qrc_path) for p in self._shown.others.pictures},
        )

    def _include_if_other(self, stored: str) -> bool:
        """Picking from a pictures file the form doesn't include adds the include first."""
        picture = self._shown.others.by_path.get(canon_resource(stored))
        if picture is None:
            return True
        try:
            commands = include_commands(self._host.document(), self._ui_path, picture.qrc_path)
        except (AttributeError, RuntimeError, TypeError):
            return False
        if not commands:
            return True
        session = self._session or self._host.begin_session("Use pictures file %s" % self._qrc_label(picture.qrc_path))
        try:
            ok = self._run(session, commands)
        finally:
            if self._session is None:
                session.close()
        if ok:
            self.reload()
            self._grid.select_path(stored)
        return ok

    def _pick(self, stored: str) -> None:
        if self._include_if_other(stored):
            self._on_pick(stored)

    def _activate(self, stored: str) -> None:
        if not self._include_if_other(stored):
            return
        self._on_pick(stored)
        if self._on_close is not None:
            self._on_close()

    def _activate_current(self) -> None:
        picture = self._grid.selected_picture()
        if picture is None:
            return
        self._activate(picture.resource_path)

    def _from_file(self) -> None:
        if self.in_project:
            names, _filter = QFileDialog.getOpenFileNames(self, "Add picture", "", dialog_filter())
            if not names:
                return
            if not self.add_pictures(list(names)):
                return
        else:
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
