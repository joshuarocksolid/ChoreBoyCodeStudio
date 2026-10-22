"""Editor tab bar: movable tabs, preview italics, and disk-state markers.

The bar keeps Qt's own ``QTabBar.paintEvent`` so a dragged tab is drawn by
Qt's moving-tab widget. Preview italics and the stale/missing markers are
drawn by :class:`EditorTabStyle` in ``drawItemText``. The product stylesheet
styles ``QTabBar::tab``; Qt's stylesheet style then paints tab shapes and
labels itself and never calls a proxy's ``drawControl``, but it still hands
the label text to the widget's own style through ``drawItemText``.
"""

from __future__ import annotations

from typing import Callable, Optional

from app.qt.QtCore import QPoint, QRect, QSize, Qt
from app.qt.QtGui import QColor, QFont, QFontMetrics, QIcon, QMouseEvent, QPainter, QPalette, QPen, QPixmap, QPolygon
from app.qt.QtWidgets import QApplication, QProxyStyle, QTabBar, QWidget
from app.qt.qt_compat import event_pos

TAB_STATE_STALE = "stale"
TAB_STATE_MISSING = "missing"
TAB_MARKER_SIZE = 14
TAB_MARKER_GAP = 5
_PREVIEW_EXTRA_WIDTH = 4

DEFAULT_WARNING_COLOR = "#D97706"
DEFAULT_ERROR_COLOR = "#E03131"
DEFAULT_MUTED_COLOR = "#868E96"

TAB_TOOLTIP_UNSAVED = "Unsaved changes"
TAB_TOOLTIP_PREVIEW = (
    "Preview: this tab is reused for the next file you open.\n"
    "Edit the file or double-click the tab to keep it open."
)
TAB_TOOLTIP_STALE = (
    "Changed on disk. You kept your version.\n"
    "When you save, CBCS asks before it replaces the file on disk."
)
TAB_TOOLTIP_MISSING = (
    "Not on disk any more. It was deleted, renamed, or moved outside CBCS.\n"
    "Your text is still here. Use Save As to keep it."
)


def tab_disk_state(tab_data: object) -> Optional[str]:
    """Return ``"missing"``, ``"stale"`` or None from editor tab data."""
    if not isinstance(tab_data, dict):
        return None
    if tab_data.get("is_missing"):
        return TAB_STATE_MISSING
    if tab_data.get("is_stale"):
        return TAB_STATE_STALE
    return None


def tab_is_preview(tab_data: object) -> bool:
    return isinstance(tab_data, dict) and bool(tab_data.get("is_preview"))


def editor_tab_tooltip(
    file_path: str,
    *,
    is_dirty: bool,
    is_preview: bool,
    is_stale: bool,
    is_missing: bool,
) -> str:
    """Tooltip for an editor tab: the full path, then what its state means."""
    lines = [file_path]
    if is_missing:
        lines.append(TAB_TOOLTIP_MISSING)
    elif is_stale:
        lines.append(TAB_TOOLTIP_STALE)
    elif is_preview:
        lines.append(TAB_TOOLTIP_PREVIEW)
    if is_dirty:
        lines.append(TAB_TOOLTIP_UNSAVED)
    return "\n".join(lines)


