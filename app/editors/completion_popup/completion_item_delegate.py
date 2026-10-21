"""Paints one completion row: kind chip, full name, muted short type.

Names are never elided; the list is sized to fit the widest name.
Matched characters are drawn bold in the accent color.
"""

from __future__ import annotations

from PySide2.QtCore import QModelIndex, QRect, QRectF, QSize, Qt
from PySide2.QtGui import QBrush, QColor, QFont, QFontMetrics, QPainter, QPen
from PySide2.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem

from app.editors.completion_popup.completion_item_model import (
    ItemRole,
    KindStyleRole,
    MatchPositionsRole,
    ShortTypeRole,
)
from app.editors.completion_popup.completion_kind_style import KindGlyphStyle
from app.intelligence.completion_matcher import is_private_name
from app.intelligence.completion_models import CompletionItem
from app.shell.theme_tokens import ShellThemeTokens

ROW_HEIGHT = 22
CHIP_SIZE = 16
CHIP_LEFT = 6
CHIP_GAP = 8
TYPE_GAP = 16
RIGHT_PADDING = 8


class CompletionItemDelegate(QStyledItemDelegate):
    """Row painter for :class:`CompletionListView`."""

    def __init__(self, parent: object | None = None) -> None:
        super().__init__(parent)
        self._color_text = QColor("#212529")
        self._color_muted = QColor("#5A6168")
        self._color_accent = QColor("#3366FF")
        self._color_selected_bg = QColor("#D0E2FF")
        self._color_hover_bg = QColor("#EEF1F5")
        self._color_chip_text = QColor("#FFFFFF")

    def apply_theme(self, tokens: ShellThemeTokens) -> None:
        self._color_text = QColor(tokens.text_primary)
        self._color_muted = QColor(tokens.text_muted)
        self._color_accent = QColor(tokens.accent)
        self._color_selected_bg = QColor(tokens.tree_selected_bg)
        self._color_hover_bg = QColor(tokens.tree_hover_bg)
        self._color_chip_text = QColor(tokens.popup_bg or tokens.panel_bg or "#FFFFFF")

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:  # noqa: N802
        return QSize(option.rect.width() if option.rect.width() > 0 else 240, ROW_HEIGHT)

    @staticmethod
    def row_height() -> int:
        return ROW_HEIGHT

    @staticmethod
    def width_for(name_width: int, type_width: int) -> int:
        """Return the row width that fits a name and a short type without eliding."""

        return CHIP_LEFT + CHIP_SIZE + CHIP_GAP + name_width + TYPE_GAP + type_width + RIGHT_PADDING

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        item = index.data(ItemRole)
        if not isinstance(item, CompletionItem):
            super().paint(painter, option, index)
            return
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        rect = QRect(option.rect)
        if option.state & QStyle.State_Selected:
            painter.fillRect(rect, self._color_selected_bg)
        elif option.state & QStyle.State_MouseOver:
            painter.fillRect(rect, self._color_hover_bg)

        style = index.data(KindStyleRole)
        chip = QRect(rect.x() + CHIP_LEFT, rect.y() + (rect.height() - CHIP_SIZE) // 2, CHIP_SIZE, CHIP_SIZE)
        small = QFont(option.font)
        small.setPointSizeF(max(7.5, option.font.pointSizeF() - 1.0))
        if isinstance(style, KindGlyphStyle):
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor(style.accent_color)))
            painter.drawRoundedRect(QRectF(chip), 3, 3)
            glyph_font = QFont(small)
            glyph_font.setBold(True)
            painter.setFont(glyph_font)
            painter.setPen(QPen(self._color_chip_text))
            painter.drawText(chip, Qt.AlignCenter, style.glyph)

        short_type = str(index.data(ShortTypeRole) or "")
        small_metrics = QFontMetrics(small)
        type_width = small_metrics.horizontalAdvance(short_type) if short_type else 0
        type_left = rect.right() - RIGHT_PADDING - type_width

        positions = set(index.data(MatchPositionsRole) or ())
        regular = QFont(option.font)
        bold = QFont(option.font)
        bold.setBold(True)
        regular_metrics = QFontMetrics(regular)
        bold_metrics = QFontMetrics(bold)
        name_color = self._color_muted if is_private_name(item.label) else self._color_text
        x = chip.right() + 1 + CHIP_GAP
        baseline = rect.y() + (rect.height() + regular_metrics.ascent() - regular_metrics.descent()) // 2
        for offset, ch in enumerate(item.label):
            matched = offset in positions
            painter.setFont(bold if matched else regular)
            painter.setPen(QPen(self._color_accent if matched else name_color))
            painter.drawText(x, baseline, ch)
            x += (bold_metrics if matched else regular_metrics).horizontalAdvance(ch)

        if short_type and type_left > x + 4:
            painter.setFont(small)
            painter.setPen(QPen(self._color_muted))
            painter.drawText(
                QRect(type_left, rect.y(), type_width, rect.height()),
                Qt.AlignRight | Qt.AlignVCenter,
                short_type,
            )
        painter.restore()
