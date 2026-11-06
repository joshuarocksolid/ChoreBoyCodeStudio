"""Settings › General › Shop sharing. Global scope only. Nothing is applied until commit()."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from app.qt.QtWidgets import (
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.features.shop_sharing.model import SHOP_FOLDER_NAME, SharingMode, ShopStatus
from app.features.shop_sharing.presenter import (
    CHECKBOX_TEXT,
    GROUP_TITLE,
    HINT_TEXT,
    TurnOn,
    sharing_intent,
    shop_folder_for_pick,
    status_line,
)
from app.features.shop_sharing.service import ShopSharingService
from app.shell.file_dialogs import choose_existing_directory


class ShopSharingGroup(QGroupBox):
    """objectName ``shell.settings.shopSharing``.

    Children: ``.enabled``, ``.folder``, ``.change``, ``.status``, ``.error``.
    The hint label carries ``shopSharingRole="hint"``.
    """

    def __init__(
        self,
        service: ShopSharingService,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(GROUP_TITLE, parent)
        self.setObjectName("shell.settings.shopSharing")
        self._service = service
        self._now = now
        self._folder = Path.home() / "share" / SHOP_FOLDER_NAME

        self._enabled = QCheckBox(CHECKBOX_TEXT, self)
        self._enabled.setObjectName("shell.settings.shopSharing.enabled")

        hint = QLabel(HINT_TEXT, self)
        hint.setWordWrap(True)
        hint.setProperty("shopSharingRole", "hint")

        self._folder_field = QLineEdit(self)
        self._folder_field.setObjectName("shell.settings.shopSharing.folder")
        self._folder_field.setReadOnly(True)

        change = QPushButton("Change\u2026", self)
        change.setObjectName("shell.settings.shopSharing.change")
        change.clicked.connect(self._choose_folder)

        folder_row = QHBoxLayout()
        folder_row.addWidget(QLabel("Saved in", self))
        folder_row.addWidget(self._folder_field, 1)
        folder_row.addWidget(change)

        self._status = QLabel(self)
        self._status.setObjectName("shell.settings.shopSharing.status")
        self._status.setWordWrap(True)

        self._error = QLabel(self)
        self._error.setObjectName("shell.settings.shopSharing.error")
        self._error.setWordWrap(True)
        self._error.setVisible(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self._enabled)
        layout.addWidget(hint)
        layout.addLayout(folder_row)
        layout.addWidget(self._status)
        layout.addWidget(self._error)
        self._render(service.status())

    def commit(self) -> bool:
        """Run the sharing change the controls ask for.

        A refusal shows ``SharingResult.error`` and re-renders every control
        from ``service.status()``. A refused turn-on leaves the checkbox off.
        A refused folder switch puts the old folder back and leaves the box checked.
        """
        intent = sharing_intent(
            self._service.status(),
            checked=self._enabled.isChecked(),
            folder=self._folder,
        )
        if intent is None:
            self._set_error("")
            return True
        if isinstance(intent, TurnOn):
            result = self._service.turn_on(intent.folder, via="settings")
        else:
            result = self._service.turn_off()
        self._render(self._service.status())
        if result.ok:
            self._set_error("")
            return True
        self._set_error(result.error)
        return False

    def _render(self, status: ShopStatus) -> None:
        self.setEnabled(status.mode is not SharingMode.PINNED)
        self._enabled.setChecked(status.mode is SharingMode.SHOP)
        if status.mode is SharingMode.SHOP and status.folder is not None:
            self._folder = status.folder
        elif status.mode is SharingMode.LOCAL:
            self._folder = self._service.default_new_folder()
        self._folder_field.setText("" if status.mode is SharingMode.PINNED else str(self._folder))
        self._status.setText(status_line(status, now=self._now()))

    def _choose_folder(self) -> None:
        picked = choose_existing_directory(self, "Choose Shop Folder", str(Path.home() / "share"))
        if not picked:
            return
        self._folder = shop_folder_for_pick(Path(picked))
        self._folder_field.setText(str(self._folder))

    def _set_error(self, text: str) -> None:
        self._error.setText(text)
        self._error.setVisible(bool(text))
