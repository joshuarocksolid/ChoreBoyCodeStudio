"""Pixmap row, icon set, and the brush Picture page (UX-PED-100 … 104)."""

from __future__ import annotations

from dataclasses import replace
from typing import Callable, Dict, Optional

from app.features.form_builder.engine.project.pictures import (
    PictureIndex,
    file_name_of,
    index_for_document,
    label_text_hides_picture,
    lookup_stored,
)
from app.features.form_builder.engine.ui4.values import (
    ICON_STATES,
    BrushValue,
    IconSetValue,
    ResourcePixmap,
)
from app.features.form_builder.qtside.inspector.api import (
    EditorHost,
    EditorKey,
    Mixed,
    Registrar,
    RowValue,
    ValueSpec,
    Written,
)
from app.features.form_builder.qtside.inspector.editors._editor_kit import (
    change_label,
    owner_name,
    warning_color,
)
from app.features.form_builder.qtside.inspector.editors._picture_picker import (
    PicturePicker,
    cached_thumbnail,
    displayed_name,
    form_directory,
)
from app.features.form_builder.qtside.inspector.editors._popover import RowPopover
from app.features.form_builder.qtside.visual.color_picker import Swatch
from app.features.form_builder.qtside.visual.common import RowSummary, begin_popover
from app.qt.QtCore import QSize, Qt
from app.qt.QtGui import QBrush, QFontMetrics, QPixmap
from app.qt.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

_FILE_WARNING = "Loaded from a file path. A packaged app may not find it."
_TEXT_HIDES = "The label's text replaces this picture when the app runs. Clear the text to show it."
_MISSING_SUFFIX = " (missing)"
_THEME_HELP = "Uses the desktop's icon with this name when there is one; otherwise the picture."
_MODES = ("Normal", "Disabled", "Active", "Selected")
_FLAGS = ("Off", "On")

OnTexture = Callable[[Optional[ResourcePixmap]], None]


def _focus(name: str) -> object:
    return getattr(getattr(Qt, "FocusPolicy", Qt), name)


def _missing_tip(stored: str) -> str:
    return "Code Studio can't find %s." % stored


class _PictureSummary(RowSummary):
    """File names elide in the middle, so the extension and "(missing)" stay visible."""

    def _elide(self) -> None:
        full = self.summary
        if not full:
            super()._elide()
            return
        metrics = QFontMetrics(self.font())
        available = max(0, self.width() - 28)
        suffix = _MISSING_SUFFIX if full.endswith(_MISSING_SUFFIX) else ""
        name = full[: len(full) - len(suffix)] if suffix else full
        room = max(0, available - metrics.horizontalAdvance(suffix))
        shown = metrics.elidedText(name, getattr(getattr(Qt, "TextElideMode", Qt), "ElideMiddle"), room) + suffix
        self.setText("%s \u25be" % shown)


class _StateButton(QToolButton):
    """One icon state. The caption wraps, because four columns share 320 px."""

    def __init__(self, parent: QWidget, on_clear: Callable[[], None]) -> None:
        super().__init__(parent)
        self._on_clear = on_clear
        self._caption = QLabel(self)
        self._caption.setWordWrap(True)
        self._caption.setAlignment(_align_center())
        self._caption.setFocusPolicy(_focus("NoFocus"))  # type: ignore[arg-type]
        self._caption.setAttribute(_transparent(), True)
        self.setSizePolicy(_policy("Expanding"), _policy("Preferred"))

    def set_caption(self, text: str, color: str) -> None:
        self._caption.setText(text)
        self._caption.setStyleSheet("color: %s; background: transparent;" % color)
        self.setText("")

    def resizeEvent(self, event: object) -> None:  # noqa: N802
        super().resizeEvent(event)  # type: ignore[arg-type]
        self._caption.setGeometry(self.rect().adjusted(2, 2, -2, -2))

    def keyPressEvent(self, event: object) -> None:  # noqa: N802
        key = event.key()  # type: ignore[attr-defined]
        keys = getattr(Qt, "Key", Qt)
        if key in (getattr(keys, "Key_Delete"), getattr(keys, "Key_Backspace")):
            self._on_clear()
            event.accept()  # type: ignore[attr-defined]
            return
        super().keyPressEvent(event)  # type: ignore[arg-type]

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(64, 36)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(48, 32)


