"""Glyphs painted with QPainter. No asset files.

Every glyph is drawn in a 16 x 16 box with 1.4 px strokes in one colour, so the
whole set reads as one family at any device pixel ratio.
"""

from __future__ import annotations

import math
import tempfile
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QGuiApplication, QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap

_CACHE: dict = {}
_ASSET_DIR = Path(tempfile.gettempdir()) / "cbcs_form_builder_assets"


def _pen(color: QColor, width: float = 1.4) -> QPen:
    pen = QPen(color, width)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    return pen


def _rr(p: QPainter, x, y, w, h, r=2.0):
    p.drawRoundedRect(QRectF(x, y, w, h), r, r)


def _fill(p: QPainter, color: QColor, alpha: int = 255):
    c = QColor(color)
    c.setAlpha(alpha)
    p.setBrush(c)


def _no_fill(p: QPainter):
    p.setBrush(Qt.NoBrush)


def _line(p: QPainter, x1, y1, x2, y2):
    p.drawLine(QPointF(x1, y1), QPointF(x2, y2))


def _chevron(p, cx, cy, size=3.0, down=True):
    path = QPainterPath()
    if down:
        path.moveTo(cx - size, cy - size / 2)
        path.lineTo(cx, cy + size / 2)
        path.lineTo(cx + size, cy - size / 2)
    else:
        path.moveTo(cx - size / 2, cy - size)
        path.lineTo(cx + size / 2, cy)
        path.lineTo(cx - size / 2, cy + size)
    p.drawPath(path)


def _g_button(p, c):
    _rr(p, 1.5, 4.5, 13, 7, 3.5)
    _line(p, 5.5, 8, 10.5, 8)


def _g_toolbutton(p, c):
    _rr(p, 3.5, 3.5, 9, 9, 2.5)
    _fill(p, c)
    p.drawEllipse(QPointF(8, 8), 1.4, 1.4)


def _g_label(p, c):
    font = QFont(QGuiApplication.font())
    font.setPixelSize(11)
    font.setBold(True)
    p.setFont(font)
    p.drawText(QRectF(0, 1, 16, 14), Qt.AlignCenter, "Aa")


def _g_lineedit(p, c):
    _rr(p, 1.5, 4.5, 13, 7, 1.8)
    _line(p, 4.5, 6.5, 4.5, 9.5)


def _g_text(p, c):
    _rr(p, 1.5, 2.5, 13, 11, 1.8)
    _line(p, 4, 5.5, 12, 5.5)
    _line(p, 4, 8, 12, 8)
    _line(p, 4, 10.5, 9, 10.5)


def _g_spin(p, c):
    _rr(p, 1.5, 4, 13, 8, 1.8)
    _line(p, 10, 4, 10, 12)
    path = QPainterPath()
    path.moveTo(11, 7)
    path.lineTo(12.2, 5.8)
    path.lineTo(13.4, 7)
    path.moveTo(11, 9)
    path.lineTo(12.2, 10.2)
    path.lineTo(13.4, 9)
    p.drawPath(path)


def _g_combo(p, c):
    _rr(p, 1.5, 4.5, 13, 7, 1.8)
    _chevron(p, 11.2, 8, 1.6)


def _g_check(p, c):
    _rr(p, 2.5, 2.5, 11, 11, 2.5)
    path = QPainterPath()
    path.moveTo(5, 8.2)
    path.lineTo(7.2, 10.3)
    path.lineTo(11, 5.8)
    p.drawPath(path)


def _g_radio(p, c):
    p.drawEllipse(QPointF(8, 8), 5.5, 5.5)
    _fill(p, c)
    p.drawEllipse(QPointF(8, 8), 2.2, 2.2)


def _g_date(p, c):
    _rr(p, 2, 3, 12, 11, 1.8)
    _line(p, 2, 6.5, 14, 6.5)
    _line(p, 5, 1.8, 5, 4)
    _line(p, 11, 1.8, 11, 4)
    _fill(p, c)
    p.drawEllipse(QPointF(6, 10), 0.9, 0.9)
    p.drawEllipse(QPointF(10, 10), 0.9, 0.9)


