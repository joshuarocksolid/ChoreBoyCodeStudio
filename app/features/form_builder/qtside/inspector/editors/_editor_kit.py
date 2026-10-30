"""Shared words and Qt enum lookups for the scalar editors."""

from __future__ import annotations

from typing import Optional

from app.features.form_builder.engine.ui4.values import Value
from app.features.form_builder.qtside.inspector.api import EditorHost, Mixed, RowValue, Unset, Written
from app.qt.QtCore import QEvent, QLocale, QObject, Qt
from app.qt.QtGui import QColor, QKeySequence
from app.qt.QtWidgets import QGridLayout, QLabel, QLineEdit, QWidget

MINUS = "\u2212"


def project_locale() -> QLocale:
    """Numbers and dates use the project locale, en_US, not the machine's."""
    language = getattr(QLocale, "Language")
    territory = getattr(QLocale, "Territory", None) or getattr(QLocale, "Country")
    return QLocale(getattr(language, "English"), getattr(territory, "UnitedStates"))

# UX spec fb.warning swatches: light, dark, high-contrast light, high-contrast dark.
# Light amber is dark enough for 4.5:1 on the white inspector. The others already clear that bar.
_WARNING = ((138, 75, 8), (229, 161, 0), (122, 69, 0), (255, 215, 0))


def change_label(label: str) -> str:
    """Undo name for one property session: "Change echo mode"."""
    if not label:
        return "Change value"
    return "Change " + label[0].lower() + label[1:]


def payload(value: RowValue) -> Optional[Value]:
    if isinstance(value, Written):
        return value.value
    if isinstance(value, Unset):
        return value.default
    return None


def can_reset(value: RowValue, previous: bool) -> bool:
    """Clearing deletes a written property, or an unset one that has a class default."""
    if isinstance(value, Written):
        return True
    if isinstance(value, Unset):
        return value.default is not None
    return previous


def part_name(host: EditorHost, part: str) -> str:
    label = host.label.strip() if host.label else "Value"
    return "%s: %s" % (label, part)


def name_part(widget: QWidget, host: EditorHost, part: str) -> None:
    widget.setAccessibleName(part_name(host, part))


def warning_color(chrome: object) -> str:
    dark = bool(getattr(chrome, "is_dark", False))
    contrast = bool(getattr(chrome, "is_high_contrast", False))
    if contrast:
        red, green, blue = _WARNING[3] if dark else _WARNING[2]
    else:
        red, green, blue = _WARNING[1] if dark else _WARNING[0]
    return QColor(red, green, blue).name()


def qt_names_visible(host: EditorHost) -> bool:
    label = host.row_widget.findChild(QLabel, "formBuilder.rowQtName")
    return isinstance(label, QLabel) and label.isVisible() and bool(label.text())


def owner_name(host: EditorHost) -> str:
    widget: Optional[QWidget] = host.row_widget
    while widget is not None and widget.objectName() != "formBuilder.inspector":
        widget = widget.parentWidget()
    if widget is None:
        return ""
    name = widget.findChild(QLineEdit, "formBuilder.inspectorName")
    if not isinstance(name, QLineEdit):
        return ""
    return str(name.text())


def qt_key(name: str) -> object:
    return getattr(getattr(Qt, "Key", Qt), name)


def qt_mod(name: str) -> object:
    return getattr(getattr(Qt, "KeyboardModifier", Qt), name)


def qt_align(name: str) -> object:
    return getattr(getattr(Qt, "AlignmentFlag", Qt), name)


def qt_focus(name: str) -> object:
    return getattr(getattr(Qt, "FocusPolicy", Qt), name)


def event_type(name: str) -> object:
    return getattr(getattr(QEvent, "Type", QEvent), name)


def is_mixed(value: RowValue) -> bool:
    return isinstance(value, Mixed)


class _YieldUndo(QObject):
    """Let Edit > Undo reach the form. The field must not eat Ctrl+Z."""

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() != event_type("ShortcutOverride"):
            return False
        matches = getattr(event, "matches", None)
        if not callable(matches):
            return False
        standard = getattr(QKeySequence, "StandardKey", QKeySequence)
        if matches(getattr(standard, "Undo")) or matches(getattr(standard, "Redo")):
            event.ignore()  # type: ignore[attr-defined]
            return True
        return False


def yield_form_undo(widget: QWidget) -> None:
    widget.installEventFilter(_YieldUndo(widget))


class PairColumn(QWidget):
    """Field beside an accessory, or above it when the column cannot hold both.

    The reference string is the widest text the field must show. At that
    width the field takes the whole column and the accessory moves under it.
    """

    def __init__(self, field: QWidget, extra: QWidget, reference: str, parent: QWidget) -> None:
        super().__init__(parent)
        self._field = field
        self._extra = extra
        self._reference = reference
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(4)
        field.setParent(self)
        extra.setParent(self)
        self._stacked: Optional[bool] = None
        self._apply(False)

    def resizeEvent(self, event: object) -> None:  # noqa: N802
        super().resizeEvent(event)  # type: ignore[arg-type]
        self.relayout()

    def relayout(self) -> None:
        metrics = self._field.fontMetrics()
        shown = str(self._field.text() or "")  # type: ignore[attr-defined]
        sample = shown if metrics.horizontalAdvance(shown) > metrics.horizontalAdvance(self._reference) else self._reference
        need = metrics.horizontalAdvance(sample) + 12
        stacked = int(self.width()) < need + int(self._extra.sizeHint().width())
        if stacked != self._stacked:
            self._apply(stacked)

    def _apply(self, stacked: bool) -> None:
        self._stacked = stacked
        while self._grid.count():
            self._grid.takeAt(0)
        if stacked:
            self._grid.addWidget(self._field, 0, 0)
            self._grid.addWidget(self._extra, 1, 0)
        else:
            self._grid.addWidget(self._field, 0, 0)
            self._grid.addWidget(self._extra, 0, 1)
