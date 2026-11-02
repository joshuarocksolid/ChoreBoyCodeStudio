"""Paint a short letter at the end of an explorer row from an in-memory lookup.

The delegate never reads the filesystem. Lookups are plain callables over a dict.
"""

from __future__ import annotations

from typing import Callable, Optional, Sequence

from app.qt.QtCore import Qt
from app.qt.QtGui import QColor, QPainter
from app.qt.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem, QWidget
from app.qt.qt_compat import enum_value

from app.shell.tree_item_roles import TREE_ROLE_RELATIVE_PATH


DecorationLookup = Callable[[str], Optional[tuple[str, str]]]

_SEVERITY_COLORS = {
    "ok": QColor("#1A7F37"),
    "info": QColor("#3D5A80"),
    "warn": QColor("#B45309"),
}


def decoration_at_paint(
    lookup: DecorationLookup,
    relative_path: str,
) -> Optional[tuple[str, str]]:
    """The only call the row painter makes. ``lookup`` must not touch disk."""
    if not relative_path:
        return None
    return lookup(relative_path)


class ExplorerDecorationDelegate(QStyledItemDelegate):
    """Draws the first lookup hit at the right edge of column 0."""

    def __init__(
        self,
        lookups: Sequence[DecorationLookup],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._lookups = lookups

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:  # type: ignore[no-untyped-def]
        super().paint(painter, option, index)
        if index.column() != 0:
            return
        path = index.data(TREE_ROLE_RELATIVE_PATH)
        if not path:
            return
        found: Optional[tuple[str, str]] = None
        for lookup in self._lookups:
            found = decoration_at_paint(lookup, str(path))
            if found:
                break
        if not found:
            return
        letter, severity = found
        painter.save()
        color = _SEVERITY_COLORS.get(severity, option.palette.text().color())
        if enum_value(option.state) & enum_value(QStyle.State_Selected):
            color = option.palette.highlightedText().color()
        painter.setPen(color)
        painter.drawText(
            option.rect.adjusted(0, 0, -8, 0),
            Qt.AlignRight | Qt.AlignVCenter,
            letter,
        )
        painter.restore()


__all__ = ["DecorationLookup", "ExplorerDecorationDelegate", "decoration_at_paint"]
