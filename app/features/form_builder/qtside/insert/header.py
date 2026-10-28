"""The Insert pane header: an overline row that toggles the pane, with buttons on the right."""

from __future__ import annotations

from typing import Callable, List

from app.qt.QtCore import QEvent, Qt
from app.qt.QtWidgets import QHBoxLayout, QLabel, QToolButton, QWidget

from app.qt.qt_compat import event_pos


class PaneHeader(QWidget):
    def __init__(self, title: str, parent: QWidget, on_toggle: Callable[[], None]) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.sectionHeader")
        self.setAccessibleName(title)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._on_toggle = on_toggle
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 8, 12, 8)
        row.setSpacing(4)
        self.title = QLabel(title.upper(), self)
        self.title.setObjectName("formBuilder.sectionTitle")
        self.title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        row.addWidget(self.title, 1)
        self.extra: List[QToolButton] = []

    def add_extra(
        self,
        text: str,
        tip: str,
        name: str = "formBuilder.sectionExtra",
        enabled: bool = False,
    ) -> QToolButton:
        """A button at the right of the header. The outline's are disabled; the Insert search and more menu are live."""
        button = QToolButton(self)
        button.setObjectName(name)
        button.setText(text)
        button.setToolTip(tip)
        button.setAccessibleName(tip)
        button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        button.setAutoRaise(True)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        button.setEnabled(enabled)
        button.setMinimumSize(24, 24)
        layout = self.layout()
        assert layout is not None
        layout.addWidget(button)
        self.extra.append(button)
        return button

    def mousePressEvent(self, event: QEvent) -> None:  # type: ignore[override]
        if getattr(event, "button")() == Qt.MouseButton.LeftButton:
            pos = event_pos(event)
            for button in self.extra:
                if button.geometry().contains(pos):
                    super().mousePressEvent(event)  # type: ignore[arg-type]
                    return
            self._on_toggle()
            event.accept()  # type: ignore[attr-defined]
            return
        super().mousePressEvent(event)  # type: ignore[arg-type]

    def keyPressEvent(self, event: QEvent) -> None:  # type: ignore[override]
        key = getattr(event, "key")()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self._on_toggle()
            event.accept()  # type: ignore[attr-defined]
            return
        super().keyPressEvent(event)  # type: ignore[arg-type]
