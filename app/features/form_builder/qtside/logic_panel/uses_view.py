"""Uses of one name. Read, Set and Call, from the same table as the Logic panel."""

from __future__ import annotations

from typing import Optional, Tuple

from app.qt.QtCore import Qt
from app.qt.QtWidgets import QDialog, QLabel, QVBoxLayout, QWidget
from app.qt.qt_compat import enum_value

from app.features.form_builder.engine.logic.uses import Use

_ELIDE = getattr(getattr(Qt, "TextElideMode", Qt), "ElideRight")
_PLAIN = getattr(getattr(Qt, "TextFormat", Qt), "PlainText")
_FOCUS = getattr(getattr(Qt, "FocusPolicy", Qt), "StrongFocus")


def _ignored() -> tuple:
    from app.qt.QtWidgets import QSizePolicy

    names = getattr(QSizePolicy, "Policy", QSizePolicy)
    return getattr(names, "Ignored"), getattr(names, "Preferred")


class ElidedLabel(QLabel):
    """One line, cut with an ellipsis, tooltip and accessible name left whole."""

    def __init__(self, full: str, parent: QWidget) -> None:
        super().__init__(parent)
        self._full = full
        self._eliding = False
        self.setWordWrap(False)
        self.setMinimumWidth(0)
        self.setTextFormat(_PLAIN)
        self.setToolTip(full)
        ignored, preferred = _ignored()
        self.setSizePolicy(ignored, preferred)  # type: ignore[arg-type]
        self._elide()

    def set_full(self, full: str) -> None:
        self._full = full
        self.setToolTip(full)
        self._elide()

    def resizeEvent(self, event: object) -> None:  # noqa: N802
        super().resizeEvent(event)  # type: ignore[arg-type]
        self._elide()

    def showEvent(self, event: object) -> None:  # noqa: N802
        super().showEvent(event)  # type: ignore[arg-type]
        self._elide()

    def _elide(self) -> None:
        if self._eliding:
            return
        self._eliding = True
        try:
            width = max(1, self.width() - 2)
            shown = self.fontMetrics().elidedText(self._full, _ELIDE, width)
            if self.text() != shown:
                self.setText(shown)
        finally:
            self._eliding = False


class UsesDialog(QDialog):
    def __init__(
        self,
        name: str,
        uses: Tuple[Use, ...],
        tokens: object,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.logic.uses")
        self.setWindowTitle("Uses of %s" % name)
        self.setMinimumWidth(0)
        self._name = name
        self._uses = uses
        self._tokens = tokens
        self._rows: list = []
        column = QVBoxLayout(self)
        column.setContentsMargins(8, 8, 8, 8)
        column.setSpacing(4)
        self._column = column
        heading = QLabel("Uses of %s" % name, self)
        heading.setObjectName("formBuilder.logic.usesHeading")
        heading.setWordWrap(False)
        heading.setMinimumWidth(0)
        column.addWidget(heading)
        self._fill()
        if tokens is not None:
            self.apply_theme(tokens)
        self.resize(420, 360)

    def keyPressEvent(self, event: object) -> None:  # noqa: N802
        if enum_value(event.key()) == enum_value(Qt.Key.Key_Escape):  # type: ignore[attr-defined]
            self.reject()
            return
        super().keyPressEvent(event)  # type: ignore[arg-type]

    def apply_theme(self, tokens: object) -> None:
        self._tokens = tokens
        width = tokens.focus_border_width  # type: ignore[attr-defined]
        self.setAutoFillBackground(True)
        from app.qt.QtGui import QColor, QPalette

        palette = self.palette()
        role = getattr(QPalette, "ColorRole", QPalette)
        palette.setColor(getattr(role, "Window"), QColor(tokens.panel_bg))  # type: ignore[attr-defined]
        palette.setColor(getattr(role, "WindowText"), QColor(tokens.text_primary))  # type: ignore[attr-defined]
        self.setPalette(palette)
        self.setStyleSheet(
            "QDialog#formBuilder\\.logic\\.uses { background: %s; color: %s; }"
            "QLabel { color: %s; background: transparent; }"
            "QLabel#formBuilder\\.logic\\.usesTitle { color: %s; }"
            "QLabel#formBuilder\\.logic\\.usesRow:focus { border: %dpx solid %s; }"
            % (
                tokens.panel_bg,  # type: ignore[attr-defined]
                tokens.text_primary,  # type: ignore[attr-defined]
                tokens.text_primary,  # type: ignore[attr-defined]
                tokens.text_muted,  # type: ignore[attr-defined]
                width,
                tokens.accent,  # type: ignore[attr-defined]
            )
        )

    def _fill(self) -> None:
        if not self._uses:
            empty = QLabel(
                "Nothing in this form reads, sets, or calls %s." % self._name,
                self,
            )
            empty.setWordWrap(True)
            empty.setMinimumWidth(0)
            self._column.addWidget(empty)
            self._column.addStretch(1)
            return
        number = 0
        for role, title in (("read", "Read"), ("set", "Set"), ("call", "Call")):
            rows = tuple(use for use in self._uses if use.role == role)
            if not rows:
                continue
            heading = QLabel(title, self)
            heading.setObjectName("formBuilder.logic.usesTitle")
            self._column.addWidget(heading)
            for use in rows:
                full = _line(use)
                label = ElidedLabel(full, self)
                label.setObjectName("formBuilder.logic.uses.row.%d" % number)
                label.setFocusPolicy(_FOCUS)
                label.setAccessibleName("%s, %s" % (title, full))
                self._column.addWidget(label)
                self._rows.append(label)
                number += 1
        self._column.addStretch(1)


def _line(use: Use) -> str:
    from app.features.form_builder.engine.logic.uses import WORDS

    if use.kind == "rule":
        words = WORDS.get(use.property_key, use.property_key)
        return "%s  %s  %s" % (use.widget, words, use.summary)
    if use.kind == "check":
        return "%s  %s" % (use.widget, use.summary)
    if use.kind == "step":
        extra = use.summary or use.method
        if extra:
            return "%s  %s  %s" % (use.widget, use.signal, extra)
        return "%s  %s" % (use.widget, use.signal)
    what = use.summary or use.method or use.signal
    if use.line:
        return "%s  %s  line %d" % (use.widget, what, use.line)
    return "%s  %s" % (use.widget, what)