def warning_marker_icon(color_hex: str, size: int = TAB_MARKER_SIZE) -> QIcon:
    """Filled warning triangle with a white bar and dot."""
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor(color_hex))
    painter.setPen(Qt.NoPen)
    inset = max(1, size // 12)
    triangle = QPolygon()
    triangle.append(QPoint(size // 2, inset))
    triangle.append(QPoint(size - inset, size - inset))
    triangle.append(QPoint(inset, size - inset))
    painter.drawPolygon(triangle)
    painter.setBrush(QColor("#FFFFFF"))
    bar_width = max(2, size // 10)
    bar_height = max(4, size // 3)
    bar_x = (size - bar_width) // 2
    bar_y = size // 2 - bar_height // 2 + size // 12
    painter.drawRoundedRect(bar_x, bar_y, bar_width, bar_height, 1.0, 1.0)
    dot_y = bar_y + bar_height + max(1, size // 16)
    painter.drawEllipse((size - bar_width) // 2, dot_y, bar_width, bar_width)
    painter.end()
    return QIcon(pixmap)


def missing_marker_icon(color_hex: str, size: int = TAB_MARKER_SIZE) -> QIcon:
    """Filled circle with a white x."""
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor(color_hex))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(1, 1, size - 2, size - 2)
    pen = QPen(QColor("#FFFFFF"))
    pen.setWidthF(max(1.6, size / 10.0))
    pen.setCapStyle(Qt.RoundCap)
    painter.setPen(pen)
    center = size / 2.0
    radius = size * 0.22
    painter.drawLine(int(center - radius), int(center - radius), int(center + radius), int(center + radius))
    painter.drawLine(int(center + radius), int(center - radius), int(center - radius), int(center + radius))
    painter.end()
    return QIcon(pixmap)


class EditorTabStyle(QProxyStyle):
    """Draws preview italics and disk-state markers for editor tab labels."""

    def __init__(self) -> None:
        super().__init__()
        self._muted_color = QColor(DEFAULT_MUTED_COLOR)
        self._icons: dict[str, QIcon] = {}
        self.set_marker_colors(
            warning=DEFAULT_WARNING_COLOR,
            error=DEFAULT_ERROR_COLOR,
            muted=DEFAULT_MUTED_COLOR,
        )

    def set_marker_colors(self, *, warning: str, error: str, muted: str) -> None:
        self._muted_color = QColor(muted or DEFAULT_MUTED_COLOR)
        self._icons = {
            TAB_STATE_STALE: warning_marker_icon(warning or DEFAULT_WARNING_COLOR),
            TAB_STATE_MISSING: missing_marker_icon(error or DEFAULT_ERROR_COLOR),
        }

    def marker_icon(self, state: str) -> QIcon:
        return self._icons[state]

    def drawItemText(  # noqa: N802 - Qt signature
        self,
        painter: QPainter,
        rect: QRect,
        flags: int,
        palette: QPalette,
        enabled: bool,
        text: str,
        textRole: QPalette.ColorRole = QPalette.NoRole,  # noqa: N803 - Qt signature
    ) -> None:
        tab_bar = MiddleClickTabBar.painting_bar
        index = -1 if tab_bar is None else tab_bar.label_index_for_paint(painter, rect, text)
        if tab_bar is None or index < 0:
            super().drawItemText(painter, rect, flags, palette, enabled, text, textRole)
            return
        data = tab_bar.tabData(index)
        state = tab_disk_state(data)
        preview = tab_is_preview(data)
        if state is None and not preview:
            super().drawItemText(painter, rect, flags, palette, enabled, text, textRole)
            return
        painter.save()
        font = QFont(painter.font())
        font.setItalic(preview)
        font.setStrikeOut(state == TAB_STATE_MISSING)
        painter.setFont(font)
        text_palette = QPalette(palette)
        if state == TAB_STATE_MISSING:
            role = textRole if textRole != QPalette.NoRole else QPalette.WindowText
            text_palette.setColor(role, self._muted_color)
        text_rect = QRect(rect)
        if state is not None:
            text_width = QFontMetrics(font).horizontalAdvance(text)
            group_width = TAB_MARKER_SIZE + TAB_MARKER_GAP + text_width
            left = rect.left() + max(0, (rect.width() - group_width) // 2)
            top = rect.top() + (rect.height() - TAB_MARKER_SIZE) // 2
            self._icons[state].paint(painter, QRect(left, top, TAB_MARKER_SIZE, TAB_MARKER_SIZE))
            text_rect = QRect(left + TAB_MARKER_SIZE + TAB_MARKER_GAP, rect.top(), text_width + 2, rect.height())
            flags = int(Qt.AlignVCenter | Qt.AlignLeft | Qt.TextShowMnemonic)
        super().drawItemText(painter, text_rect, flags, text_palette, enabled, text, textRole)
        painter.restore()


class MiddleClickTabBar(QTabBar):
    """Editor tab bar: movable, middle-click close, double-click promote.

    A press that leaves the bar vertically hands the drag to the group-drag
    callbacks (plain mouse tracking, no ``QDrag``), so another editor group can
    take the tab without a nested event loop.
    """

    # The bar whose paint or mouse handler is running. Qt paints the moving
    # tab's drag image into a pixmap from inside mouseMoveEvent, so the style
    # cannot reach the bar through the painter there.
    painting_bar: Optional["MiddleClickTabBar"] = None

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tab_double_click_callback: Callable[[int], None] | None = None
        self._group_drag_started: Callable[[int], None] | None = None
        self._group_drag_moved: Callable[[QPoint], None] | None = None
        self._group_drag_finished: Callable[[QPoint], None] | None = None
        self._press_index = -1
        self._press_pos = QPoint()
        self._group_drag_active = False
        self._tab_style = EditorTabStyle()
        self.setStyle(self._tab_style)
        self.setMovable(True)

    def tab_style(self) -> EditorTabStyle:
        return self._tab_style

    def set_tab_double_click_callback(self, callback: Callable[[int], None] | None) -> None:
        self._tab_double_click_callback = callback

    def set_group_drag_callbacks(
        self,
        *,
        started: Callable[[int], None] | None,
        moved: Callable[[QPoint], None] | None,
        finished: Callable[[QPoint], None] | None,
    ) -> None:
        self._group_drag_started = started
        self._group_drag_moved = moved
        self._group_drag_finished = finished

    def is_group_drag_active(self) -> bool:
        return self._group_drag_active

    def label_index_for_paint(self, painter: QPainter, rect: QRect, text: str) -> int:
        """Return the tab whose label is being painted, or -1."""
        if not isinstance(painter.device(), QWidget):
            # The drag image of the pressed tab, which is the current tab.
            return self.currentIndex()
        matches = [index for index in range(self.count()) if self.tabText(index) == text]
        if len(matches) == 1:
            return matches[0]
        center = rect.center()
        for index in matches or range(self.count()):
            if self.tabRect(index).contains(center):
                return index
        return matches[0] if matches else -1

    def tabSizeHint(self, index: int) -> QSize:  # noqa: N802 - Qt signature
        size = super().tabSizeHint(index)
        data = self.tabData(index)
        extra = 0
        if tab_disk_state(data) is not None:
            extra += TAB_MARKER_SIZE + TAB_MARKER_GAP
        if tab_is_preview(data):
            extra += _PREVIEW_EXTRA_WIDTH
        if extra:
            size.setWidth(size.width() + extra)
        return size

    def paintEvent(self, arg__1) -> None:  # type: ignore[no-untyped-def]  # noqa: N802 - Qt signature
        with _PaintingBar(self):
            super().paintEvent(arg__1)

    def mousePressEvent(self, arg__1: QMouseEvent) -> None:  # noqa: N802 - Qt signature
        if arg__1.button() == Qt.MiddleButton:
            tab_index = self.tabAt(event_pos(arg__1))
            if tab_index >= 0:
                self.tabCloseRequested.emit(tab_index)
            return
        if arg__1.button() == Qt.LeftButton:
            self._press_index = self.tabAt(event_pos(arg__1))
            self._press_pos = QPoint(event_pos(arg__1))
            self._group_drag_active = False
        with _PaintingBar(self):
            super().mousePressEvent(arg__1)

    def mouseMoveEvent(self, arg__1: QMouseEvent) -> None:  # noqa: N802 - Qt signature
        if (
            self._group_drag_started is not None
            and self._press_index >= 0
            and arg__1.buttons() & Qt.LeftButton
        ):
            if not self._group_drag_active and self._left_bar(event_pos(arg__1)):
                self._group_drag_active = True
                self._group_drag_started(self._press_index)
            if self._group_drag_active:
                if self._group_drag_moved is not None:
                    self._group_drag_moved(self.mapToGlobal(event_pos(arg__1)))
                return
        with _PaintingBar(self):
            super().mouseMoveEvent(arg__1)

    def mouseReleaseEvent(self, arg__1: QMouseEvent) -> None:  # noqa: N802 - Qt signature
        if self._group_drag_active:
            self._group_drag_active = False
            self._press_index = -1
            super().mouseReleaseEvent(arg__1)
            if self._group_drag_finished is not None:
                self._group_drag_finished(self.mapToGlobal(event_pos(arg__1)))
            return
        self._press_index = -1
        super().mouseReleaseEvent(arg__1)

    def mouseDoubleClickEvent(self, arg__1: QMouseEvent) -> None:  # noqa: N802 - Qt signature
        tab_index = self.tabAt(event_pos(arg__1))
        if tab_index >= 0 and self._tab_double_click_callback is not None:
            self._tab_double_click_callback(tab_index)
            arg__1.accept()
            return
        super().mouseDoubleClickEvent(arg__1)

    def _left_bar(self, pos: QPoint) -> bool:
        """Return whether a tab drag has left this bar, so it targets another group.

        Up or down past the bar's height, or sideways past its ends, which is
        where the other group's tab bar is when the groups sit side by side.
        """
        distance = max(self.height(), QApplication.startDragDistance())
        if abs(pos.y() - self._press_pos.y()) > distance:
            return True
        margin = QApplication.startDragDistance()
        return pos.x() < -margin or pos.x() > self.width() + margin


class _PaintingBar:
    """Marks ``bar`` as the bar being painted for the duration of a handler."""

    def __init__(self, bar: MiddleClickTabBar) -> None:
        self._bar = bar
        self._previous: Optional[MiddleClickTabBar] = None

    def __enter__(self) -> None:
        self._previous = MiddleClickTabBar.painting_bar
        MiddleClickTabBar.painting_bar = self._bar

    def __exit__(self, *_exc: object) -> None:
        MiddleClickTabBar.painting_bar = self._previous


__all__ = [
    "EditorTabStyle",
    "MiddleClickTabBar",
    "TAB_STATE_MISSING",
    "TAB_STATE_STALE",
    "editor_tab_tooltip",
    "missing_marker_icon",
    "tab_disk_state",
    "tab_is_preview",
    "warning_marker_icon",
]