def _g_time(p, c):
    p.drawEllipse(QPointF(8, 8), 6, 6)
    _line(p, 8, 8, 8, 4.5)
    _line(p, 8, 8, 10.5, 9.5)


def _g_slider(p, c):
    _line(p, 1.5, 8, 14.5, 8)
    _fill(p, QColor(255, 255, 255, 0))
    _fill(p, c)
    p.drawEllipse(QPointF(6, 8), 2.4, 2.4)


def _g_progress(p, c):
    _rr(p, 1.5, 5.5, 13, 5, 2.5)
    _fill(p, c)
    _rr(p, 1.5, 5.5, 7.5, 5, 2.5)


def _g_buttonbox(p, c):
    _rr(p, 1, 5.5, 6.5, 5, 2.5)
    _fill(p, c)
    _rr(p, 8.5, 5.5, 6.5, 5, 2.5)


def _g_group(p, c):
    path = QPainterPath()
    path.moveTo(5, 3.5)
    path.lineTo(2.5, 3.5)
    path.arcTo(QRectF(1.5, 3.5, 2, 2), 90, 90)
    path.lineTo(1.5, 13.5)
    path.lineTo(14.5, 13.5)
    path.lineTo(14.5, 3.5)
    path.lineTo(11, 3.5)
    p.drawPath(path)
    _line(p, 6, 3.5, 10, 3.5)


def _g_frame(p, c):
    _rr(p, 2, 2.5, 12, 11, 2)


def _g_widget(p, c):
    pen = p.pen()
    pen.setStyle(Qt.DashLine)
    pen.setDashPattern([2, 2])
    p.setPen(pen)
    _rr(p, 2, 2.5, 12, 11, 2)


def _g_tabs(p, c):
    path = QPainterPath()
    path.moveTo(1.5, 13.5)
    path.lineTo(1.5, 3)
    path.lineTo(7, 3)
    path.lineTo(7, 5.5)
    path.lineTo(14.5, 5.5)
    path.lineTo(14.5, 13.5)
    path.closeSubpath()
    p.drawPath(path)
    _line(p, 9, 3, 12, 3)


def _g_stack(p, c):
    _rr(p, 4.5, 1.5, 10, 9, 1.8)
    _fill(p, QColor(0, 0, 0, 0))
    _rr(p, 1.5, 5.5, 10, 9, 1.8)


def _g_scroll(p, c):
    _rr(p, 1.5, 2, 13, 12, 1.8)
    _line(p, 11.5, 2, 11.5, 14)
    _fill(p, c)
    _rr(p, 12.3, 4, 1.5, 4, 0.7)


def _g_splitter(p, c):
    _rr(p, 1.5, 2.5, 5.5, 11, 1.5)
    _rr(p, 9, 2.5, 5.5, 11, 1.5)
    _fill(p, c)
    p.drawEllipse(QPointF(8, 6.5), 0.7, 0.7)
    p.drawEllipse(QPointF(8, 9.5), 0.7, 0.7)


def _g_list(p, c):
    for y in (4, 8, 12):
        _fill(p, c)
        p.drawEllipse(QPointF(3, y), 0.9, 0.9)
        _line(p, 6, y, 14, y)


def _g_table(p, c):
    _rr(p, 1.5, 2.5, 13, 11, 1.5)
    _line(p, 1.5, 6.2, 14.5, 6.2)
    _line(p, 1.5, 9.8, 14.5, 9.8)
    _line(p, 6, 2.5, 6, 13.5)
    _line(p, 10.3, 2.5, 10.3, 13.5)


def _g_tree(p, c):
    _line(p, 3.5, 3, 3.5, 12)
    _line(p, 3.5, 7.5, 7, 7.5)
    _line(p, 3.5, 12, 7, 12)
    _fill(p, c)
    p.drawEllipse(QPointF(3.5, 3), 1.3, 1.3)
    _line(p, 9, 7.5, 14, 7.5)
    _line(p, 9, 12, 14, 12)


