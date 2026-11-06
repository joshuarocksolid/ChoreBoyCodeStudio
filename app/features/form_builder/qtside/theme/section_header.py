"""One section header for the builder chrome.

The title uses the same size, weight, and tracking as ``shell.outlinePanel.title``.
The label keeps its own object name, because callers and the perf probe find
headers by that name. A parent sheet that paints every ``QLabel`` in body text
would otherwise win, so the header sheet repeats the host title rule here.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from app.features.form_builder.qtside.icons.glyphs import paint_glyph
from app.features.form_builder.qtside.theme.chrome import FormChrome
from app.features.form_builder.qtside.theme.metrics import (
    CHEVRON,
    ICON,
    ICON_BUTTON_HEADER,
    LETTER_SECTION,
    PANE_PAD,
    S1,
    S2,
    SECTION_HEADER,
    TYPE_FINE,
    TYPE_SECTION,
)
from app.qt.QtCore import QSize, Qt, Signal
from app.qt.QtGui import QFont, QIcon
from app.qt.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QToolButton, QWidget

_TITLE_NAME = "shell.outlinePanel.title"


class SectionHeader(QWidget):
    """Uppercase overline. Optional chevron, count, and 20 px actions."""

    toggled = Signal(bool)
    clicked = Signal(bool)

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        title: str = "",
        *,
        collapsible: bool = False,
        object_name: str = "",
        accessible_name: str = "",
        checkable: bool = False,
    ) -> None:
        super().__init__(parent)
        self._collapsible = collapsible
        self._expanded = True
        self._chrome: Optional[FormChrome] = None
        self._actions: List[Tuple[QToolButton, str]] = []
        self.setObjectName(object_name or "formBuilder.sectionHeader")
        self.setFixedHeight(SECTION_HEADER)
        policy = getattr(QSizePolicy, "Policy", QSizePolicy)
        self.setSizePolicy(getattr(policy, "Expanding"), getattr(policy, "Fixed"))
        self.setFocusPolicy(self._focus("NoFocus") if checkable else self._focus("StrongFocus"))
        self.setAccessibleName(accessible_name or title)

        row = QHBoxLayout(self)
        row.setContentsMargins(PANE_PAD, 0, S2, 0)
        row.setSpacing(S1)
        self._chevron = QLabel(self)
        self._chevron.setFixedSize(CHEVRON, CHEVRON)
        self._chevron.setFocusPolicy(self._focus("NoFocus"))
        self._chevron.setVisible(collapsible)
        row.addWidget(self._chevron)

        self._button: Optional[QToolButton] = None
        self._label = QLabel(self)
        self._label.setObjectName(_TITLE_NAME)
        self._label.setFont(self._title_font())
        self._label.setFocusPolicy(self._focus("NoFocus"))
        if checkable:
            button = QToolButton(self)
            button.setObjectName(object_name or "formBuilder.sectionHeader")
            button.setCheckable(True)
            button.setChecked(True)
            button.setAutoRaise(True)
            button.setArrowType(self._no_arrow())
            button.setFont(self._title_font())
            button.setFocusPolicy(self._focus("StrongFocus"))
            button.setSizePolicy(getattr(policy, "Fixed"), getattr(policy, "Fixed"))
            button.setToolButtonStyle(self._text_only())
            button.setProperty("fbSectionTitle", "true")
            if accessible_name:
                button.setAccessibleName(accessible_name)
            button.clicked.connect(self._button_clicked)
            button.toggled.connect(self._sync_chevron)
            self._button = button
            self._label.hide()
            row.addWidget(button)
        else:
            if object_name:
                self._label.setObjectName(object_name)
            self._label.setAlignment(self._left())
            self._label.setSizePolicy(getattr(policy, "Fixed"), getattr(policy, "Preferred"))
            row.addWidget(self._label)

        self._count = QLabel(self)
        self._count.setObjectName("formBuilder.sectionCount")
        self._count.setFont(self._count_font())
        self._count.setFocusPolicy(self._focus("NoFocus"))
        self._count.hide()
        row.addWidget(self._count)
        row.addStretch(1)
        self._row = row
        self.set_title(title)
        self._sync_chevron()

    @property
    def toggle(self) -> QToolButton:
        """The checkable title. Group code and older tests click this button."""
        if self._button is None:
            raise RuntimeError("this header has no checkable title")
        return self._button

    def title_label(self) -> QLabel:
        return self._label

    def set_title(self, title: str) -> None:
        shown = title.upper()
        self._label.setText(shown)
        if self._button is not None:
            self._button.setText(shown)
        self._fit_title()

    def setText(self, title: str) -> None:  # noqa: N802
        self.set_title(title)

    def text(self) -> str:
        if self._button is not None:
            return self._button.text()
        return self._label.text()

    def set_count(self, count: Optional[int]) -> None:
        if count is None:
            self._count.hide()
            return
        self._count.setText(str(count))
        self._count.show()

    def add_action(
        self,
        glyph: str,
        tooltip: str,
        accessible_name: str = "",
        object_name: str = "",
    ) -> QToolButton:
        button = QToolButton(self)
        button.setObjectName(object_name or "shell.outlinePanel.action.more")
        button.setFixedSize(ICON_BUTTON_HEADER, ICON_BUTTON_HEADER)
        button.setAutoRaise(True)
        button.setToolTip(tooltip)
        button.setAccessibleName(accessible_name or tooltip)
        button.setFocusPolicy(self._focus("StrongFocus"))
        button.setArrowType(self._no_arrow())
        self._actions.append((button, glyph))
        self._row.addWidget(button)
        self._paint_marks()
        return button

    @property
    def extra(self) -> List[QToolButton]:
        """Action buttons, in focus order. The outline and insert panes tab through these."""
        return [button for button, _glyph in self._actions]

    def detach_actions(self) -> List[QToolButton]:
        """Hand the action buttons to a tab corner. The header keeps the references."""
        buttons = []
        for button, _glyph in self._actions:
            self._row.removeWidget(button)
            buttons.append(button)
        return buttons

    def reclaim_actions(self) -> None:
        """Put action buttons back on the header before a corner widget is destroyed."""
        for button, _glyph in self._actions:
            button.setParent(self)
            if self._row.indexOf(button) < 0:
                self._row.addWidget(button)
        self._paint_marks()

    def setChecked(self, checked: bool) -> None:  # noqa: N802
        self._set_expanded(bool(checked), emit=False)

    def isChecked(self) -> bool:  # noqa: N802
        if self._button is not None:
            return bool(self._button.isChecked())
        return self._expanded

    def click(self) -> None:
        if self._button is not None:
            self._button.click()
            return
        self._set_expanded(not self._expanded, emit=True)

    def set_pad(self, left: int) -> None:
        margins = self._row.contentsMargins()
        self._row.setContentsMargins(left, margins.top(), margins.right(), margins.bottom())

    def apply_chrome(self, chrome: FormChrome) -> None:
        self._chrome = chrome
        title = self._label.objectName() or _TITLE_NAME
        title_sel = _escape(title)
        button_sel = _escape(self._button.objectName()) if self._button is not None else ""
        focus = chrome.focus_width if chrome.focus_width > 0 else 1
        if self._button is not None and button_sel:
            # The button's own sheet beats a parent rule that paints every QWidget.
            self._button.setStyleSheet(
                "QToolButton#%s[fbSectionTitle=\"true\"] { color: %s; background: transparent; border: none;"
                " padding: 0px; text-align: left; font-size: %dpx; font-weight: 700;"
                " letter-spacing: %spx; }"
                "QToolButton#%s[fbSectionTitle=\"true\"]:focus { border: %dpx solid %s; }"
                % (button_sel, chrome.muted, TYPE_SECTION, LETTER_SECTION, button_sel, focus, chrome.accent)
            )
        self.setStyleSheet(
            "QWidget#%s { background: transparent; border: none; }"
            "QLabel#%s { color: %s; background: transparent; border: none; padding: 0px;"
            " font-size: %dpx; font-weight: 700; letter-spacing: %spx; }"
            "QLabel#formBuilder\\.sectionCount { color: %s; background: transparent; border: none;"
            " font-size: %dpx; font-variant-numeric: tabular-nums; }"
            "%s { background: transparent; border: none; border-radius: %dpx; padding: 0px; }"
            "%s:hover { background: %s; }"
            "%s:pressed { background: %s; }"
            "%s:focus { border: %dpx solid %s; }"
            "%s { image: none; width: 0px; }"
            % (
                _escape(self.objectName()),
                title_sel,
                chrome.muted,
                TYPE_SECTION,
                LETTER_SECTION,
                chrome.faint,
                TYPE_FINE,
                _action_selector(self._actions),
                S1,
                _action_selector(self._actions),
                chrome.row_hover,
                _action_selector(self._actions),
                chrome.selected or chrome.row_hover,
                _action_selector(self._actions),
                focus,
                chrome.accent,
                _action_selector(self._actions, "::menu-indicator"),
            )
        )
        self._fit_title()
        self._paint_marks()

    def showEvent(self, event: object) -> None:  # noqa: N802
        super().showEvent(event)  # type: ignore[arg-type]
        self._fit_title()
        self._paint_marks()

    def mouseReleaseEvent(self, event: object) -> None:  # noqa: N802
        if not self._collapsible:
            super().mouseReleaseEvent(event)  # type: ignore[arg-type]
            return
        pos = event.pos()  # type: ignore[attr-defined]
        child = self.childAt(pos)
        if child is not None and (child is self._button or self._action_holds(child)):
            super().mouseReleaseEvent(event)  # type: ignore[arg-type]
            return
        self.click()

    def keyPressEvent(self, event: object) -> None:  # noqa: N802
        key = event.key()  # type: ignore[attr-defined]
        if self._collapsible and self._button is None and key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.click()
            return
        super().keyPressEvent(event)  # type: ignore[arg-type]

    def _button_clicked(self, checked: bool) -> None:
        self._expanded = bool(checked)
        self._sync_chevron()
        self.clicked.emit(self._expanded)
        self.toggled.emit(self._expanded)

    def _set_expanded(self, expanded: bool, *, emit: bool) -> None:
        self._expanded = expanded
        if self._button is not None:
            self._button.setChecked(expanded)
        self._sync_chevron()
        if emit:
            self.clicked.emit(expanded)
            self.toggled.emit(expanded)

    def _sync_chevron(self, *_args: object) -> None:
        if not self._collapsible:
            return
        self._paint_marks()

    def _paint_marks(self) -> None:
        chrome = self._chrome
        ink = chrome.icon_muted if chrome is not None else ""
        if not ink:
            return
        dpr = float(self.devicePixelRatioF()) if hasattr(self, "devicePixelRatioF") else 1.0
        if self._collapsible:
            name = "chevron_down" if self.isChecked() else "chevron_right"
            self._chevron.setPixmap(paint_glyph(name, ink, CHEVRON, dpr))
        for button, glyph in self._actions:
            button.setIcon(QIcon(paint_glyph(glyph, ink, ICON, dpr)))
            button.setIconSize(_icon_size())

    def _action_holds(self, widget: QWidget) -> bool:
        for button, _glyph in self._actions:
            if widget is button or button.isAncestorOf(widget):
                return True
        return False

    def _fit_title(self) -> None:
        widget = self._button if self._button is not None else self._label
        text = widget.text()
        metrics = widget.fontMetrics()
        width = max(int(metrics.horizontalAdvance(text)), int(metrics.boundingRect(text).width()), 1)
        if widget.width() != width or widget.minimumWidth() != width:
            widget.setFixedWidth(width)

    @staticmethod
    def _title_font() -> QFont:
        font = QFont()
        font.setPixelSize(TYPE_SECTION)
        font.setWeight(_weight("Bold"))
        font.setLetterSpacing(QFont.AbsoluteSpacing, LETTER_SECTION)
        return font

    @staticmethod
    def _count_font() -> QFont:
        font = QFont()
        font.setPixelSize(TYPE_FINE)
        return font

    @staticmethod
    def _focus(name: str) -> Qt.FocusPolicy:
        return getattr(getattr(Qt, "FocusPolicy", Qt), name)

    @staticmethod
    def _no_arrow() -> Qt.ArrowType:
        arrows = getattr(Qt, "ArrowType", Qt)
        return getattr(arrows, "NoArrow")

    @staticmethod
    def _text_only() -> Qt.ToolButtonStyle:
        styles = getattr(Qt, "ToolButtonStyle", Qt)
        return getattr(styles, "ToolButtonTextOnly")

    @staticmethod
    def _left() -> Qt.AlignmentFlag:
        flags = getattr(Qt, "AlignmentFlag", Qt)
        return getattr(flags, "AlignLeft") | getattr(flags, "AlignVCenter")


def _weight(name: str) -> QFont.Weight:
    return getattr(getattr(QFont, "Weight", QFont), name)


def _escape(name: str) -> str:
    return name.replace(".", "\\.")


def _action_selector(actions: List[Tuple[QToolButton, str]], suffix: str = "") -> str:
    names = []
    for button, _glyph in actions:
        name = button.objectName() or "shell.outlinePanel.action.more"
        if name not in names:
            names.append(name)
    if not names:
        names.append("shell.outlinePanel.action.more")
    return ", ".join("QToolButton#%s%s" % (_escape(name), suffix) for name in names)


def _icon_size() -> QSize:
    return QSize(ICON, ICON)
