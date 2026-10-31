"""The quick-symbol row paints. ``kind_color_for`` takes theme tokens, not ``is_dark``."""

from __future__ import annotations

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.intelligence.outline_service import OutlineSymbol  # noqa: E402
from app.qt.QtCore import QRect  # noqa: E402
from app.qt.QtGui import QImage, QPainter  # noqa: E402
from app.qt.QtWidgets import QStyleOptionViewItem  # noqa: E402
from app.shell.outline.outline_icons import kind_color_for  # noqa: E402
from app.shell.quick_symbol_dialog import QuickSymbolDelegate, QuickSymbolRow, SymbolRole  # noqa: E402
from app.shell.theme_tokens import ShellThemeTokens  # noqa: E402
from app.qt.QtGui import QStandardItem, QStandardItemModel  # noqa: E402

pytestmark = pytest.mark.unit


def _tokens() -> ShellThemeTokens:
    return ShellThemeTokens(
        window_bg="#FFFFFF",
        panel_bg="#FFFFFF",
        editor_bg="#FFFFFF",
        text_primary="#111111",
        text_muted="#555555",
        border="#111111",
        accent="#0055AA",
        gutter_bg="#FFFFFF",
        gutter_text="#555555",
        line_highlight="#EEEEEE",
        icon_primary="#111111",
        icon_muted="#555555",
    )


def test_kind_color_for_does_not_take_is_dark() -> None:
    with pytest.raises(TypeError):
        kind_color_for("function", is_dark=True)  # type: ignore[call-arg]


def test_a_quick_symbol_row_paints(qapp: object) -> None:
    del qapp
    tokens = _tokens()
    assert kind_color_for("function", tokens)
    delegate = QuickSymbolDelegate(tokens)
    symbol = OutlineSymbol(
        name="on_okButton_clicked",
        qualified_name="SaleWindow.on_okButton_clicked",
        kind="function",
        line_number=12,
        end_line_number=14,
    )
    row = QuickSymbolRow(symbol, 0, frozenset())
    model = QStandardItemModel()
    item = QStandardItem()
    item.setData(row, int(SymbolRole))
    model.appendRow(item)
    image = QImage(240, 28, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    option = QStyleOptionViewItem()
    option.rect = QRect(0, 0, 240, 28)
    try:
        delegate.paint(painter, option, model.index(0, 0))
    finally:
        painter.end()