def _g_vbox(p, c):
    for y in (2.5, 6.5, 10.5):
        _rr(p, 2.5, y, 11, 3, 1)


def _g_hbox(p, c):
    for x in (2.5, 6.5, 10.5):
        _rr(p, x, 2.5, 3, 11, 1)


def _g_grid(p, c):
    for x in (2.5, 9):
        for y in (2.5, 9):
            _rr(p, x, y, 4.5, 4.5, 1)


def _g_form(p, c):
    for y in (3, 9):
        _line(p, 2, y + 2, 5, y + 2)
        _rr(p, 7, y, 7.5, 4, 1)


def _g_hspacer(p, c):
    path = QPainterPath()
    path.moveTo(1.5, 5)
    path.lineTo(1.5, 11)
    path.moveTo(14.5, 5)
    path.lineTo(14.5, 11)
    path.moveTo(1.5, 8)
    for index, x in enumerate((3.5, 5.5, 7.5, 9.5, 11.5, 13.5)):
        path.lineTo(x, 6 if index % 2 == 0 else 10)
    path.lineTo(14.5, 8)
    p.drawPath(path)


def _g_vspacer(p, c):
    p.translate(16, 0)
    p.rotate(90)
    _g_hspacer(p, c)


def _g_mainwindow(p, c):
    _rr(p, 1.5, 2, 13, 12, 2)
    _line(p, 1.5, 5, 14.5, 5)
    _line(p, 3.5, 7.5, 6, 7.5)
    _line(p, 7.5, 7.5, 10, 7.5)


def _g_dialog(p, c):
    _rr(p, 1.5, 2, 13, 12, 2)
    _line(p, 1.5, 5, 14.5, 5)
    _fill(p, c)
    _rr(p, 9, 10, 4, 2, 1)


def _g_menubar(p, c):
    _rr(p, 1.5, 4.5, 13, 7, 1.5)
    _line(p, 3.5, 8, 6, 8)
    _line(p, 7.5, 8, 10, 8)


def _g_menu(p, c):
    _rr(p, 3, 1.5, 10, 13, 1.8)
    for y in (5, 8, 11):
        _line(p, 5.5, y, 10.5, y)


def _g_toolbar(p, c):
    _rr(p, 1.5, 5, 13, 6, 1.5)
    _fill(p, c)
    for x in (4, 7.5, 11):
        _rr(p, x - 1, 7, 2, 2, 0.5)


def _g_statusbar(p, c):
    _rr(p, 1.5, 2, 13, 12, 2)
    _line(p, 1.5, 11, 14.5, 11)


def _g_action(p, c):
    path = QPainterPath()
    path.moveTo(9, 1.5)
    path.lineTo(4, 9)
    path.lineTo(8, 9)
    path.lineTo(7, 14.5)
    path.lineTo(12, 7)
    path.lineTo(8, 7)
    path.closeSubpath()
    p.drawPath(path)


def _g_custom(p, c):
    font = QFont(QGuiApplication.font())
    font.setPixelSize(11)
    font.setBold(True)
    p.setFont(font)
    p.drawText(QRectF(0, 0, 16, 15), Qt.AlignCenter, "{ }")


def _g_plus(p, c):
    _line(p, 8, 3, 8, 13)
    _line(p, 3, 8, 13, 8)


def _g_minus(p, c):
    _line(p, 3, 8, 13, 8)


def _g_close(p, c):
    _line(p, 4, 4, 12, 12)
    _line(p, 12, 4, 4, 12)


def _g_search(p, c):
    p.drawEllipse(QPointF(7, 7), 4.2, 4.2)
    _line(p, 10.2, 10.2, 13.5, 13.5)


def _g_chev_down(p, c):
    _chevron(p, 8, 8, 3.2)


def _g_chev_right(p, c):
    _chevron(p, 8, 8, 3.2, down=False)


def _g_chev_left(p, c):
    p.translate(16, 0)
    p.scale(-1, 1)
    _chevron(p, 8, 8, 3.2, down=False)


