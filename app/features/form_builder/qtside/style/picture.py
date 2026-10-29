"""The picture picker of the inspector (UX-PED-100), for the drawer's Insert > Picture… (UX-STYLE-006)."""

from __future__ import annotations

import math
from typing import Any, List, Optional, Sequence, Tuple, Union

from app.features.form_builder.engine.commands.base import CommandRejected

from app.features.form_builder.qtside.inspector.editors._picture_picker import PicturePicker
from app.qt.QtWidgets import QDialog, QDialogButtonBox, QVBoxLayout, QWidget


class _Rejected:
    def __init__(self, message: str) -> None:
        self.message = message


class _Step:
    """The picker's edit session: its include commands join the drawer visit's one undo step (UX-STYLE-007)."""

    def __init__(self, session: Any, label: str, token: str) -> None:
        self._session = session
        self._label = label
        self._token = token

    def set_label(self, label: str) -> None:
        # The step is the drawer visit's; it keeps the visit's name.
        del label

    def run(self, commands: Sequence[Any]) -> Union[Tuple[object, ...], _Rejected]:
        try:
            results = []
            with self._session.log.transaction(
                self._label, merge_token=self._token or None, merge_within_s=math.inf if self._token else 0.0
            ) as txn:
                for command in commands:
                    results.append(txn.execute(command))
            return tuple(results)
        except CommandRejected as exc:
            return _Rejected(str(exc))

    def close(self) -> None:
        pass


class _Host:
    """Just enough of an editor host for the picker (M5.2's ``PicturePicker``): document, chrome, anchor and steps."""

    def __init__(self, session: Any, chrome: Any, anchor: QWidget, label: str, token: str) -> None:
        self._session = session
        self.chrome = chrome
        self.row_widget = anchor
        self._label = label
        self._token = token

    def document(self) -> Any:
        return self._session.document

    def begin_session(self, label: str) -> _Step:
        del label
        return _Step(self._session, self._label, self._token)


class _Anchor(QWidget):
    """A parentless-looking widget that carries the session, as an inspector row does."""

    def __init__(self, session: Any, parent: QWidget) -> None:
        super().__init__(parent)
        self._services = type("_Services", (), {"session": session})()


def pick_picture(session: Any, chrome: Any, parent: QWidget, *, label: str = "Add picture", token: str = "") -> str:
    anchor = _Anchor(session, parent)
    host = _Host(session, chrome, anchor, label, token)
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
