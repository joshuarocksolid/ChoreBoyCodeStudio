"""The picture picker of the inspector (UX-PED-100), for the drawer's Insert > Picture… (UX-STYLE-006)."""

from __future__ import annotations

from typing import Any, List, Optional

from app.features.form_builder.qtside.inspector.editors._picture_picker import PicturePicker
from app.qt.QtWidgets import QDialog, QDialogButtonBox, QVBoxLayout, QWidget


class _Host:
    """Just enough of an editor host for the picker: the document, the chrome and the session's folder."""

    def __init__(self, session: Any, chrome: Any, anchor: QWidget) -> None:
        self._session = session
        self.chrome = chrome
        self.row_widget = anchor

    def document(self) -> Any:
        return self._session.document


class _Anchor(QWidget):
    """A parentless-looking widget that carries the session, as an inspector row does."""

    def __init__(self, session: Any, parent: QWidget) -> None:
        super().__init__(parent)
        self._services = type("_Services", (), {"session": session})()


def pick_picture(session: Any, chrome: Any, parent: QWidget) -> str:
    anchor = _Anchor(session, parent)
    host = _Host(session, chrome, anchor)
    dialog = QDialog(parent)
    dialog.setObjectName("formBuilder.stylePictureDialog")
    dialog.setWindowTitle("Picture")
    chosen: List[str] = []
    layout = QVBoxLayout(dialog)

    def done(stored: str) -> None:
        chosen.append(stored)

    picker = PicturePicker(dialog, host, done, on_close=dialog.accept)  # type: ignore[arg-type]
    layout.addWidget(picker)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, dialog)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    picker.focus_first()
    accepted: Optional[bool] = bool(dialog.exec())
    return chosen[-1] if accepted and chosen else ""
