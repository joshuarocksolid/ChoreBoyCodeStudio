"""In-place text editor. It is a viewport child and does not touch the form."""

from __future__ import annotations

from typing import Callable, Literal, Optional, Union

from app.qt.QtCore import QEvent, QObject, Qt
from app.qt.QtGui import QFont, QKeyEvent
from app.qt.QtWidgets import QGraphicsView, QLineEdit, QPlainTextEdit, QWidget
from app.qt.qt_compat import enum_value

from app.features.form_builder.qtside.canvas.core.gesture import EditorDone
from app.features.form_builder.qtside.canvas.core.space import ViewMap
from app.features.form_builder.qtside.canvas.core.text import TextTarget
from app.features.form_builder.qtside.realize.api import Realizer
from app.features.form_builder.qtside.theme.overlay import overlay_palette

_How = Literal["enter", "tab", "backtab", "escape", "focus_out"]
_Edit = Union[QLineEdit, QPlainTextEdit]


class InPlaceEditor:
    def __init__(self, viewport: QWidget, realizer: Realizer, done: Callable[[EditorDone], None]) -> None:
        self._viewport = viewport
        self._realizer = realizer
        self._done = done
        self._target: Optional[TextTarget] = None
        self._edit: Optional[_Edit] = None
        self._keys = _Keys(self)

    def open(self, target: TextTarget, view: ViewMap) -> None:
        # The proxy is already at ``view``. The editor reads the live widget.
        del view
        self.close(False)
        widget = self._realizer.widget_for(target.owner)
        if widget is None:
            return
        self._target = target
        edit: _Edit = QPlainTextEdit(self._viewport) if target.multiline else QLineEdit(self._viewport)
        zoomed = _zoomed_font(widget.font(), _scale(widget))
        edit.setFont(zoomed)
        edit.setStyleSheet(_sheet(self._viewport, zoomed))
        _copy_alignment(widget, edit)
        text = "" if target.original is None else target.original.text
        edit.setPlainText(text) if isinstance(edit, QPlainTextEdit) else edit.setText(text)
        edit.installEventFilter(self._keys)
        edit.textChanged.connect(lambda *args: self._grow())
        self._edit = edit
        self._place()
        edit.show()
        edit.raise_()
        edit.setFocus()
        edit.selectAll()

    def follow(self, view: ViewMap) -> None:
        del view
        if self._target is None:
            return
        self._place()

    def commit_on_press(self) -> None:
        """A press outside the editor commits. Escape is the only cancel."""
        if self._edit is None:
            return
        self._finish("focus_out")

    def close(self, restore_focus: bool) -> None:
        edit = self._edit
        self._edit = None
        self._target = None
        if edit is not None:
            edit.hide()
            edit.deleteLater()
        if restore_focus:
            view = self._viewport.parentWidget()
            if view is not None:
                view.setFocus()

    def target(self) -> Optional[TextTarget]:
        return self._target

    def _finish(self, how: _How) -> None:
        edit = self._edit
        target = self._target
        if edit is None or target is None:
            return
        text = edit.toPlainText() if isinstance(edit, QPlainTextEdit) else edit.text()
        self._target = None
        self._done(EditorDone(how, text))

    def _grow(self) -> None:
        edit = self._edit
        widget = None if self._target is None else self._realizer.widget_for(self._target.owner)
        if edit is None or widget is None:
            return
        scale = _scale(widget)
        width = max(int(round(widget.width() * scale)), edit.fontMetrics().horizontalAdvance(_current(edit)) + 12)
        if isinstance(edit, QPlainTextEdit):
            height = max(int(round(widget.height() * scale)), int(edit.document().size().height()) + 8)
        else:
            height = max(int(round(widget.height() * scale)), edit.sizeHint().height())
        edit.resize(width, height)

    def _place(self) -> None:
        edit = self._edit
        target = self._target
        if edit is None or target is None:
            return
        widget = self._realizer.widget_for(target.owner)
        root = self._realizer.root_widget
        view = self._viewport.parentWidget()
        if widget is None or root is None or view is None:
            return
        proxy = root.graphicsProxyWidget()
        if proxy is None:
            return
        if not isinstance(view, QGraphicsView):
            return
        origin = widget.mapTo(root, widget.rect().topLeft())
        port = view.mapFromScene(proxy.mapToScene(origin))
        edit.move(port)
        self._grow()


