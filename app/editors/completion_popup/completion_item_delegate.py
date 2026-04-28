"""Custom delegate that renders one completion row.

Layout per row::

    [icon] label  signature                                       origin

* ``[icon]`` is a 22px square chip painted in the kind accent color with the
  kind glyph centered.
* ``label`` uses the primary text color; matched characters from the prefix
  are drawn bold.
* ``signature`` (parameters / detail) is muted and elided right.
* ``origin`` is a right-aligned badge showing ``engine`` or ``source``.
"""

from __future__ import annotations

from PySide2.QtCore import QModelIndex, QPointF, QRect, QRectF, QSize, Qt
from PySide2.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QPainter,
    QPen,
    QPalette,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextOption,
)
from PySide2.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem

from app.editors.completion_popup.completion_item_model import (
    ItemRole,
    KindStyleRole,
    MatchRangesRole,
)
from app.editors.completion_popup.completion_kind_style import KindGlyphStyle
from app.intelligence.completion_models import CompletionItem
from app.shell.theme_tokens import ShellThemeTokens


_ROW_HEIGHT = 24
_ICON_SIZE = 18
_ICON_PADDING_LEFT = 6
_ICON_PADDING_RIGHT = 8
_RIGHT_PADDING = 8
_GAP_LABEL_SIGNATURE = 8
_GAP_SIGNATURE_ORIGIN = 12


