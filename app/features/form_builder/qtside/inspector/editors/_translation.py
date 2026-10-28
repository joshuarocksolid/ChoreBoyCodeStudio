"""Translation disclosure (UX-PED-041).

"Translation ▸" expands the fields. "Not translated" stays on that line when
``notr`` is set, so it is visible while the disclosure is closed. Each field
calls ``on_change`` once. The host makes that one undo step.
"""

from __future__ import annotations

from typing import Callable, Optional, Tuple

from app.qt.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

_MEANING_HELP = (
    "Tells translators which meaning is meant when the same words mean "
    "different things, like \u201cOpen\u201d a file or \u201cOpen\u201d the shop."
)


class TranslationDisclosure(QWidget):
    """Attribute editor for one string or one whole string list."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.translation")
        self._on_change: Optional[Callable[[str, object], None]] = None
        self._show_id = False
        self._painting = False
        self._expanded = False
        self._toggle = QToolButton(self)
        self._toggle.setObjectName("formBuilder.translationToggle")
        self._toggle.setText("Translation \u25b8")
        self._toggle.setAccessibleName("Translation")
        self._toggle.setAutoRaise(True)
        self._toggle.setCheckable(True)
        self._tag = QLabel("Not translated", self)
        self._tag.setObjectName("formBuilder.translationTag")
        self._tag.hide()
        line = QWidget(self)
        row = QHBoxLayout(line)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self._toggle, 0)
        row.addStretch(1)
        row.addWidget(self._tag, 0)
        self._body = QWidget(self)
        body = QVBoxLayout(self._body)
        body.setContentsMargins(12, 2, 0, 0)
        body.setSpacing(2)
        self._translate = QCheckBox("Translate this text", self._body)
        self._translate.setAccessibleName("Translation: translate this text")
        self._meaning = self._field("Meaning", _MEANING_HELP)
        self._note = self._field("Note for the translator", "")
        self._ident = self._field("Translation id", "")
        for widget in (self._translate, self._meaning[0], self._meaning[1], self._note[0], self._note[1], self._ident[0], self._ident[1]):
            body.addWidget(widget)
        self._body.hide()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(line)
        layout.addWidget(self._body)
        self._toggle.clicked.connect(self._toggle_body)
        self._translate.clicked.connect(self._commit_translate)
        self._meaning[1].editingFinished.connect(lambda: self._commit_text("comment", self._meaning[1]))
        self._note[1].editingFinished.connect(lambda: self._commit_text("extracomment", self._note[1]))
        self._ident[1].editingFinished.connect(lambda: self._commit_text("id", self._ident[1]))

    def set_on_change(self, callback: Optional[Callable[[str, object], None]]) -> None:
        self._on_change = callback

    def set_values(
        self,
        *,
        notr: Optional[bool],
        comment: Optional[str],
        extracomment: Optional[str],
        ident: Optional[str],
        show_id: bool,
    ) -> None:
        self._painting = True
        self._show_id = show_id or ident is not None
        self._translate.setChecked(notr is not True)
        self._meaning[1].setText(comment or "")
        self._note[1].setText(extracomment or "")
        self._ident[1].setText(ident or "")
        self._tag.setVisible(notr is True)
        self._apply_id()
        self._painting = False

    def set_expanded(self, expanded: bool) -> None:
        self._expanded = bool(expanded)
        self._toggle.setChecked(self._expanded)
        self._toggle.setText("Translation \u25be" if self._expanded else "Translation \u25b8")
        self._body.setVisible(self._expanded)

    def expanded(self) -> bool:
        return self._expanded

    def _field(self, label: str, tip: str) -> Tuple[QLabel, QLineEdit]:
        caption = QLabel(label, self._body)
        caption.setObjectName("formBuilder.translationCaption")
        edit = QLineEdit(self._body)
        edit.setAccessibleName("Translation: %s" % label.lower())
        if tip:
            edit.setToolTip(tip)
            caption.setToolTip(tip)
        return caption, edit

    def _apply_id(self) -> None:
        shown = self._show_id or bool(self._ident[1].text())
        self._ident[0].setVisible(shown)
        self._ident[1].setVisible(shown)

    def _toggle_body(self) -> None:
        self.set_expanded(self._toggle.isChecked())

    def _commit_translate(self) -> None:
        if self._painting:
            return
        checked = self._translate.isChecked()
        self._tag.setVisible(not checked)
        self._emit("notr", None if checked else True)

    def _commit_text(self, field: str, edit: QLineEdit) -> None:
        if self._painting:
            return
        self._emit(field, edit.text() or None)

    def _emit(self, field: str, value: object) -> None:
        callback = self._on_change
        if callback is not None:
            callback(field, value)