def _g_check_mark(p, c):
    pen = p.pen()
    pen.setWidthF(2.0)
    p.setPen(pen)
    path = QPainterPath()
    path.moveTo(3.5, 8.5)
    path.lineTo(6.5, 11.5)
    path.lineTo(12.5, 4.5)
    p.drawPath(path)


def _g_undo(p, c):
    path = QPainterPath()
    path.moveTo(4, 9)
    path.arcTo(QRectF(4, 4, 9, 9), 180, -200)
    p.drawPath(path)
    _line(p, 4, 9, 2.5, 6.5)
    _line(p, 4, 9, 6.8, 7.8)


def _g_redo(p, c):
    p.translate(16, 0)
    p.scale(-1, 1)
    _g_undo(p, c)


def _g_play(p, c):
    path = QPainterPath()
    path.moveTo(5, 3)
    path.lineTo(13, 8)
    path.lineTo(5, 13)
    path.closeSubpath()
    _fill(p, c)
    p.drawPath(path)


def _g_save(p, c):
    path = QPainterPath()
    path.moveTo(2.5, 2.5)
    path.lineTo(11, 2.5)
    path.lineTo(13.5, 5)
    path.lineTo(13.5, 13.5)
    path.lineTo(2.5, 13.5)
    path.closeSubpath()
    p.drawPath(path)
    _rr(p, 5, 9, 6, 4.5, 0.5)
    _line(p, 5, 2.5, 5, 5.5)
    _line(p, 5, 5.5, 10, 5.5)


def _g_database(p, c):
    p.drawEllipse(QRectF(3, 2, 10, 3.5))
    path = QPainterPath()
    path.moveTo(3, 3.75)
    path.lineTo(3, 12.25)
    path.arcTo(QRectF(3, 10.5, 10, 3.5), 180, 180)
    path.lineTo(13, 3.75)
    p.drawPath(path)
    path = QPainterPath()
    path.moveTo(3, 8)
    path.arcTo(QRectF(3, 6.25, 10, 3.5), 180, 180)
    p.drawPath(path)


def _g_file(p, c):
    path = QPainterPath()
    path.moveTo(3.5, 1.5)
    path.lineTo(9.5, 1.5)
    path.lineTo(12.5, 4.5)
    path.lineTo(12.5, 14.5)
    path.lineTo(3.5, 14.5)
    path.closeSubpath()
    p.drawPath(path)
    _line(p, 9.5, 1.5, 9.5, 4.5)
    _line(p, 9.5, 4.5, 12.5, 4.5)


def _g_folder(p, c):
    path = QPainterPath()
    path.moveTo(1.5, 4)
    path.lineTo(6, 4)
    path.lineTo(7.5, 5.5)
    path.lineTo(14.5, 5.5)
    path.lineTo(14.5, 13)
    path.lineTo(1.5, 13)
    path.closeSubpath()
    p.drawPath(path)


def _g_warning(p, c):
    path = QPainterPath()
    path.moveTo(8, 2)
    path.lineTo(14.5, 13.5)
    path.lineTo(1.5, 13.5)
    path.closeSubpath()
    p.drawPath(path)
    _line(p, 8, 6, 8, 9.5)
    _fill(p, c)
    p.drawEllipse(QPointF(8, 11.5), 0.6, 0.6)


def _g_dot(p, c):
    _fill(p, c)
    p.setPen(Qt.NoPen)
    p.drawEllipse(QPointF(8, 8), 3, 3)


def _g_wrap(p, c):
    pen = p.pen()
    pen.setStyle(Qt.DashLine)
    pen.setDashPattern([2, 2])
    p.setPen(pen)
    _rr(p, 1.5, 1.5, 13, 13, 2.5)
    pen.setStyle(Qt.SolidLine)
    p.setPen(pen)
    _rr(p, 4.5, 4.5, 7, 3, 1)
    _rr(p, 4.5, 9, 7, 3, 1)


def _g_width(p, c):
    _line(p, 2, 8, 14, 8)
    _line(p, 2, 5, 2, 11)
    _line(p, 14, 5, 14, 11)