class CompletionItemDelegate(QStyledItemDelegate):
    """Paints a single completion row with icon, label, signature, origin."""

    def __init__(self, parent: object | None = None) -> None:
        super().__init__(parent)
        self._tokens: ShellThemeTokens | None = None
        self._color_text: QColor = QColor("#212529")
        self._color_muted: QColor = QColor("#6C757D")
        self._color_selected_bg: QColor = QColor("#D0E2FF")
        self._color_hover_bg: QColor = QColor("#E9ECEF")
        self._color_alt_bg: QColor = QColor(0, 0, 0, 0)
        self._color_badge_bg: QColor = QColor("#E9ECEF")
        self._color_badge_text: QColor = QColor("#6C757D")

    def apply_theme(self, tokens: ShellThemeTokens) -> None:
        """Refresh cached painter colors from the supplied theme tokens."""
        self._tokens = tokens
        self._color_text = QColor(tokens.text_primary or "#212529")
        self._color_muted = QColor(tokens.text_muted or "#6C757D")
        self._color_selected_bg = QColor(tokens.tree_selected_bg or "#D0E2FF")
        self._color_hover_bg = QColor(tokens.tree_hover_bg or "#E9ECEF")
        self._color_alt_bg = QColor(tokens.row_alt_bg) if tokens.row_alt_bg else QColor(0, 0, 0, 0)
        self._color_badge_bg = QColor(tokens.badge_bg or "#E9ECEF")
        self._color_badge_text = QColor(tokens.text_muted or "#6C757D")

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:  # noqa: N802
        return QSize(option.rect.width() if option.rect.width() > 0 else 320, _ROW_HEIGHT)

    def paint(  # noqa: C901 - render path with multiple regions
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> None:
        item = index.data(ItemRole)
        if not isinstance(item, CompletionItem):
            super().paint(painter, option, index)
            return

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        rect = QRect(option.rect)
        is_selected = bool(option.state & QStyle.State_Selected)
        is_hovered = bool(option.state & QStyle.State_MouseOver) and not is_selected

        if is_selected:
            painter.fillRect(rect, self._color_selected_bg)
        elif is_hovered:
            painter.fillRect(rect, self._color_hover_bg)
        elif index.row() % 2 == 1 and self._color_alt_bg.alpha() > 0:
            painter.fillRect(rect, self._color_alt_bg)

        kind_style = index.data(KindStyleRole)
        cursor_x = rect.x() + _ICON_PADDING_LEFT
        if isinstance(kind_style, KindGlyphStyle):
            self._paint_kind_chip(painter, rect, cursor_x, kind_style)
        cursor_x += _ICON_SIZE + _ICON_PADDING_RIGHT

        right_edge = rect.right() - _RIGHT_PADDING
        origin_text = self._origin_text(item)
        font_metrics = QFontMetrics(option.font)

        if origin_text:
            badge_width = font_metrics.horizontalAdvance(origin_text) + 12
            badge_height = font_metrics.height() + 2
            badge_rect = QRect(
                right_edge - badge_width,
                rect.y() + (rect.height() - badge_height) // 2,
                badge_width,
                badge_height,
            )
            self._paint_origin_badge(painter, badge_rect, origin_text, option.font)
            right_edge = badge_rect.left() - _GAP_SIGNATURE_ORIGIN

        text_top = rect.y()
        text_height = rect.height()

        signature_text = item.signature or item.detail or ""
        signature_width = 0
        if signature_text:
            max_signature_width = max(0, (right_edge - cursor_x) // 2)
            elided_signature = font_metrics.elidedText(
                signature_text, Qt.ElideRight, max_signature_width
            )
            signature_width = font_metrics.horizontalAdvance(elided_signature)
            sig_rect = QRect(
                right_edge - signature_width,
                text_top,
                signature_width,
                text_height,
            )
            painter.setPen(QPen(self._color_muted))
            painter.setFont(option.font)
            painter.drawText(sig_rect, Qt.AlignVCenter | Qt.AlignRight, elided_signature)
            right_edge = sig_rect.left() - _GAP_LABEL_SIGNATURE

        label_max_width = max(0, right_edge - cursor_x)
        label_rect = QRect(cursor_x, text_top, label_max_width, text_height)
        match_ranges = index.data(MatchRangesRole) or []
        self._paint_label(
            painter,
            label_rect,
            item.label,
            match_ranges,
            base_font=option.font,
            base_color=self._color_text,
        )

        painter.restore()

    def _paint_kind_chip(
        self,
        painter: QPainter,
        row_rect: QRect,
        x: int,
        style: KindGlyphStyle,
    ) -> None:
        chip_rect = QRect(
            x,
            row_rect.y() + (row_rect.height() - _ICON_SIZE) // 2,
            _ICON_SIZE,
            _ICON_SIZE,
        )
        accent = QColor(style.accent_color)
        # Background chip uses the accent color at low alpha so the glyph
        # remains legible in both light and dark themes.
        chip_bg = QColor(accent)
        chip_bg.setAlpha(48)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(chip_bg))
        painter.drawRoundedRect(QRectF(chip_rect), 4, 4)

        glyph_font = QFont(painter.font())
        glyph_font.setBold(True)
        glyph_font.setPointSizeF(max(8.0, glyph_font.pointSizeF() - 1.0))
        painter.setFont(glyph_font)
        painter.setPen(QPen(accent))
        painter.drawText(chip_rect, Qt.AlignCenter, style.glyph)

    def _paint_label(
        self,
        painter: QPainter,
        rect: QRect,
        label: str,
        match_ranges: list[tuple[int, int]],
        *,
        base_font: QFont,
        base_color: QColor,
    ) -> None:
        if rect.width() <= 0 or not label:
            return

        metrics = QFontMetrics(base_font)
        # Elide first so the document never has more glyphs than the row can
        # actually paint; then format the visible substring.
        if metrics.horizontalAdvance(label) > rect.width():
            visible_text = metrics.elidedText(label, Qt.ElideRight, rect.width())
        else:
            visible_text = label

        document = QTextDocument()
        document.setDefaultFont(base_font)
        document.setDocumentMargin(0)
        # Disable wrapping; the delegate guarantees one visual line per row.
        text_option = QTextOption()
        text_option.setWrapMode(QTextOption.NoWrap)
        document.setDefaultTextOption(text_option)
        document.setTextWidth(-1)
        document.setPlainText(visible_text)

        cursor = QTextCursor(document)
        cursor.select(QTextCursor.Document)
        base_format = QTextCharFormat()
        base_format.setForeground(base_color)
        cursor.mergeCharFormat(base_format)

        if match_ranges:
            highlight_format = QTextCharFormat()
            highlight_font = QFont(base_font)
            highlight_font.setBold(True)
            highlight_format.setFont(highlight_font)
            highlight_format.setForeground(base_color)
            visible_len = len(visible_text)
            for start, length in match_ranges:
                if length <= 0 or start >= visible_len:
                    continue
                end = min(start + length, visible_len)
                cursor.setPosition(start)
                cursor.setPosition(end, QTextCursor.KeepAnchor)
                cursor.mergeCharFormat(highlight_format)

        painter.save()
        block_height = metrics.height()
        y_offset = rect.y() + max(0, (rect.height() - block_height) // 2)
        painter.translate(QPointF(rect.x(), y_offset))
        document.drawContents(painter)
        painter.restore()

    def _paint_origin_badge(
        self,
        painter: QPainter,
        rect: QRect,
        text: str,
        font: QFont,
    ) -> None:
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(self._color_badge_bg))
        painter.drawRoundedRect(QRectF(rect), 3, 3)
        painter.setPen(QPen(self._color_badge_text))
        badge_font = QFont(font)
        badge_font.setPointSizeF(max(7.5, font.pointSizeF() - 1.0))
        painter.setFont(badge_font)
        painter.drawText(rect, Qt.AlignCenter, text)

    @staticmethod
    def _origin_text(item: CompletionItem) -> str:
        engine = (item.engine or "").strip()
        if engine:
            return engine
        source = (item.source or "").strip()
        if source:
            return source
        return ""

    @staticmethod
    def row_height() -> int:
        return _ROW_HEIGHT
