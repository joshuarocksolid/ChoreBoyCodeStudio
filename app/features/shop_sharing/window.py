"""Window-scoped shop sharing: status chip, one-time prompt bar, reconnect on activate, one listener."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from app.qt.QtCore import QEvent, QObject, Qt, Signal
from app.qt.QtGui import QMouseEvent
from app.qt.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from app.features.shop_sharing.model import DiscoveredShop, SharingChanged, ShopStatus
from app.features.shop_sharing.presenter import (
    KEEP_TEXT,
    USE_TEXT,
    PromptCopy,
    chip_view,
    prompt_copy,
)
from app.features.shop_sharing.service import ShopSharingService
from app.features.shop_sharing.settings_group import ShopSharingGroup


@dataclass(frozen=True)
class ShopSharingWindowPorts:
    """What the window does when sharing moves the documents. Lambdas resolve window fields lazily."""

    reload_settings: Callable[[], None]
    restore_console_history: Callable[[], None]
    refresh_open_recent: Callable[[], None]
    refresh_welcome: Callable[[], None]
    open_settings: Callable[[], None]


class ShopSharingShell(QObject):
    """Bound at FeatureSpec.install as ``window._shop_sharing``. Widgets come later in ``build()``.

    ``service`` None (explicit state_root): every method is a no-op and ``settings_group()`` is None.
    GUI thread only. The listener is removed on ``window.destroyed`` because the service outlives test windows.
    """

    def __init__(
        self,
        window: QWidget,
        service: Optional[ShopSharingService],
        ports: ShopSharingWindowPorts,
    ) -> None:
        super().__init__(window)
        self._window = window
        self._service = service
        self._ports = ports
        self._built = False
        self._chip: Optional[_ClickableStatusLabel] = None
        self._prompt: Optional[_PromptBar] = None

    def build(
        self,
        *,
        status_bar: QStatusBar,
        center_layout: QVBoxLayout,
        center_stack: QWidget,
    ) -> None:
        """Once. A second call is a no-op."""
        if self._service is None or self._built:
            return
        self._built = True
        chip = _ClickableStatusLabel(status_bar)
        chip.setObjectName("shell.status.shopSharing")
        chip.setCursor(Qt.PointingHandCursor)
        chip.clicked.connect(self._ports.open_settings)
        status_bar.addPermanentWidget(chip, 0)
        self._chip = chip
        self._render_chip(self._service.status())
        target = self._service.undecided_prompt_target()
        if target is not None:
            self._show_prompt(target, center_layout, center_stack)
        self._window.installEventFilter(self)
        unsubscribe = self._service.add_listener(self._on_sharing_changed)
        self._window.destroyed.connect(lambda *_args: unsubscribe())

    def settings_group(self) -> Optional[ShopSharingGroup]:
        """A fresh group per Settings dialog, or None when sharing UI is hidden."""
        if self._service is None:
            return None
        return ShopSharingGroup(self._service)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        """Window activation probes the share. Never consumes the event."""
        if (
            self._service is not None
            and watched is self._window
            and event.type() == QEvent.WindowActivate
            and self._service.check_reconnect()
        ):
            self._render_chip(self._service.status())
        return False

    def _on_sharing_changed(self, event: SharingChanged) -> None:
        if self._service is None:
            return
        self._render_chip(event.status)
        if self._service.undecided_prompt_target() is None:
            self._dismiss_prompt()
        if not event.documents_reloaded:
            return
        self._ports.reload_settings()
        self._ports.restore_console_history()
        self._ports.refresh_open_recent()
        self._ports.refresh_welcome()

    def _render_chip(self, status: ShopStatus) -> None:
        chip = self._chip
        if chip is None:
            return
        view = chip_view(status)
        if view is None:
            chip.hide()
            return
        chip.setText(view.text)
        chip.setToolTip(view.tooltip)
        chip.setProperty("shopSharingSeverity", view.severity)
        _repolish(chip)
        chip.show()

    def _show_prompt(
        self,
        target: DiscoveredShop,
        center_layout: QVBoxLayout,
        center_stack: QWidget,
    ) -> None:
        bar = _PromptBar(prompt_copy(target))
        bar.use_clicked.connect(lambda target=target: self._use_shop(target))
        bar.keep_clicked.connect(lambda target=target: self._keep_local(target))
        index = center_layout.indexOf(center_stack)
        if index < 0:
            index = center_layout.count()
        center_layout.insertWidget(index, bar)
        self._prompt = bar

    def _use_shop(self, target: DiscoveredShop) -> None:
        if self._service is None or self._prompt is None:
            return
        result = self._service.turn_on(target.folder, via="prompt")
        if result.ok:
            return
        # A refused Use stays open so the reason is visible. Success closes through the listener.
        self._prompt.show_error(result.error)

    def _keep_local(self, target: DiscoveredShop) -> None:
        if self._service is None:
            return
        self._service.decline(target.folder)
        self._dismiss_prompt()

    def _dismiss_prompt(self) -> None:
        bar = self._prompt
        if bar is None:
            return
        self._prompt = None
        bar.hide()
        bar.deleteLater()


class _ClickableStatusLabel(QLabel):
    clicked = Signal()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class _PromptBar(QFrame):
    """objectName ``shell.shopPrompt``. Buttons ``shell.shopPrompt.use`` and ``.keep``."""

    use_clicked = Signal()
    keep_clicked = Signal()

    def __init__(self, copy: PromptCopy, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("shell.shopPrompt")
        headline = QLabel(copy.headline, self)
        headline.setProperty("shopPromptRole", "headline")
        question = QLabel(copy.question, self)
        question.setProperty("shopPromptRole", "question")
        question.setWordWrap(True)
        use = QPushButton(USE_TEXT, self)
        use.setObjectName("shell.shopPrompt.use")
        use.clicked.connect(self.use_clicked.emit)
        keep = QPushButton(KEEP_TEXT, self)
        keep.setObjectName("shell.shopPrompt.keep")
        keep.clicked.connect(self.keep_clicked.emit)
        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.addWidget(use)
        buttons.addWidget(keep)
        buttons.addStretch(1)
        self._note = QLabel(copy.note, self)
        self._note.setProperty("shopPromptRole", "note")
        self._note.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)
        layout.addWidget(headline)
        layout.addWidget(question)
        layout.addLayout(buttons)
        layout.addWidget(self._note)

    def show_error(self, text: str) -> None:
        """Replace the note with the refusal. The bar stays open."""
        self._note.setText(text)
        self._note.setProperty("shopPromptRole", "error")
        _repolish(self._note)


def _repolish(widget: QWidget) -> None:
    style = widget.style()
    if style is None:
        return
    style.unpolish(widget)
    style.polish(widget)
    widget.update()