def _g_two_widths(p, c):
    _rr(p, 1.5, 3, 5, 10, 1.5)
    _rr(p, 8.5, 3, 6, 10, 1.5)


def _g_text_size(p, c):
    font = QFont(QGuiApplication.font())
    font.setPixelSize(12)
    font.setBold(True)
    p.setFont(font)
    p.drawText(QRectF(0, 0, 9, 16), Qt.AlignCenter, "A")
    font.setPixelSize(8)
    p.setFont(font)
    p.drawText(QRectF(8, 2, 8, 14), Qt.AlignCenter, "A")


def _g_order(p, c):
    font = QFont(QGuiApplication.font())
    font.setPixelSize(8)
    font.setBold(True)
    p.setFont(font)
    p.drawEllipse(QPointF(4.5, 4.5), 3.2, 3.2)
    p.drawText(QRectF(1.3, 1.3, 6.4, 6.4), Qt.AlignCenter, "1")
    p.drawEllipse(QPointF(11.5, 11.5), 3.2, 3.2)
    p.drawText(QRectF(8.3, 8.3, 6.4, 6.4), Qt.AlignCenter, "2")
    _line(p, 7, 7, 9, 9)


def _g_link(p, c):
    _rr(p, 1.5, 5.5, 6.5, 5, 2.5)
    _rr(p, 8, 5.5, 6.5, 5, 2.5)
    _line(p, 5.5, 8, 10.5, 8)


def _g_design(p, c):
    path = QPainterPath()
    path.moveTo(3, 2.5)
    path.lineTo(12.5, 8)
    path.lineTo(8.3, 9.2)
    path.lineTo(6.2, 13.3)
    path.closeSubpath()
    p.drawPath(path)


def _g_sun(p, c):
    p.drawEllipse(QPointF(8, 8), 3, 3)
    for index in range(8):
        angle = index * math.pi / 4
        _line(p, 8 + 5 * math.cos(angle), 8 + 5 * math.sin(angle), 8 + 6.5 * math.cos(angle), 8 + 6.5 * math.sin(angle))


def _g_moon(p, c):
    path = QPainterPath()
    path.addEllipse(QPointF(8, 8), 5.5, 5.5)
    cut = QPainterPath()
    cut.addEllipse(QPointF(11, 5.5), 4.5, 4.5)
    p.drawPath(path.subtracted(cut))


def _g_more(p, c):
    _fill(p, c)
    p.setPen(Qt.NoPen)
    for x in (3.5, 8, 12.5):
        p.drawEllipse(QPointF(x, 8), 1.3, 1.3)


def _g_grip(p, c):
    _fill(p, c)
    p.setPen(Qt.NoPen)
    for x in (6, 10):
        for y in (4, 8, 12):
            p.drawEllipse(QPointF(x, y), 1.0, 1.0)