class _Keys(QObject):
    def __init__(self, owner: InPlaceEditor) -> None:
        super().__init__(owner._viewport)
        self._owner = owner

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        edit = self._owner._edit
        if edit is None or watched is not edit:
            return False
        if _is(event, "ShortcutOverride") and isinstance(event, QKeyEvent) and _claims(event, edit):
            event.accept()
            return True
        if _is(event, "KeyPress") and isinstance(event, QKeyEvent):
            how = _claimed(event, edit)
            if how is not None:
                self._owner._finish(how)
                return True
        if _is(event, "FocusOut"):
            self._owner._finish("focus_out")
        return False


def _claims(event: QKeyEvent, edit: _Edit) -> bool:
    return _claimed(event, edit) is not None


def _claimed(event: QKeyEvent, edit: _Edit) -> Optional[_How]:
    name = _key_name(event)
    if name == "enter" and isinstance(edit, QPlainTextEdit) and _shift(event):
        return None
    return name


def _key_name(event: QKeyEvent) -> Optional[_How]:
    key = enum_value(event.key())
    codes = getattr(Qt, "Key", Qt)
    if key in (enum_value(codes.Key_Return), enum_value(codes.Key_Enter)):
        return "enter"
    if key == enum_value(codes.Key_Escape):
        return "escape"
    if key == enum_value(codes.Key_Backtab) or (key == enum_value(codes.Key_Tab) and _shift(event)):
        return "backtab"
    if key == enum_value(codes.Key_Tab):
        return "tab"
    return None


def _shift(event: QKeyEvent) -> bool:
    value = enum_value(event.modifiers())
    flag = enum_value(getattr(getattr(Qt, "KeyboardModifier", Qt), "ShiftModifier"))
    return bool(value & flag)


def _is(event: QEvent, name: str) -> bool:
    expected = getattr(getattr(QEvent, "Type", QEvent), name)
    return enum_value(event.type()) == enum_value(expected)


def _scale(widget: QWidget) -> float:
    """Stage zoom. Only the page root is proxied, so walk up to it."""
    current: Optional[QWidget] = widget
    while current is not None:
        proxy = current.graphicsProxyWidget()
        if proxy is not None:
            return float(proxy.scale()) or 1.0
        current = current.parentWidget()
    return 1.0


def _zoomed_font(font: QFont, scale: float) -> QFont:
    zoomed = QFont(font)
    if zoomed.pixelSize() > 0:
        zoomed.setPixelSize(max(1, int(round(zoomed.pixelSize() * scale))))
    elif zoomed.pointSizeF() > 0:
        zoomed.setPointSizeF(zoomed.pointSizeF() * scale)
    return zoomed


def _sheet(viewport: QWidget, font: QFont) -> str:
    contrast = bool(viewport.property("formBuilderHighContrast"))
    color = overlay_palette(contrast).select
    if len(color) == 9:
        color = color[:7]
    family = font.family().replace("\\", "").replace("'", "")
    if font.pixelSize() > 0:
        size = "%dpx" % font.pixelSize()
    else:
        size = "%gpt" % font.pointSizeF()
    return (
        "background: #FFFFFF; color: #212529; border: 1px solid %s; padding: 0px;"
        " font-family: '%s'; font-size: %s;"
    ) % (color, family, size)


def _copy_alignment(widget: QWidget, edit: _Edit) -> None:
    alignment = getattr(widget, "alignment", None)
    setter = getattr(edit, "setAlignment", None)
    if alignment is None or setter is None:
        return
    setter(alignment())


def _current(edit: _Edit) -> str:
    if isinstance(edit, QPlainTextEdit):
        return edit.toPlainText()
    return edit.text()
