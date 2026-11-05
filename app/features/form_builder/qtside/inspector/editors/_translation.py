"""Translation for one string (UX-PED-041).

The disclosure is a 16 px glyph on the trailing edge of the field. It is
painted on hover, on focus, or all the time once a translation flag is set.
The panel under the row keeps the translator fields.
"""

from __future__ import annotations

from typing import Callable, Optional, Tuple

from app.features.form_builder.qtside.theme.metrics import ICON, S2
from app.qt.qt_compat import wrapper_is_valid
from app.qt.QtCore import QEvent, QObject, QPoint, QTimer, Qt
from app.qt.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from app.qt.QtWidgets import (
    QApplication,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

_MEANING_HELP = (
    "Tells translators which meaning is meant when the same words mean "
    "different things, like \u201cOpen\u201d a file or \u201cOpen\u201d the shop."
)


class TranslationDisclosure(QWidget):
    """Attribute editor for one string or one whole string list."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.translation")
        self._on_change: Optional[Callable[[str, object], None]] = None
        self._on_toggle: Optional[Callable[[bool], None]] = None
        self._show_id = False
        self._painting = False
        self._expanded = False
        self._pinned = False
        self._hover = False
        self._host: Optional[QWidget] = None
        self._inset = -1
        self._notr = False
        self._toggle = QToolButton(self)
        self._toggle.setObjectName("formBuilder.translationToggle")
        self._toggle.setToolTip("Translation")
        self._toggle.setAccessibleName("Translation")
        self._toggle.setAutoRaise(True)
        self._toggle.setCheckable(True)
        self._toggle.setFixedSize(ICON, ICON)
        self._toggle.setFocusPolicy(Qt.StrongFocus)
        self._tag = QLabel("Not translated", self)
        self._tag.setObjectName("formBuilder.translationTag")
        self._tag.hide()
        self._body = QWidget(self)
        body = QVBoxLayout(self._body)
        body.setContentsMargins(S2, 2, 0, 0)
        body.setSpacing(2)
        self._translate = QCheckBox("Translate this text", self._body)
        self._translate.setAccessibleName("Translation: translate this text")
        self._meaning = self._field("Meaning", _MEANING_HELP)
        self._note = self._field("Note for the translator", "")
        self._ident = self._field("Translation id", "")
        for widget in (
            self._translate,
            self._meaning[0],
            self._meaning[1],
            self._note[0],
            self._note[1],
            self._ident[0],
            self._ident[1],
        ):
            body.addWidget(widget)
        self._body.hide()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(self._body)
        self._toggle.clicked.connect(self._toggle_body)
        self._translate.clicked.connect(self._commit_translate)
        self._meaning[1].editingFinished.connect(lambda: self._commit_text("comment", self._meaning[1]))
        self._note[1].editingFinished.connect(lambda: self._commit_text("extracomment", self._note[1]))
        self._ident[1].editingFinished.connect(lambda: self._commit_text("id", self._ident[1]))
        self._paint_icon()

    def place_on(self, host: QWidget) -> None:
        """Sit the glyph on the trailing edge of ``host`` (a line edit or summary)."""
        previous = self._host
        if previous is not None and previous is not host:
            previous.removeEventFilter(self)
        self._host = host
        self._toggle.setParent(host)
        self._toggle.raise_()
        host.installEventFilter(self)
        self._inset = -1
        self._seat()
        self._sync_button()

    def setVisible(self, visible: bool) -> None:  # noqa: N802
        super().setVisible(visible)
        self._toggle.setVisible(bool(visible))
        if not visible:
            self._clear_margins()

    def _clear_margins(self) -> None:
        host = self._host
        if host is None:
            return
        margins = getattr(host, "setTextMargins", None)
        if callable(margins):
            margins(0, 0, 0, 0)
        self._inset = -1

    def set_on_change(self, callback: Optional[Callable[[str, object], None]]) -> None:
        self._on_change = callback

    def set_on_toggle(self, callback: Optional[Callable[[bool], None]]) -> None:
        """Told when the user opens or closes the disclosure, so the host can remember it."""
        self._on_toggle = callback

    def set_values(
        self,
        *,
        notr: Optional[bool],
        comment: Optional[str],
        extracomment: Optional[str],
        ident: Optional[str],
        show_id: bool,
    ) -> None:
        self._painting = True
        self._show_id = show_id or ident is not None
        self._notr = notr is True
        self._pinned = bool(notr is True or comment or extracomment or ident)
        self._translate.setChecked(notr is not True)
        self._meaning[1].setText(comment or "")
        self._note[1].setText(extracomment or "")
        self._ident[1].setText(ident or "")
        self._tag.setVisible(notr is True)
        self._apply_id()
        self._painting = False
        self._sync_button()

    def set_expanded(self, expanded: bool) -> None:
        self._expanded = bool(expanded)
        self._toggle.setChecked(self._expanded)
        self._body.setVisible(self._expanded)
        self._sync_button()

    def expanded(self) -> bool:
        return self._expanded

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if watched is not self._host:
            return False
        kind = event.type()
        if kind in (_RESIZE, _SHOW):
            self._seat()
        elif kind == _ENTER:
            self._hover = True
            self._sync_button()
        elif kind == _LEAVE:
            self._hover = False
            QTimer.singleShot(0, self._sync_button)
        elif kind in (_FOCUS_IN, _FOCUS_OUT):
            QTimer.singleShot(0, self._sync_button)
        return False

    def showEvent(self, event: QEvent) -> None:  # noqa: N802
        super().showEvent(event)  # type: ignore[arg-type]
        self._paint_icon()
        self._seat()

    def _field(self, label: str, tip: str) -> Tuple[QLabel, QLineEdit]:
        caption = QLabel(label, self._body)
        caption.setObjectName("formBuilder.translationCaption")
        edit = QLineEdit(self._body)
        edit.setAccessibleName("Translation: %s" % label.lower())
        if tip:
            edit.setToolTip(tip)
            caption.setToolTip(tip)
        return caption, edit

    def _apply_id(self) -> None:
        shown = self._show_id or bool(self._ident[1].text())
        self._ident[0].setVisible(shown)
        self._ident[1].setVisible(shown)

    def _toggle_body(self) -> None:
        self.set_expanded(self._toggle.isChecked())
        callback = self._on_toggle
        if callback is not None:
            callback(self._expanded)

    def _commit_translate(self) -> None:
        if self._painting:
            return
        checked = self._translate.isChecked()
        self._notr = not checked
        self._pinned = self._pinned or self._notr
        self._tag.setVisible(not checked)
        self._emit("notr", None if checked else True)

    def _commit_text(self, field: str, edit: QLineEdit) -> None:
        if self._painting:
            return
        text = edit.text() or None
        if text:
            self._pinned = True
        self._emit(field, text)

    def _emit(self, field: str, value: object) -> None:
        callback = self._on_change
        if callback is not None:
            callback(field, value)
        self._sync_button()

    def _seat(self) -> None:
        if not wrapper_is_valid(self):
            return
        host = self._host
        toggle = self._toggle
        holder = toggle.parentWidget()
        if host is None or holder is None:
            return
        inset = max(0, (host.height() - ICON) // 2)
        if holder is host:
            origin = QPoint(0, 0)
        else:
            origin = host.mapTo(holder, QPoint(0, 0))
        toggle.setGeometry(origin.x() + max(0, host.width() - ICON - inset), origin.y() + inset, ICON, ICON)
        toggle.raise_()
        if inset == self._inset:
            return
        self._inset = inset
        margins = getattr(host, "setTextMargins", None)
        if callable(margins):
            margins(0, 0, ICON + inset, 0)

    def _sync_button(self) -> None:
        if not wrapper_is_valid(self) or not wrapper_is_valid(self._toggle):
            return
        if not self.isVisible():
            self._toggle.setVisible(False)
            return
        focus = QApplication.focusWidget()
        hot = self._hover or focus is self._host or focus is self._toggle or self._toggle.hasFocus()
        glyph = self._pinned or hot or self._expanded
        self._paint_icon("" if not glyph else _ink(self._toggle))
        if self._host is None:
            self._toggle.setVisible(True)
            return
        # Stay in the tab chain. The glyph is what appears and disappears.
        self._toggle.setVisible(True)

    def _paint_icon(self, color: str = "") -> None:
        ink = color or _ink(self._toggle)
        if not ink:
            self._toggle.setIcon(QIcon())
            return
        dpr = float(self._toggle.devicePixelRatioF()) if hasattr(self._toggle, "devicePixelRatioF") else 1.0
        self._toggle.setIcon(QIcon(_balloon(ink, dpr)))
        self._toggle.setIconSize(self._toggle.size())


def _ink(widget: QWidget) -> str:
    color = widget.palette().color(widget.foregroundRole())
    if not color.isValid():
        return ""
    return color.name()


def _balloon(color: str, dpr: float) -> QPixmap:
    """A 16 px speech balloon. The glyph catalog has no translation mark."""
    ratio = round(float(dpr), 2) or 1.0
    device = max(1, int(round(ICON * ratio)))
    pixmap = QPixmap(device, device)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    try:
        painter.setRenderHint(getattr(getattr(QPainter, "RenderHint", QPainter), "Antialiasing"), True)
        pen = QPen(QColor(color))
        pen.setWidthF(1.5 * (ICON / 16.0) * ratio)
        painter.setPen(pen)
        painter.setBrush(getattr(getattr(Qt, "BrushStyle", Qt), "NoBrush"))
        scale = (ICON / 16.0) * ratio
        painter.drawRoundedRect(int(3 * scale), int(2 * scale), int(10 * scale), int(8 * scale), 2 * scale, 2 * scale)
        painter.drawLine(int(6 * scale), int(10 * scale), int(5 * scale), int(13 * scale))
    finally:
        painter.end()
    pixmap.setDevicePixelRatio(ratio)
    return pixmap


_RESIZE = getattr(getattr(QEvent, "Type", QEvent), "Resize")
_SHOW = getattr(getattr(QEvent, "Type", QEvent), "Show")
_ENTER = getattr(getattr(QEvent, "Type", QEvent), "Enter")
_LEAVE = getattr(getattr(QEvent, "Type", QEvent), "Leave")
_FOCUS_IN = getattr(getattr(QEvent, "Type", QEvent), "FocusIn")
_FOCUS_OUT = getattr(getattr(QEvent, "Type", QEvent), "FocusOut")