def _align_center() -> object:
    flag = getattr(Qt, "AlignmentFlag", Qt)
    return getattr(flag, "AlignCenter")


def _transparent() -> object:
    return getattr(getattr(Qt, "WidgetAttribute", Qt), "WA_TransparentForMouseEvents")


def _policy(name: str) -> object:
    from app.qt.QtWidgets import QSizePolicy

    return getattr(getattr(QSizePolicy, "Policy", QSizePolicy), name)


def _popover_width_large(host: EditorHost) -> bool:
    """320 px. A wide row already caps a normal popover at 320; a narrow one needs large."""
    return host.row_widget.width() < 320


class _PictureRow:
    """Shared summary, thumbnail, file-path warning and picker popover."""

    def __init__(self, host: EditorHost, parent: QWidget, *, kind: str) -> None:
        self._host = host
        self._kind = kind
        self._root = QWidget(parent)
        layout = QHBoxLayout(self._root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self._swatch = Swatch(self._root, 16)
        self._swatch.set_tokens(host.chrome)
        self._summary = _PictureSummary(host.label or kind, self._root)
        self._summary.set_opener(self._open)
        layout.addWidget(self._swatch)
        layout.addWidget(self._summary, 1)
        self._warning = QLabel(parent)
        self._warning.setObjectName("formBuilder.pictureWarning")
        self._warning.setWordWrap(True)
        self._warning.setStyleSheet("color: %s;" % warning_color(host.chrome))
        self._warning.hide()
        self._stored = ""
        self._missing = False
        self._mixed = False
        self._written = False
        self._popover: Optional[RowPopover] = None
        self._form_dir = ""
        self._index = PictureIndex((), (), {})

    @property
    def widget(self) -> QWidget:
        return self._root

    @property
    def caption_widget(self) -> QWidget:
        return self._warning

    def paint_stored(self, stored: str, value: RowValue, *, label: str = "") -> None:
        self._mixed = isinstance(value, Mixed)
        self._written = isinstance(value, Written)
        self._stored = "" if self._mixed else stored
        self._form_dir = form_directory(self._host)
        try:
            self._index = index_for_document(self._host.document(), self._form_dir)
        except (AttributeError, RuntimeError, TypeError, OSError):
            self._index = PictureIndex((), (), {})
        _disk, self._missing = lookup_stored(self._stored, self._form_dir, self._index)
        text = label or displayed_name(self._stored, self._missing and bool(self._stored), mixed=self._mixed)
        self._summary.set_summary(text)
        self._summary.show_state(value, self._host.chrome.faint)
        if self._missing and self._stored:
            self._summary.setStyleSheet("color: %s;" % self._host.chrome.error)
            self._summary.setToolTip(_missing_tip(self._stored))
        elif self._stored:
            self._summary.setToolTip(self._stored)
        self._paint_thumb()
        file_path = bool(self._stored) and not self._stored.startswith(":/") and not self._missing
        notes = [_FILE_WARNING] if file_path else []
        if self._stored and not self._mixed and self._text_hides_picture():
            notes.append(_TEXT_HIDES)
        self._warning.setText("\n".join(notes))
        self._warning.setVisible(bool(notes))

    def _text_hides_picture(self) -> bool:
        if self._kind != "Pixmap":
            return False
        try:
            document = self._host.document()
            owners = self._host.owner_ids()
        except (AttributeError, RuntimeError, TypeError):
            return False
        for owner in owners:
            try:
                node = document.node(owner)
            except KeyError:
                continue
            if label_text_hides_picture(node):
                return True
        return False

    def _paint_thumb(self) -> None:
        if self._mixed or not self._stored or self._missing:
            self._swatch.set_color(None, hollow=not self._mixed, mixed=self._mixed)
            return
        disk, missing = lookup_stored(self._stored, self._form_dir, self._index)
        pixmap = QPixmap() if missing else cached_thumbnail(disk, 14)
        if pixmap.isNull():
            self._swatch.set_color(None, hollow=True, mixed=False)
            return
        self._swatch.set_fill(QBrush(pixmap))

    def _open(self) -> None:
        raise NotImplementedError

    def _begin(self, label: str) -> RowPopover:
        if self._popover is not None and not self._popover.closed:
            return self._popover
        opened = begin_popover(
            self._host,
            self._summary,
            label,
            large=_popover_width_large(self._host),
        )
        opened.set_reset(self._host.reset if self._written else None)
        self._popover = opened
        return opened


class PixmapEditor(_PictureRow):
    def __init__(self, spec: ValueSpec, host: EditorHost, parent: QWidget) -> None:
        del spec
        super().__init__(host, parent, kind="Pixmap")

    def show(self, value: RowValue) -> None:
        stored = ""
        if isinstance(value, Written) and isinstance(value.value, ResourcePixmap):
            stored = value.value.path
        self.paint_stored(stored, value)

    def _open(self) -> None:
        if self._popover is not None and not self._popover.closed:
            return
        popover = self._begin(change_label(self._host.label or "pixmap"))
        picker = PicturePicker(popover, self._host, self._pick, on_close=popover.done)
        if self._stored:
            picker.select_path(self._stored)
        popover.body().addWidget(picker)
        popover.open_popover()
        picker.focus_first()

    def _pick(self, stored: str) -> None:
        popover = self._popover
        if popover is None:
            return
        self._host.commit(ResourcePixmap(stored), session=popover.session)


class IconEditor(_PictureRow):
    def __init__(self, spec: ValueSpec, host: EditorHost, parent: QWidget) -> None:
        del spec
        super().__init__(host, parent, kind="Icon")
        self._icon = IconSetValue()
        self._target = "normaloff"
        self._pushing = False
        self._theme: Optional[QLineEdit] = None
        self._states: Dict[str, QToolButton] = {}
        self._picker: Optional[PicturePicker] = None
        self._picture_label: Optional[QLabel] = None

    def show(self, value: RowValue) -> None:
        if isinstance(value, Written) and isinstance(value.value, IconSetValue):
            self._icon = value.value
        else:
            # Mixed starts from an empty icon: a pick must not carry another selection's states.
            self._icon = IconSetValue()
        path = "" if isinstance(value, Mixed) else _icon_path(self._icon)
        label = ""
        if not path and self._icon.theme and not isinstance(value, Mixed):
            label = self._icon.theme
        self.paint_stored(path, value, label=label)
        self._sync_open()

    def _open(self) -> None:
        if self._popover is not None and not self._popover.closed:
            return
        name = owner_name(self._host) or "widget"
        popover = self._begin("Change icon of %s" % name)
        body = QWidget(popover)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        picture = QLabel("Picture", body)
        picture.setObjectName("formBuilder.iconPictureLabel")
        picture.setFocusPolicy(_focus("NoFocus"))  # type: ignore[arg-type]
        self._picture_label = picture
        layout.addWidget(picture)
        self._picker = PicturePicker(
            body,
            self._host,
            self._pick,
            on_close=popover.done,
            grid_height=180,
        )
        layout.addWidget(self._picker)
        theme_label = QLabel("Theme icon name", body)
        theme_label.setFocusPolicy(_focus("NoFocus"))  # type: ignore[arg-type]
        layout.addWidget(theme_label)
        theme = QLineEdit(body)
        theme.setObjectName("formBuilder.iconTheme")
        theme.setAccessibleName("Icon: theme icon name")
        theme.textChanged.connect(self._theme_changed)
        self._theme = theme
        layout.addWidget(theme)
        help_label = QLabel(_THEME_HELP, body)
        help_label.setWordWrap(True)
        help_label.setFocusPolicy(_focus("NoFocus"))  # type: ignore[arg-type]
        help_label.setStyleSheet("color: %s;" % self._host.chrome.muted)
        layout.addWidget(help_label)
        other = QToolButton(body)
        other.setText("Other states \u25b8")
        other.setCheckable(True)
        other.setObjectName("formBuilder.iconOtherStates")
        other.setAccessibleName("Icon: other states")
        other.setFocusPolicy(_focus("StrongFocus"))  # type: ignore[arg-type]
        grid = QWidget(body)
        grid.setObjectName("formBuilder.iconStates")
        grid_layout = QGridLayout(grid)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        self._states = {}
        for column, mode in enumerate(_MODES, start=1):
            header = QLabel(mode, grid)
            header.setFocusPolicy(_focus("NoFocus"))  # type: ignore[arg-type]
            grid_layout.addWidget(header, 0, column)
        for row, flag in enumerate(_FLAGS, start=1):
            side = QLabel(flag, grid)
            side.setFocusPolicy(_focus("NoFocus"))  # type: ignore[arg-type]
            grid_layout.addWidget(side, row, 0)
            for column, mode in enumerate(_MODES, start=1):
                attr = (mode + flag).lower()
                button = _StateButton(grid, lambda name=attr: self._clear_state(name))
                button.setObjectName("formBuilder.iconState." + attr)
                button.setAccessibleName("Icon: %s %s" % (mode.lower(), flag.lower()))
                button.setToolTip("Choose this state's picture above. Delete clears it.")
                button.setCheckable(True)
                button.setAutoExclusive(False)
                button.clicked.connect(lambda _checked=False, name=attr: self._retarget(name))
                self._states[attr] = button
                grid_layout.addWidget(button, row, column)
        for column in range(1, 5):
            grid_layout.setColumnStretch(column, 1)
        grid.hide()
        other.toggled.connect(grid.setVisible)
        other.toggled.connect(lambda _open: popover.place())
        layout.addWidget(other)
        layout.addWidget(grid)
        popover.body().addWidget(body)
        self._target = "normaloff"
        self._sync_open()
        popover.open_popover()
        if self._picker is not None:
            self._picker.focus_first()

    def _sync_open(self) -> None:
        theme = self._theme
        if theme is None or self._popover is None or self._popover.closed:
            return
        self._pushing = True
        shown = self._icon.theme or ""
        if theme.text() != shown and not theme.hasFocus():
            theme.setText(shown)
        for name, button in self._states.items():
            pixmap = getattr(self._icon, name)
            path = pixmap.path if isinstance(pixmap, ResourcePixmap) else ""
            chrome = self._host.chrome
            button.setStyleSheet(
                "QToolButton { background: %s; border: 1px solid %s; border-radius: 4px; }"
                "QToolButton:checked { border: 2px solid %s; }"
                % (chrome.input, chrome.border, chrome.accent)
            )
            if path:
                button.set_caption(file_name_of(path), chrome.text)
            elif name == "normaloff":
                button.set_caption("None", chrome.faint)
            else:
                button.set_caption("Same as normal", chrome.faint)
            button.setChecked(name == self._target)
        label = self._picture_label
        if label is not None:
            label.setText(_target_title(self._target))
        if self._picker is not None:
            current = getattr(self._icon, self._target)
            if isinstance(current, ResourcePixmap):
                self._picker.select_path(current.path)
        self._pushing = False

    def _retarget(self, name: str) -> None:
        self._target = name
        self._sync_open()

    def _pick(self, stored: str) -> None:
        states = {name: getattr(self._icon, name) for name in ICON_STATES}
        states[self._target] = ResourcePixmap(stored)
        text = self._icon.text
        normal = states.get("normaloff")
        if self._target == "normaloff":
            text = stored or None
        elif text is None and isinstance(normal, ResourcePixmap):
            text = normal.path
        self._icon = IconSetValue(
            theme=self._icon.theme,
            resource=self._icon.resource,
            text=text,
            normaloff=states["normaloff"],
            normalon=states["normalon"],
            disabledoff=states["disabledoff"],
            disabledon=states["disabledon"],
            activeoff=states["activeoff"],
            activeon=states["activeon"],
            selectedoff=states["selectedoff"],
            selectedon=states["selectedon"],
        )
        self._commit()

    def _clear_state(self, name: str) -> None:
        if getattr(self._icon, name) is None:
            return
        self._icon = replace(self._icon, **{name: None})
        if name == "normaloff":
            self._icon = replace(self._icon, text=None)
        self._target = name
        self._commit()

    def _theme_changed(self, text: str) -> None:
        if self._pushing:
            return
        theme = text.strip() or None
        if theme == self._icon.theme:
            return
        self._icon = replace(self._icon, theme=theme)
        self._commit()

    def _commit(self) -> None:
        popover = self._popover
        if popover is None:
            return
        self._host.commit(self._icon, session=popover.session)
        path = _icon_path(self._icon)
        label = (self._icon.theme or "") if not path else ""
        self.paint_stored(path, Written(self._icon), label=label)
        self._sync_open()


def _target_title(target: str) -> str:
    """ "Picture" for the normal off state, else which state the picker writes."""
    if target == "normaloff":
        return "Picture"
    for mode in _MODES:
        for flag in _FLAGS:
            if (mode + flag).lower() == target:
                return "Picture for %s, %s" % (mode.lower(), flag.lower())
    return "Picture"


def _icon_path(icon: IconSetValue) -> str:
    if icon.normaloff is not None and icon.normaloff.path:
        return icon.normaloff.path
    if icon.text:
        return icon.text
    for name in ICON_STATES:
        pixmap = getattr(icon, name)
        if isinstance(pixmap, ResourcePixmap) and pixmap.path:
            return pixmap.path
    return ""


class BrushPicturePage(QWidget):
    """The picture picker embedded in the brush popover (UX-PED-103)."""

    def __init__(self, parent: QWidget, host: EditorHost, on_texture: OnTexture) -> None:
        super().__init__(parent)
        self._on_texture = on_texture
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._picker = PicturePicker(self, host, self._picked, grid_height=160)
        layout.addWidget(self._picker)

    def show_stored(self, texture: Optional[ResourcePixmap]) -> None:
        if texture is not None and texture.path:
            self._picker.select_path(texture.path)

    def _picked(self, path: str) -> None:
        self._on_texture(ResourcePixmap(path) if path else None)


def _brush_picture_page(parent: QWidget, host: EditorHost, on_texture: OnTexture) -> QWidget:
    return BrushPicturePage(parent, host, on_texture)


def _brush_thumbnail(host: EditorHost, stored: str, side: int) -> QPixmap:
    form_dir = form_directory(host)
    try:
        index = index_for_document(host.document(), form_dir)
    except (AttributeError, RuntimeError, TypeError, OSError):
        return QPixmap()
    disk, missing = lookup_stored(stored, form_dir, index)
    return QPixmap() if missing else cached_thumbnail(disk, side)


def register(registrar: Registrar) -> None:
    from app.features.form_builder.qtside.visual.brush import add_brush_style, set_brush_picture_page

    add_brush_style("picture", "Picture")
    set_brush_picture_page(_brush_picture_page, _brush_thumbnail)
    registrar.editor(EditorKey(ResourcePixmap.ELEMENT), PixmapEditor)
    registrar.editor(EditorKey(IconSetValue.ELEMENT), IconEditor)
