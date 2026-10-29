"""Ctrl+R in a form tab: a small picker that jumps to a widget (UX-SHELL-004)."""

from __future__ import annotations

from typing import Callable, List, Sequence, Tuple

from app.qt.QtCore import QEvent, QObject, QPoint, QRect, Qt
from app.qt.QtGui import QKeyEvent
from app.qt.QtWidgets import QFrame, QLabel, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout, QWidget
from app.qt.qt_compat import enum_value

from app.features.form_builder.qtside.theme.chrome import FormChrome, popover_style

#: One row of the picker: object name and the friendly class words.
WidgetEntry = Tuple[str, str]

_WIDTH = 360
_ROWS = 9
_ENTER = frozenset({enum_value(Qt.Key.Key_Return), enum_value(Qt.Key.Key_Enter)})
_ESCAPE = enum_value(Qt.Key.Key_Escape)
_STEPS = {enum_value(Qt.Key.Key_Up): -1, enum_value(Qt.Key.Key_Down): 1}
_ROLE = enum_value(Qt.ItemDataRole.UserRole)


def filter_entries(entries: Sequence[WidgetEntry], query: str) -> List[WidgetEntry]:
    """Entries whose name or class words contain every word of ``query``.

    Names that start with the first word come first, then other name matches,
    then class-only matches. Document order is kept inside each group.
    """
    words = query.lower().split()
    if not words:
        return list(entries)
    ranked: List[Tuple[int, int, WidgetEntry]] = []
    for index, entry in enumerate(entries):
        name = entry[0].lower()
        text = "%s %s" % (name, entry[1].lower())
        if not all(word in text for word in words):
            continue
        if name.startswith(words[0]):
            rank = 0
        elif all(word in name for word in words):
            rank = 1
        else:
            rank = 2
        ranked.append((rank, index, entry))
    ranked.sort(key=lambda row: (row[0], row[1]))
    return [row[2] for row in ranked]


class GoToWidgetPicker(QFrame):
    """Type to filter, Up and Down to move, Enter to go, Esc to close.

    A popup, not a dialog: it never blocks the event loop, and a click outside
    closes it.
    """

    def __init__(
        self,
        parent: QWidget,
        entries: Sequence[WidgetEntry],
        chrome: FormChrome,
        on_pick: Callable[[str], None],
    ) -> None:
        super().__init__(parent, Qt.WindowType.Popup)
        self.setObjectName("formBuilder.goToWidget")
        self.setAccessibleName("Go to widget")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self._entries = list(entries)
        self._on_pick = on_pick
        self._chrome = chrome
        column = QVBoxLayout(self)
        column.setContentsMargins(10, 8, 10, 10)
        column.setSpacing(6)
        header = QLabel("Go to widget…", self)
        header.setObjectName("formBuilder.goToWidgetHeader")
        column.addWidget(header)
        self.search = QLineEdit(self)
        self.search.setObjectName("formBuilder.goToWidgetSearch")
        self.search.setAccessibleName("Widget name or kind")
        self.search.setPlaceholderText("Type a name or a kind, such as button")
        self.search.textChanged.connect(self._refill)
        self.search.installEventFilter(self)
        column.addWidget(self.search)
        self.rows = QListWidget(self)
        self.rows.setObjectName("formBuilder.goToWidgetList")
        self.rows.setAccessibleName("Matching widgets")
        self.rows.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.rows.itemClicked.connect(self._clicked)
        column.addWidget(self.rows)
        self.note = QLabel("No widget matches.", self)
        self.note.setObjectName("formBuilder.goToWidgetNote")
        self.note.setProperty("note", True)
        column.addWidget(self.note)
        self.setStyleSheet(self._style())
        self.setFixedWidth(_WIDTH)
        self._refill()

    def open_in(self, bounds: QRect) -> None:
        """Show near the top centre of ``bounds`` (global) with the search box focused."""
        self.adjustSize()
        at = QPoint(bounds.center().x() - self.width() // 2, bounds.top() + 48)
        at.setX(max(bounds.left(), min(at.x(), bounds.right() - self.width())))
        self.move(at)
        self.show()
        self.search.setFocus()

    def names(self) -> List[str]:
        """Object names now listed, top first."""
        return [str(self.rows.item(i).data(_ROLE)) for i in range(self.rows.count())]

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        kind = event.type()
        if watched is self.search and kind == QEvent.Type.ShortcutOverride:
            # Ctrl+R again, or any window key, must not run behind the picker.
            event.accept()
            return True
        if watched is self.search and kind == QEvent.Type.KeyPress:
            return self._key(event)  # type: ignore[arg-type]
        return super().eventFilter(watched, event)

    def _key(self, event: QKeyEvent) -> bool:
        key = enum_value(event.key())
        step = _STEPS.get(key)
        if step is not None:
            count = self.rows.count()
            if count:
                self.rows.setCurrentRow((self.rows.currentRow() + step) % count)
            return True
        if key in _ENTER:
            self._choose()
            return True
        if key == _ESCAPE:
            self.close()
            return True
        return False

    def _refill(self) -> None:
        shown = filter_entries(self._entries, self.search.text())
        self.rows.clear()
        for name, kind in shown:
            item = QListWidgetItem("%s    %s" % (name, kind))
            item.setData(_ROLE, name)
            self.rows.addItem(item)
        if shown:
            self.rows.setCurrentRow(0)
        self.note.setVisible(not shown)
        rows = min(max(len(shown), 1), _ROWS)
        self.rows.setFixedHeight(rows * max(self.rows.sizeHintForRow(0), 24) + 6)
        self.adjustSize()

    def _choose(self) -> None:
        item = self.rows.currentItem()
        if item is None:
            return
        name = str(item.data(_ROLE))
        self.close()
        self._on_pick(name)

    def _clicked(self, item: QListWidgetItem) -> None:
        self.rows.setCurrentItem(item)
        self._choose()

    def _style(self) -> str:
        chrome = self._chrome
        frame = "QFrame#formBuilder\\.goToWidget"
        return popover_style(self.objectName(), chrome) + (
            "%(f)s QLineEdit { color: %(text)s; background: %(input)s; border: 1px solid %(border)s;"
            " border-radius: 4px; padding: 5px 8px; }"
            "%(f)s QLineEdit:focus { border: %(focus)dpx solid %(accent)s; }"
            "%(f)s QListWidget { color: %(text)s; background: %(panel)s; border: none; outline: none; }"
            "%(f)s QListWidget::item { padding: 4px 8px; border-radius: 4px; }"
            "%(f)s QListWidget::item:hover { background: %(hover)s; }"
            "%(f)s QListWidget::item:selected { color: %(text)s; background: %(selected)s;"
            " border: %(focus)dpx solid %(accent)s; }"
        ) % {
            "f": frame,
            "text": chrome.text,
            "input": chrome.input,
            "border": chrome.border,
            "panel": chrome.panel,
            "hover": chrome.row_hover,
            "selected": chrome.selected,
            "accent": chrome.accent,
            "focus": chrome.focus_width,
        }
