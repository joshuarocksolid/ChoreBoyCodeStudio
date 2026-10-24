"""One form toast. It confirms a command the user might want back.

The note records the undo label and the log depth that announced it. Undo
runs only while that command is still the top of the log.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Sequence, Tuple

from app.qt.QtCore import QEvent, Qt, QTimer
from app.qt.QtGui import QColor
from app.qt.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from app.features.form_builder.engine.ui4.spec import NodeSpec
from app.shell.theme_tokens import ShellThemeTokens

_WITH_ACTION_MS = 8000
_PLAIN_MS = 6000


@dataclass(frozen=True)
class ToastNote:
    """What the toast is offering to undo."""

    text: str
    action: Optional[str]
    command: str
    depth: int
    #: The log entry this note undoes. Identity, not the label.
    entry: object = None


def notice_for(label: str) -> Optional[str]:
    """A sentence when ``label`` is a command the toast should confirm."""
    return notice_sentence(label)


def notice_sentence(label: str, names: Sequence[str] = ()) -> Optional[str]:
    """``Deleted printButton``, ``Deleted 3 widgets``, or ``Changed the layout``."""
    folded = " ".join(label.strip().lower().split())
    if not folded:
        return None
    phrase = _phrase(folded)
    if phrase is None:
        return None
    if phrase[1] is None:
        return phrase[0]
    unique = tuple(dict.fromkeys(name for name in names if name))
    verb = phrase[0]
    if len(unique) == 1:
        return "%s %s" % (verb, unique[0])
    if len(unique) > 1:
        return "%s %d widgets" % (verb, len(unique))
    return "%s the selection" % verb


def names_from_entry(entry: object) -> Tuple[str, ...]:
    """Object names of the subtrees an undo would put back."""
    names = []
    for op in getattr(entry, "inverse_ops", ()):
        name = _spec_name(getattr(op, "spec", None))
        if name and name not in names:
            names.append(name)
    return tuple(names)


def _spec_name(spec: object) -> Optional[str]:
    if not isinstance(spec, NodeSpec):
        return None
    name = spec.field("object_name") or spec.field("name")
    if isinstance(name, str) and name:
        return name
    for slot, _kids in spec.slots:
        for child in spec.children(slot):
            found = _spec_name(child)
            if found:
                return found
    return None


def _phrase(folded: str) -> Optional[Tuple[str, Optional[str]]]:
    """``(sentence, None)`` or ``(verb, "named")`` for a regret command."""
    if "remove layout" in folded:
        return ("Removed the layout", None)
    if "break layout" in folded:
        return ("Broke the layout", None)
    if "change layout" in folded:
        return ("Changed the layout", None)
    if "change widget" in folded or "morph" in folded:
        return ("Changed the widget", None)
    if "unwrap" in folded:
        return ("Unwrapped the selection", None)
    if "delete" in folded:
        return ("Deleted", "named")
    if folded == "cut" or folded.startswith("cut "):
        return ("Cut", "named")
    if "wrap" in folded:
        return ("Wrapped the selection", None)
    return None


def toast_duration_ms(has_action: bool) -> int:
    return _WITH_ACTION_MS if has_action else _PLAIN_MS


def undo_matches(note: ToastNote, entry: object) -> bool:
    return entry is not None and note.entry is entry


class CommandToast(QFrame):
    """Level-2 notice at the bottom centre of the form surface. It does not take focus."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.commandToast")
        self.setAccessibleName("Notice")
        self.setFocusPolicy(_no_focus())
        self.setMaximumWidth(480)
        self.setAttribute(_attr("WA_ShowWithoutActivating"), True)
        self._note: Optional[ToastNote] = None
        self._on_action: Optional[Callable[[ToastNote], None]] = None
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 8, 8, 8)
        row.setSpacing(8)
        self._text = QLabel(self)
        self._text.setObjectName("formBuilder.toastText")
        self._text.setWordWrap(True)
        self._text.setFocusPolicy(_no_focus())
        row.addWidget(self._text, 1)
        self._action = QPushButton(self)
        self._action.setObjectName("formBuilder.toastUndo")
        self._action.setFocusPolicy(_no_focus())
        self._action.clicked.connect(self._activate)
        self._action.hide()
        row.addWidget(self._action, 0)
        close = QPushButton("\u00d7", self)
        close.setObjectName("formBuilder.toastClose")
        close.setAccessibleName("Close")
        close.setFocusPolicy(_no_focus())
        close.clicked.connect(self.dismiss)
        row.addWidget(close, 0)
        self._timer = QTimer(self)
        self._timer.setObjectName("formBuilder.toastTimer")
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.dismiss)
        self.hide()

    def show_note(self, note: ToastNote, on_action: Callable[[ToastNote], None]) -> None:
        self._note = note
        self._on_action = on_action
        self._text.setText(note.text)
        self._text.setAccessibleName(note.text)
        if note.action:
            self._action.setText(note.action)
            self._action.setAccessibleName(note.action)
            self._action.show()
        else:
            self._action.hide()
        self._arm()
        self.show()
        self.raise_()
        self.place()

    def dismiss(self) -> None:
        self._timer.stop()
        self._note = None
        self._on_action = None
        self.hide()

    def place(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        self.adjustSize()
        width = min(480, max(self.sizeHint().width(), 160), max(1, parent.width() - 16))
        height = max(self.sizeHint().height(), 32)
        self.resize(width, height)
        self.move(max(0, (parent.width() - width) // 2), max(0, parent.height() - height - 16))

    def apply_theme(self, tokens: ShellThemeTokens) -> None:
        fill = tokens.popup_bg or tokens.panel_bg
        border = tokens.popup_border or tokens.border
        width = tokens.focus_border_width or 1
        self.setStyleSheet(
            "QFrame#formBuilder\\.commandToast { background: %s; color: %s;"
            " border: %dpx solid %s; border-radius: 6px; }"
            "QLabel { background: transparent; color: %s; border: none; }"
            "QPushButton { background: transparent; color: %s; border: none; padding: 2px 6px; }"
            % (fill, tokens.text_primary, width, border, tokens.text_primary, tokens.text_primary)
        )
        if tokens.is_high_contrast:
            self.setGraphicsEffect(None)
            return
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(0, 0, 0, 41))
        self.setGraphicsEffect(shadow)

    def enterEvent(self, event: QEvent) -> None:  # noqa: N802
        self._timer.stop()
        super().enterEvent(event)  # type: ignore[arg-type]

    def leaveEvent(self, event: QEvent) -> None:  # noqa: N802
        if self.isVisible():
            self._arm()
        super().leaveEvent(event)  # type: ignore[arg-type]

    def _activate(self) -> None:
        note = self._note
        action = self._on_action
        if note is None or action is None:
            return
        action(note)

    def _arm(self) -> None:
        self._timer.start(toast_duration_ms(not self._action.isHidden()))


def _no_focus() -> Qt.FocusPolicy:
    return getattr(getattr(Qt, "FocusPolicy", Qt), "NoFocus")


def _attr(name: str) -> Qt.WidgetAttribute:
    return getattr(getattr(Qt, "WidgetAttribute", Qt), name)
