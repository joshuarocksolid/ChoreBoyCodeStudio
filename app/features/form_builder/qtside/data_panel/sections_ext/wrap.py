"""Labels that take the width they are given and the height that width needs."""

from __future__ import annotations

from app.qt.QtCore import Qt
from app.qt.QtWidgets import QLabel


class WrappedLabel(QLabel):
    """Word wrap, with the height of the wrapped text. No fixed height."""

    def __init__(self, text: str = "", parent: object = None) -> None:
        super().__init__(text, parent)  # type: ignore[arg-type]
        self.setWordWrap(True)
        self.setMinimumWidth(0)

    def resizeEvent(self, event: object) -> None:  # noqa: N802
        super().resizeEvent(event)  # type: ignore[arg-type]
        width = self.width()
        if width <= 0:
            return
        height = self.heightForWidth(width)
        if height > 0 and self.minimumHeight() != height:
            self.setMinimumHeight(height)
            self.updateGeometry()


def show_elided(label: QLabel, full: str, width: int) -> None:
    """Show ``full`` cut at the right. The tooltip is the whole string."""

    label.setToolTip(full)
    if width <= 0:
        label.setText(full)
        return
    shown = label.fontMetrics().elidedText(full, Qt.TextElideMode.ElideRight, width)
    if label.text() != shown:
        label.setText(shown)