GLYPHS = {
    "QPushButton": _g_button,
    "QCommandLinkButton": _g_button,
    "QToolButton": _g_toolbutton,
    "QLabel": _g_label,
    "QLineEdit": _g_lineedit,
    "QKeySequenceEdit": _g_lineedit,
    "QPlainTextEdit": _g_text,
    "QTextEdit": _g_text,
    "QTextBrowser": _g_text,
    "QSpinBox": _g_spin,
    "QDoubleSpinBox": _g_spin,
    "QComboBox": _g_combo,
    "QFontComboBox": _g_combo,
    "QCheckBox": _g_check,
    "QRadioButton": _g_radio,
    "QDateEdit": _g_date,
    "QDateTimeEdit": _g_date,
    "QCalendarWidget": _g_date,
    "QTimeEdit": _g_time,
    "QSlider": _g_slider,
    "QDial": _g_time,
    "QScrollBar": _g_slider,
    "QProgressBar": _g_progress,
    "QDialogButtonBox": _g_buttonbox,
    "QGroupBox": _g_group,
    "QFrame": _g_frame,
    "QLCDNumber": _g_frame,
    "QWidget": _g_widget,
    "QTabWidget": _g_tabs,
    "QToolBox": _g_tabs,
    "QStackedWidget": _g_stack,
    "QScrollArea": _g_scroll,
    "QSplitter": _g_splitter,
    "QListWidget": _g_list,
    "QListView": _g_list,
    "QTableWidget": _g_table,
    "QTableView": _g_table,
    "QTreeWidget": _g_tree,
    "QTreeView": _g_tree,
    "QColumnView": _g_table,
    "QVBoxLayout": _g_vbox,
    "QHBoxLayout": _g_hbox,
    "QGridLayout": _g_grid,
    "QFormLayout": _g_form,
    "Qt::Horizontal": _g_hspacer,
    "Qt::Vertical": _g_vspacer,
    "Spacer": _g_hspacer,
    "QMainWindow": _g_mainwindow,
    "QDialog": _g_dialog,
    "QWizard": _g_dialog,
    "QWizardPage": _g_widget,
    "QMenuBar": _g_menubar,
    "QMenu": _g_menu,
    "QToolBar": _g_toolbar,
    "QStatusBar": _g_statusbar,
    "QDockWidget": _g_stack,
    "Action": _g_action,
    "custom": _g_custom,
    "plus": _g_plus,
    "minus": _g_minus,
    "close": _g_close,
    "search": _g_search,
    "chevron-down": _g_chev_down,
    "chevron-right": _g_chev_right,
    "chevron-left": _g_chev_left,
    "check-mark": _g_check_mark,
    "undo": _g_undo,
    "redo": _g_redo,
    "play": _g_play,
    "save": _g_save,
    "database": _g_database,
    "file": _g_file,
    "folder": _g_folder,
    "warning": _g_warning,
    "dot": _g_dot,
    "wrap": _g_wrap,
    "width": _g_width,
    "two-widths": _g_two_widths,
    "text-size": _g_text_size,
    "order": _g_order,
    "link": _g_link,
    "design": _g_design,
    "sun": _g_sun,
    "moon": _g_moon,
    "more": _g_more,
    "grip": _g_grip,
}


def glyph_for_class(class_name: str) -> str:
    if class_name in GLYPHS:
        return class_name
    short = class_name.split("::")[-1]
    if short in GLYPHS:
        return short
    return "custom"


def paint_glyph(painter: QPainter, name: str, rect: QRectF, color) -> None:
    """Paint a glyph into rect (any size); used by delegates and the overlay."""
    func = GLYPHS.get(name) or GLYPHS[glyph_for_class(name)]
    color = QColor(color)
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.translate(rect.topLeft())
    painter.scale(rect.width() / 16.0, rect.height() / 16.0)
    painter.setPen(_pen(color))
    painter.setBrush(Qt.NoBrush)
    func(painter, color)
    painter.restore()


def pixmap(name: str, color, size: int = 16, ratio: float = 2.0) -> QPixmap:
    key = ("pix", name, QColor(color).name(QColor.HexArgb), size, ratio)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    pix = QPixmap(int(size * ratio), int(size * ratio))
    pix.fill(Qt.transparent)
    pix.setDevicePixelRatio(ratio)
    painter = QPainter(pix)
    paint_glyph(painter, name, QRectF(0, 0, size, size), color)
    painter.end()
    _CACHE[key] = pix
    return pix


def icon(name: str, color, size: int = 16) -> QIcon:
    key = ("icon", name, QColor(color).name(QColor.HexArgb), size)
    cached = _CACHE.get(key)
    if cached is None:
        cached = QIcon(pixmap(name, color, size))
        _CACHE[key] = cached
    return cached


def qss_asset(name: str, color) -> str:
    """Render a glyph to a PNG for style sheet url(), once per colour."""
    _ASSET_DIR.mkdir(parents=True, exist_ok=True)
    tag = QColor(color).name().lstrip("#")
    path = _ASSET_DIR / f"{name}-{tag}.png"
    if not path.exists():
        pixmap(name, color, 16, 2.0).save(str(path))
    return path.as_posix()
