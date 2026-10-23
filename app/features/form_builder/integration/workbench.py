"""Workbench panes and the tab toolbar (UX-WB-001..003, UX-RESP).

Widths come from a ``LayoutPlan``. This module does not decide breakpoints.
"""

from __future__ import annotations

from typing import Callable, List, Optional, Sequence, Tuple

from app.qt.QtCore import QSize, Qt
from app.qt.QtGui import QColor, QPainter
from app.qt.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QSplitterHandle,
    QStackedWidget,
    QTabWidget,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)
from app.qt.qt_compat import event_pos

from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import LayoutNode, SpacerNode, WidgetNode
from app.features.form_builder.integration.canvas import FormCanvas
from app.features.form_builder.integration.layout import (
    INSPECTOR_MAX,
    INSPECTOR_MIN,
    LEFT_MAX,
    LEFT_MIN,
    LayoutPlan,
    RAIL_WIDTH,
)
from app.features.form_builder.integration.structure import structure_entries
from app.features.form_builder.qtside.realize.api import Realizer
from app.features.form_builder.qtside.theme.chrome import (
    SEARCH_GLYPH,
    SEARCH_GLYPH_PX,
    SPLITTER_HIT_PX,
    ChromeTokens,
    Height,
    Radius,
    Space,
    chrome_tokens,
    elevation,
    font_css,
)
from app.shell.theme_tokens import ShellThemeTokens

Choice = Tuple[str, Callable[[], None]]


def _strong() -> Qt.FocusPolicy:
    return getattr(getattr(Qt, "FocusPolicy", Qt), "StrongFocus")


def _transparent() -> Qt.WidgetAttribute:
    return getattr(getattr(Qt, "WidgetAttribute", Qt), "WA_TransparentForMouseEvents")


def _align(*names: str) -> Qt.Alignment:
    flag = getattr(Qt, "AlignmentFlag", Qt)
    value = getattr(flag, names[0])
    for name in names[1:]:
        value = value | getattr(flag, name)
    return value


def _top_left() -> Qt.Alignment:
    return _align("AlignLeft", "AlignTop")


def _center() -> Qt.Alignment:
    return _align("AlignHCenter", "AlignVCenter")


def _policy(name: str) -> QSizePolicy.Policy:
    return getattr(getattr(QSizePolicy, "Policy", QSizePolicy), name)


def _button(text: str, name: str, tip: str, parent: QWidget) -> QPushButton:
    button = QPushButton(text, parent)
    button.setObjectName(name)
    button.setToolTip(tip)
    button.setAccessibleName(text or tip)
    button.setFocusPolicy(_strong())
    return button


def _tool(text: str, name: str, tip: str, parent: QWidget) -> QToolButton:
    button = QToolButton(parent)
    button.setObjectName(name)
    button.setText(text)
    button.setToolTip(tip)
    button.setAccessibleName(text or tip)
    button.setFocusPolicy(_strong())
    button.setAutoRaise(True)
    button.setToolButtonStyle(getattr(Qt, "ToolButtonTextOnly"))
    return button


class _LineSplitter(QSplitter):
    """1 px line, ``SPLITTER_HIT_PX`` grab. Stylesheet margins paint the whole handle."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._line: Optional[QColor] = None
        self._fill: Optional[QColor] = None
        self.setHandleWidth(SPLITTER_HIT_PX)

    def set_line(self, line: QColor, fill: QColor) -> None:
        self._line = QColor(line)
        self._fill = QColor(fill)
        index = 1
        while index < self.count():
            self.handle(index).update()
            index += 1

    def line_color(self) -> Optional[QColor]:
        return self._line

    def fill_color(self) -> Optional[QColor]:
        return self._fill

    def createHandle(self) -> QSplitterHandle:  # noqa: N802
        return _LineHandle(self.orientation(), self)


class _LineHandle(QSplitterHandle):
    def paintEvent(self, event: object) -> None:  # noqa: N802
        parent = self.splitter()
        line = parent.line_color() if isinstance(parent, _LineSplitter) else None
        fill = parent.fill_color() if isinstance(parent, _LineSplitter) else None
        if line is None or fill is None:
            super().paintEvent(event)  # type: ignore[arg-type]
            return
        painter = QPainter(self)
        painter.setRenderHint(getattr(getattr(QPainter, "RenderHint", QPainter), "Antialiasing"), False)
        painter.fillRect(self.rect(), fill)
        rect = self.rect()
        horizontal = getattr(getattr(Qt, "Orientation", Qt), "Horizontal")
        if self.orientation() == horizontal:
            x = rect.x() + (rect.width() - 1) // 2
            painter.fillRect(x, rect.y(), 1, rect.height(), line)
        else:
            y = rect.y() + (rect.height() - 1) // 2
            painter.fillRect(rect.x(), y, rect.width(), 1, line)
        painter.end()


class NoticeBar(QFrame):
    """One info bar for a recovered draft or a file that changed on disk."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.notice")
        self._row = QHBoxLayout(self)
        self._row.setContentsMargins(int(Space.S), int(Space.XS), int(Space.XS), int(Space.XS))
        self._row.setSpacing(int(Space.S))
        self._label = QLabel(self)
        self._label.setObjectName("formBuilder.noticeText")
        self._label.setWordWrap(True)
        self._row.addWidget(self._label, 1)
        self._buttons: List[QPushButton] = []
        self.hide()

    def show_choices(self, text: str, choices: Sequence[Choice]) -> None:
        self._label.setText(text)
        self._label.setAccessibleName(text)
        for button in self._buttons:
            self._row.removeWidget(button)
            button.deleteLater()
        self._buttons = []
        for label, callback in choices:
            button = _button(label, "formBuilder.noticeButton", label, self)
            button.clicked.connect(callback)
            self._row.addWidget(button, 0)
            self._buttons.append(button)
        self.show()

    def dismiss(self) -> None:
        self.hide()


class FormToolbar(QWidget):
    """36 px bar. Design | XML replaces the single View XML toggle."""

    def __init__(
        self,
        parent: QWidget,
        *,
        on_design: Callable[[], None],
        on_xml: Callable[[bool], None],
        on_undo: Callable[[], None],
        on_redo: Callable[[], None],
    ) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.toolbar")
        self.setFixedHeight(int(Height.TOOLBAR))
        row = QHBoxLayout(self)
        row.setContentsMargins(int(Space.S), 0, int(Space.S), 0)
        row.setSpacing(int(Space.XS))

        self._mode = QWidget(self)
        self._mode.setObjectName("formBuilder.modeGroup")
        self._mode.setAccessibleName("Design or XML")
        mode_row = QHBoxLayout(self._mode)
        mode_row.setContentsMargins(0, 0, 0, 0)
        mode_row.setSpacing(0)
        self.design = _tool("Design", "formBuilder.design", "Design", self._mode)
        self.design.setCheckable(True)
        self.design.setChecked(True)
        self.design.clicked.connect(on_design)
        self.xml = _tool("XML", "formBuilder.viewXml", "View XML (Ctrl+Shift+V)", self._mode)
        self.xml.setCheckable(True)
        self.xml.toggled.connect(on_xml)
        mode_row.addWidget(self.design)
        mode_row.addWidget(self.xml)
        row.addWidget(self._mode, 0)
        self._divider = QFrame(self)
        self._divider.setObjectName("formBuilder.modeDivider")
        self._divider.setFixedWidth(1)
        self._divider.setFixedHeight(18)
        row.addWidget(self._divider)

        self.tab_order = _tool(
            "Tab order",
            "formBuilder.tabOrder",
            "Tab order is not available yet",
            self,
        )
        self.tab_order.setEnabled(False)
        self.buddies = _tool("Buddies", "formBuilder.buddies", "Buddies are not available yet", self)
        self.buddies.setEnabled(False)
        row.addWidget(self.tab_order)
        row.addWidget(self.buddies)

        self.undo = _tool("Undo", "formBuilder.undo", "Undo (Ctrl+Z)", self)
        self.redo = _tool("Redo", "formBuilder.redo", "Redo (Ctrl+Shift+Z)", self)
        self.undo.clicked.connect(on_undo)
        self.redo.clicked.connect(on_redo)
        row.addWidget(self.undo)
        row.addWidget(self.redo)

        self.zoom_out = _tool("−", "formBuilder.zoomOut", "Zoom is not available yet", self)
        self.zoom_label = _tool("100%", "formBuilder.zoomLabel", "Zoom is not available yet", self)
        self.zoom_in = _tool("+", "formBuilder.zoomIn", "Zoom is not available yet", self)
        for button in (self.zoom_out, self.zoom_label, self.zoom_in):
            button.setEnabled(False)
            row.addWidget(button)
        self.text_size = _tool("Aa", "formBuilder.textSize", "Text size is not available yet", self)
        self.two_widths = _tool("Widths", "formBuilder.twoWidths", "Two widths is not available yet", self)
        self.text_size.setEnabled(False)
        self.two_widths.setEnabled(False)
        row.addWidget(self.text_size)
        row.addWidget(self.two_widths)

        self.preview = _tool("Preview", "formBuilder.preview", "Preview is not available yet", self)
        self.preview.setEnabled(False)
        row.addWidget(self.preview)

        self.overflow = QToolButton(self)
        self.overflow.setObjectName("formBuilder.overflow")
        self.overflow.setText("⋯")
        self.overflow.setToolTip("More")
        self.overflow.setAccessibleName("More")
        self.overflow.setAutoRaise(True)
        self.overflow.setToolButtonStyle(getattr(Qt, "ToolButtonTextOnly"))
        self.overflow.setFocusPolicy(_strong())
        self.overflow.setPopupMode(getattr(QToolButton, "ToolButtonPopupMode", QToolButton).InstantPopup)
        self._menu = QMenu(self.overflow)
        self._menu.addAction("Text size").setEnabled(False)
        self._menu.addAction("Two widths").setEnabled(False)
        self.overflow.setMenu(self._menu)
        self.overflow.hide()
        row.addWidget(self.overflow)

        row.addStretch(1)
        self.save_state = QLabel(self)
        self.save_state.setObjectName("formBuilder.saveState")
        self.save_state.setAccessibleName("Save state")
        row.addWidget(self.save_state, 0)

    def set_compact(self, compact: bool) -> None:
        self.tab_order.setText("⇥" if compact else "Tab order")
        self.buddies.setText("↔" if compact else "Buddies")
        self.text_size.setVisible(not compact)
        self.two_widths.setVisible(not compact)
        self.overflow.setVisible(compact)

    def set_undo(self, enabled: bool, tip: str) -> None:
        self.undo.setEnabled(enabled)
        self.undo.setToolTip(tip)

    def set_redo(self, enabled: bool, tip: str) -> None:
        self.redo.setEnabled(enabled)
        self.redo.setToolTip(tip)

    def set_save(self, text: str, *, error: bool, tokens: Optional[ShellThemeTokens]) -> None:
        self.save_state.setText(text)
        if tokens is None:
            return
        chrome = chrome_tokens(tokens)
        role = "error" if error else "faint"
        self.save_state.setStyleSheet(
            "QLabel#formBuilder\\.saveState { color: %s; background: transparent; border: none; }"
            % chrome.paint(role, "panel")
        )

    def apply_theme(self, tokens: ShellThemeTokens) -> None:
        self.setStyleSheet(_toolbar_qss(chrome_tokens(tokens)))


def _join(selectors: Sequence[str], suffix: str) -> str:
    return ", ".join("%s%s" % (selector, suffix) for selector in selectors)


def _flat_tools(chrome: ChromeTokens, selectors: Sequence[str]) -> str:
    return (
        "%s { color: %s; background: transparent; border: 1px solid transparent; padding: 0px %dpx; }"
        "%s { color: %s; background: %s; }"
        "%s { color: %s; background: %s; }"
        "%s { color: %s; }"
        "%s { border: %dpx solid %s; }"
        % (
            ", ".join(selectors),
            chrome.paint("text", "panel"),
            int(Space.S),
            _join(selectors, ":hover"),
            chrome.paint("text", "row_hover"),
            chrome.row_hover,
            _join(selectors, ":checked"),
            chrome.paint("text", "row_selected"),
            chrome.row_selected,
            _join(selectors, ":disabled"),
            chrome.paint("faint", "panel"),
            _join(selectors, ":focus"),
            chrome.focus_width,
            chrome.paint("accent", "panel"),
        )
    )


def _mode_group_qss(chrome: ChromeTokens) -> str:
    return (
        "QWidget#formBuilder\\.modeGroup {"
        " border: 1px solid %s; border-radius: %dpx; background: %s; }"
        "QWidget#formBuilder\\.modeGroup QToolButton {"
        " background: transparent; color: %s; border: none;"
        " border-right: 1px solid %s; border-radius: 0; padding: %dpx %dpx; %s }"
        "QWidget#formBuilder\\.modeGroup QToolButton:hover { background: %s; color: %s; }"
        "QWidget#formBuilder\\.modeGroup QToolButton:checked { background: %s; color: %s; }"
        "QWidget#formBuilder\\.modeGroup QToolButton:disabled { color: %s; }"
        "QWidget#formBuilder\\.modeGroup QToolButton:focus { border: %dpx solid %s; }"
        "QWidget#formBuilder\\.modeGroup QToolButton#formBuilder\\.viewXml { border-right: none; }"
        % (
            chrome.border,
            int(Radius.CONTROL),
            chrome.input,
            chrome.paint("muted", "input"),
            chrome.border,
            int(Space.XS),
            int(Space.S),
            font_css(chrome.scale.caption),
            chrome.row_hover,
            chrome.paint("text", "row_hover"),
            chrome.row_selected,
            chrome.paint("text", "row_selected"),
            chrome.paint("faint", "input"),
            chrome.focus_width,
            chrome.paint("accent", "input"),
        )
    )


def _problem_summary_qss(chrome: ChromeTokens) -> str:
    return (
        "QWidget#formBuilder\\.problemSummaryRow { background: transparent; }"
        "QLabel#formBuilder\\.problemSummary { color: %s; background: transparent; border: none; %s }"
        "QPushButton#formBuilder\\.showProblems {"
        " color: %s; background: transparent; border: %dpx solid transparent; padding: 0px %dpx;"
        " text-decoration: underline; }"
        "QPushButton#formBuilder\\.showProblems:focus { border: %dpx solid %s; }"
        % (
            chrome.paint("text", "panel"),
            font_css(chrome.scale.body),
            chrome.paint("text", "panel"),
            chrome.focus_width,
            int(Space.XS),
            chrome.focus_width,
            chrome.paint("accent", "panel"),
        )
    )


def _toolbar_qss(chrome: ChromeTokens) -> str:
    names = (
        "tabOrder",
        "buddies",
        "undo",
        "redo",
        "zoomOut",
        "zoomLabel",
        "zoomIn",
        "textSize",
        "twoWidths",
        "preview",
        "overflow",
    )
    selectors = ["QToolButton#formBuilder\\.%s" % name for name in names]
    return "".join(
        (
            "QWidget#formBuilder\\.toolbar { background: %s; color: %s; border-bottom: 1px solid %s; }"
            % (chrome.panel, chrome.paint("text", "panel"), chrome.border),
            _mode_group_qss(chrome),
            "QFrame#formBuilder\\.modeDivider { background: %s; border: none; }" % chrome.border,
            _flat_tools(chrome, selectors),
            "QLabel#formBuilder\\.saveState { color: %s; background: transparent; border: none; }"
            % chrome.paint("faint", "panel"),
        )
    )


def _search_qss() -> str:
    return (
        "QToolButton#formBuilder\\.sectionSearch {"
        " font-size: %dpx; padding: 0; border: none;"
        " min-width: %dpx; max-width: %dpx; min-height: %dpx; max-height: %dpx; }"
        % (
            SEARCH_GLYPH_PX,
            int(Height.CONTROL),
            int(Height.CONTROL),
            int(Height.CONTROL),
            int(Height.CONTROL),
        )
    )


def _pin_qss(chrome: ChromeTokens) -> str:
    return (
        "QToolButton#formBuilder\\.pin {"
        " color: %s; background: transparent; border: none; padding: 0px %dpx; }"
        "QToolButton#formBuilder\\.pin:hover { color: %s; background: %s; }"
        "QToolButton#formBuilder\\.pin:focus { border: %dpx solid %s; }"
        % (
            chrome.paint("text", "popup"),
            int(Space.S),
            chrome.paint("text", "row_hover"),
            chrome.row_hover,
            chrome.focus_width,
            chrome.paint("accent", "popup"),
        )
    )


def _level2_stroke(chrome: ChromeTokens) -> Tuple[int, str]:
    level = elevation(2, chrome)
    if level.border_px >= 2:
        return level.border_px, chrome.paint("text", "popup")
    return level.border_px, chrome.popup_border


class _Header(QWidget):
    """Overline row. The row toggles the pane. The buttons on the right do not."""

    def __init__(self, title: str, parent: QWidget, on_toggle: Callable[[], None]) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.sectionHeader")
        self.setFixedHeight(int(Height.SECTION))
        self.setAccessibleName(title)
        self.setFocusPolicy(_strong())
        self._on_toggle = on_toggle
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(int(Space.XS))
        self.title = QLabel(title.upper(), self)
        self.title.setObjectName("formBuilder.sectionTitle")
        self.title.setAttribute(_transparent(), True)
        row.addWidget(self.title, 1)
        self.extra: List[QToolButton] = []

    def add_extra(self, text: str, tip: str, name: str) -> QToolButton:
        button = _tool(text, name, tip, self)
        if name == "formBuilder.sectionSearch":
            button.setFixedSize(int(Height.CONTROL), int(Height.CONTROL))
        button.setEnabled(False)
        button.setAccessibleName(tip)
        layout = self.layout()
        assert layout is not None
        layout.addWidget(button)
        self.extra.append(button)
        return button

    def mousePressEvent(self, event: object) -> None:  # noqa: N802
        left = getattr(getattr(Qt, "MouseButton", Qt), "LeftButton")
        if getattr(event, "button", lambda: None)() == left:
            pos = event_pos(event)
            for button in self.extra:
                if button.geometry().contains(pos):
                    super().mousePressEvent(event)  # type: ignore[arg-type]
                    return
            self._on_toggle()
            event.accept()  # type: ignore[attr-defined]
            return
        super().mousePressEvent(event)  # type: ignore[arg-type]

    def keyPressEvent(self, event: object) -> None:  # noqa: N802
        key = getattr(event, "key", lambda: None)()
        keys = getattr(Qt, "Key", Qt)
        if key in (getattr(keys, "Key_Return"), getattr(keys, "Key_Enter"), getattr(keys, "Key_Space")):
            self._on_toggle()
            event.accept()  # type: ignore[attr-defined]
            return
        super().keyPressEvent(event)  # type: ignore[arg-type]


class OutlinePane(QWidget):
    """Read-only structure tree. Selection is written to the session."""

    def __init__(
        self,
        on_pick: Callable[[NodeId], None],
        on_collapsed: Callable[[bool], None],
        parent: QWidget,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.outline")
        self._on_pick = on_pick
        self._on_collapsed = on_collapsed
        self._blocked = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.header = _Header("Outline", self, self._toggle)
        self.header.add_extra("+", "Not available yet", "formBuilder.sectionAdd")
        self.header.add_extra(SEARCH_GLYPH, "Not available yet", "formBuilder.sectionSearch")
        layout.addWidget(self.header)
        self.tree = QTreeWidget(self)
        self.tree.setObjectName("formBuilder.structure")
        self.tree.setAccessibleName("Form structure")
        self.tree.setHeaderHidden(True)
        self.tree.setFocusPolicy(_strong())
        triggers = getattr(self.tree, "EditTrigger", type(self.tree))
        self.tree.setEditTriggers(getattr(triggers, "NoEditTriggers", 0))
        mode = getattr(self.tree, "SelectionMode", type(self.tree))
        self.tree.setSelectionMode(getattr(mode, "SingleSelection"))
        self.tree.currentItemChanged.connect(self._current_changed)
        layout.addWidget(self.tree, 1)
        self._collapsed = False

    def set_collapsed(self, collapsed: bool) -> None:
        self._collapsed = collapsed
        self.tree.setVisible(not collapsed)

    def rebuild(self, document: UiDocument, selected: Optional[NodeId]) -> None:
        self._blocked = True
        self.tree.clear()
        parents: dict[int, QTreeWidgetItem] = {}
        role = getattr(Qt, "UserRole")
        current: Optional[QTreeWidgetItem] = None
        for entry in structure_entries(document):
            item = QTreeWidgetItem([entry.label])
            item.setData(0, role, int(entry.node_id))
            parent = parents.get(entry.depth - 1)
            if parent is None:
                self.tree.addTopLevelItem(item)
            else:
                parent.addChild(item)
            parents[entry.depth] = item
            for deeper in [key for key in parents if key > entry.depth]:
                del parents[deeper]
            if selected is not None and entry.node_id == selected:
                current = item
        self.tree.expandAll()
        if current is not None:
            self.tree.setCurrentItem(current)
        self._blocked = False

    def show_for_design(self) -> None:
        self.tree.setVisible(not self._collapsed)

    def _toggle(self) -> None:
        self.set_collapsed(not self._collapsed)
        self._on_collapsed(self._collapsed)

    def _current_changed(self, current: Optional[QTreeWidgetItem], _previous: object) -> None:
        if self._blocked or current is None:
            return
        raw = current.data(0, getattr(Qt, "UserRole"))
        if raw is None:
            return
        self._on_pick(NodeId(int(raw)))


class InsertPane(QWidget):
    def __init__(self, on_collapsed: Callable[[bool], None], parent: QWidget) -> None:
        super().__init__(parent)
        self._on_collapsed = on_collapsed
        self.setObjectName("formBuilder.insert")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.header = _Header("Insert", self, self._toggle)
        self.header.add_extra(SEARCH_GLYPH, "Not available yet", "formBuilder.sectionSearch")
        layout.addWidget(self.header)
        self.body = QLabel("Widgets you can place will show up here.", self)
        self.body.setObjectName("formBuilder.insertBody")
        self.body.setAccessibleName("Insert")
        self.body.setWordWrap(True)
        self.body.setAlignment(_top_left())
        self.body.setFocusPolicy(_strong())
        layout.addWidget(self.body, 1)
        self._collapsed = False

    def set_collapsed(self, collapsed: bool) -> None:
        self._collapsed = collapsed
        self.body.setVisible(not collapsed)

    def _toggle(self) -> None:
        self.set_collapsed(not self._collapsed)
        self._on_collapsed(self._collapsed)


class InspectorPane(QWidget):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.inspector")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._short = False
        self._title = ""
        self._kind = ""
        self._has_node = False
        self.header = QLabel("Inspector", self)
        self.header.setObjectName("formBuilder.inspectorHeader")
        self.header.setAccessibleName("Inspector")
        self.header.setFocusPolicy(_strong())
        layout.addWidget(self.header)
        self.tabs = QTabWidget(self)
        self.tabs.setObjectName("formBuilder.inspectorTabs")
        self.tabs.setFocusPolicy(_strong())
        self.properties = QLabel("Select a widget to see its properties.", self.tabs)
        self.properties.setObjectName("formBuilder.inspectorBody")
        self.properties.setWordWrap(True)
        self.properties.setAccessibleName("Properties")
        self.properties.setFocusPolicy(_strong())
        self.behavior = QLabel("Select a widget to see what you can configure.", self.tabs)
        self.behavior.setObjectName("formBuilder.behaviorBody")
        self.behavior.setWordWrap(True)
        self.behavior.setAccessibleName("Behavior")
        self.behavior.setFocusPolicy(_strong())
        self.tabs.addTab(self.properties, "Properties")
        self.tabs.addTab(self.behavior, "Behavior")
        layout.addWidget(self.tabs, 1)
        self._summary_row = QWidget(self)
        self._summary_row.setObjectName("formBuilder.problemSummaryRow")
        summary_layout = QHBoxLayout(self._summary_row)
        summary_layout.setContentsMargins(0, int(Space.XS), 0, 0)
        summary_layout.setSpacing(int(Space.S))
        self.problem_summary = QLabel(self._summary_row)
        self.problem_summary.setObjectName("formBuilder.problemSummary")
        self.problem_summary.setAccessibleName("Problems")
        self.problem_summary.setWordWrap(True)
        summary_layout.addWidget(self.problem_summary, 1)
        self.show_problems = _button(
            "Show in Problems",
            "formBuilder.showProblems",
            "Show in Problems",
            self._summary_row,
        )
        summary_layout.addWidget(self.show_problems, 0)
        self._summary_row.hide()
        layout.addWidget(self._summary_row)

    def set_short(self, short: bool) -> None:
        self._short = short
        self._paint_header()

    def set_problem_summary(self, text: str) -> None:
        self.problem_summary.setText(text)
        self._sync_summary()

    def show_selection(self, document: UiDocument, selected: Optional[NodeId]) -> None:
        node = None if selected is None else document.get(selected)
        self._has_node = node is not None
        if node is None:
            self._title = ""
            self._kind = ""
            self.properties.setText("Select a widget to see its properties.")
            self.behavior.setText("Select a widget to see what you can configure.")
        else:
            self._title, self._kind = _node_title(node)
            self.properties.setText("Properties are not available yet.")
            self.behavior.setText("Nothing to configure on this widget yet.")
        self._sync_summary()
        self._paint_header()

    def show_problem(self, document: UiDocument, selected: NodeId, sentence: str) -> None:
        self.show_selection(document, selected)
        if sentence:
            self.properties.setText(sentence)

    def _sync_summary(self) -> None:
        self._summary_row.setVisible(bool(self.problem_summary.text()) and not self._has_node)

    def _paint_header(self) -> None:
        if not self._has_node:
            self.header.setText("Inspector")
            return
        if self._short:
            text = "%s · %s" % (self._title, self._kind) if self._title else self._kind
        else:
            text = "%s\n%s" % (self._title, self._kind) if self._title else self._kind
        self.header.setText(text)


def _node_title(node: object) -> Tuple[str, str]:
    if isinstance(node, WidgetNode):
        return node.object_name, node.class_name or "Widget"
    if isinstance(node, LayoutNode):
        return node.object_name, node.class_name or "Layout"
    if isinstance(node, SpacerNode):
        return node.name, "Spacer"
    return "", "Item"


class _RailButton(QToolButton):
    """Keeps a 36 px rail from growing to the width of the button's words."""

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(32, 40)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(24, 32)


class _Rail(QWidget):
    def __init__(self, name: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName(name)
        self._layout = QVBoxLayout(self)
        # 2 px is the inset that still leaves a 32 px button inside a 36 px rail.
        self._layout.setContentsMargins(2, int(Space.XS), 2, int(Space.XS))
        self._layout.setSpacing(2)
        self._layout.addStretch(1)

    def add_button(self, name: str, label: str, on_click: Callable[[], None]) -> QToolButton:
        button = _RailButton(self)
        button.setObjectName(name)
        button.setText("")
        button.setToolTip(label)
        button.setAccessibleName(label)
        button.setFocusPolicy(_strong())
        button.setAutoRaise(True)
        button.setToolButtonStyle(getattr(Qt, "ToolButtonTextOnly"))
        button.setSizePolicy(_policy("Ignored"), _policy("Fixed"))
        button.setFixedSize(32, 40)
        caption = QLabel(label, button)
        caption.setObjectName("formBuilder.railLabel")
        caption.setWordWrap(True)
        caption.setAlignment(_center())
        caption.setAttribute(_transparent(), True)
        caption.setGeometry(0, 2, 32, 36)
        button.clicked.connect(lambda _checked=False, call=on_click: call())
        self._layout.insertWidget(self._layout.count() - 1, button)
        return button


class FormWorkbench(QWidget):
    """Outline, insert, canvas, and inspector. Drawers reparent the same panes."""

    def __init__(
        self,
        session: FormSession,
        realizer: Realizer,
        on_pick: Callable[[NodeId], None],
        on_pin_left: Callable[[], None],
        on_pin_inspector: Callable[[], None],
        on_widths: Callable[[int, int], None],
        on_collapsed: Callable[[str, bool], None],
        parent: QWidget,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.workbench")
        self._session = session
        self._on_pin_left = on_pin_left
        self._on_pin_inspector = on_pin_inspector
        self._on_widths = on_widths
        self._on_collapsed = on_collapsed
        self._plan: Optional[LayoutPlan] = None
        self._applying = False
        self._left_open = False
        self._right_open = False
        self._drawer_listener: Optional[Callable[[], None]] = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self._splitter = _LineSplitter(self)
        self._splitter.setObjectName("formBuilder.splitter")
        self._splitter.setChildrenCollapsible(False)
        self._splitter.splitterMoved.connect(self._remember_widths)
        orient = getattr(Qt, "Orientation", Qt)
        self._splitter.setOrientation(getattr(orient, "Horizontal"))
        outer.addWidget(self._splitter, 1)

        self._left_stack = QStackedWidget(self._splitter)
        self.outline = OutlinePane(on_pick, lambda collapsed: on_collapsed("outline", collapsed), self._left_stack)
        self.insert = InsertPane(lambda collapsed: on_collapsed("insert", collapsed), self._left_stack)
        self._left_body = QWidget(self._left_stack)
        self._left_split = _LineSplitter(self._left_body)
        self._left_split.setObjectName("formBuilder.leftSplitter")
        self._left_split.setChildrenCollapsible(False)
        self._left_split.setOrientation(getattr(orient, "Vertical"))
        self._left_body.setObjectName("formBuilder.leftBody")
        left_layout = QVBoxLayout(self._left_body)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(self._left_split)
        self._left_tabs = QTabWidget(self._left_body)
        self._left_tabs.setObjectName("formBuilder.leftTabs")
        self._left_tabs.hide()
        left_layout.addWidget(self._left_tabs)
        self._left_split.addWidget(self.outline)
        self._left_split.addWidget(self.insert)
        self._left_rail = _Rail("formBuilder.leftRail", self._left_stack)
        self._left_rail.add_button("formBuilder.leftRail.outline", "Outline", self.focus_outline)
        self._left_rail.add_button("formBuilder.leftRail.insert", "Insert", self.focus_insert)
        self._left_stack.addWidget(self._left_body)
        self._left_stack.addWidget(self._left_rail)

        self.canvas = FormCanvas(session, realizer, self._splitter)
        self.canvas.set_drawer_closer(self.close_drawers)

        self._right_stack = QStackedWidget(self._splitter)
        self.inspector = InspectorPane(self._right_stack)
        self._right_rail = _Rail("formBuilder.rightRail", self._right_stack)
        self._right_rail.add_button(
            "formBuilder.rightRail.properties",
            "Properties",
            lambda: self._focus_inspector_tab(0),
        )
        self._right_rail.add_button(
            "formBuilder.rightRail.behavior",
            "Behavior",
            lambda: self._focus_inspector_tab(1),
        )
        self._right_stack.addWidget(self.inspector)
        self._right_stack.addWidget(self._right_rail)
        self._splitter.addWidget(self._left_stack)
        self._splitter.addWidget(self.canvas)
        self._splitter.addWidget(self._right_stack)

        self._drawer = QFrame(self)
        self._drawer.setObjectName("formBuilder.drawer")
        drawer_layout = QVBoxLayout(self._drawer)
        drawer_layout.setContentsMargins(0, 0, 0, 0)
        pin_row = QHBoxLayout()
        self._pin = _tool("Pin", "formBuilder.pin", "Keep this pane open", self._drawer)
        self._pin.clicked.connect(self._pin_clicked)
        pin_row.addStretch(1)
        pin_row.addWidget(self._pin)
        drawer_layout.addLayout(pin_row)
        self._drawer_host = QWidget(self._drawer)
        self._drawer_host_layout = QVBoxLayout(self._drawer_host)
        self._drawer_host_layout.setContentsMargins(0, 0, 0, 0)
        drawer_layout.addWidget(self._drawer_host, 1)
        self._drawer.hide()
        self._drawer_side = ""

    def canvas_view(self) -> FormCanvas:
        return self.canvas

    def refresh(self, selected: Optional[NodeId]) -> None:
        document = self._session.document
        self.outline.rebuild(document, selected)
        self.inspector.show_selection(document, selected)
        self.canvas.refresh_chip()

    def set_drawer_listener(self, callback: Callable[[], None]) -> None:
        self._drawer_listener = callback

    def apply_plan(self, plan: LayoutPlan) -> None:
        self._plan = plan
        self.inspector.set_short(plan.short)
        self._apply_padding(plan.padding)
        self._apply_short(plan.stack_left)
        if plan.left_docked:
            self._dock("left")
        else:
            self._show_rail("left")
        if plan.inspector_docked:
            self._dock("right")
        else:
            self._show_rail("right")
        self._size_panes(plan)
        self._place_drawer()

    def apply_theme(self, tokens: ShellThemeTokens) -> None:
        chrome = chrome_tokens(tokens)
        self._splitter.set_line(QColor(chrome.border), QColor(chrome.panel))
        self._left_split.set_line(QColor(chrome.border), QColor(chrome.panel))
        drawer_px, drawer_border = _level2_stroke(chrome)
        panes = (
            "QWidget#formBuilder\\.workbench, QWidget#formBuilder\\.outline,"
            " QWidget#formBuilder\\.insert, QWidget#formBuilder\\.inspector,"
            " QWidget#formBuilder\\.leftBody, QWidget#formBuilder\\.leftRail,"
            " QWidget#formBuilder\\.rightRail { background: %s; color: %s; }"
            % (chrome.panel, chrome.paint("text", "panel"))
        )
        tree = (
            "QTreeWidget#formBuilder\\.structure { background: %s; color: %s; border: 1px solid %s; }"
            "QTreeWidget#formBuilder\\.structure::item { min-height: %dpx; }"
            "QTreeWidget#formBuilder\\.structure::item:selected { background: %s; color: %s; }"
            "QTreeWidget#formBuilder\\.structure:focus { border: %dpx solid %s; }"
            % (
                chrome.input,
                chrome.paint("text", "input"),
                chrome.border,
                int(Height.OUTLINE_ROW),
                chrome.row_selected,
                chrome.paint("text", "row_selected"),
                chrome.focus_width,
                chrome.paint("accent", "input"),
            )
        )
        labels = (
            "QLabel#formBuilder\\.inspectorHeader { color: %s; background: transparent; border: none; %s }"
            "QLabel#formBuilder\\.inspectorBody, QLabel#formBuilder\\.behaviorBody {"
            " color: %s; background: transparent; border: none; %s }"
            "QLabel#formBuilder\\.insertBody { color: %s; background: transparent; border: none; %s }"
            "QWidget#formBuilder\\.sectionHeader { background: transparent; color: %s; border: none; }"
            "QWidget#formBuilder\\.sectionHeader:focus { border: %dpx solid %s; }"
            "QLabel#formBuilder\\.sectionTitle { color: %s; background: transparent; border: none; %s }"
            "QLabel#formBuilder\\.railLabel { color: %s; background: transparent; border: none; %s }"
            % (
                chrome.paint("text", "panel"),
                font_css(chrome.scale.title, lock_weight=True),
                chrome.paint("text", "panel"),
                font_css(chrome.scale.body),
                chrome.paint("muted", "panel"),
                font_css(chrome.scale.caption),
                chrome.paint("text", "panel"),
                chrome.focus_width,
                chrome.paint("accent", "panel"),
                chrome.paint("muted", "panel"),
                font_css(chrome.scale.overline, lock_weight=True),
                chrome.paint("muted", "panel"),
                font_css(chrome.scale.caption),
            )
        )
        drawer = (
            "QFrame#formBuilder\\.drawer {"
            " background: %s; color: %s; border: %dpx solid %s; border-radius: %dpx; }"
            % (
                chrome.popup,
                chrome.paint("text", "popup"),
                drawer_px,
                drawer_border,
                int(Radius.POPOVER),
            )
        )
        tabs = (
            "QTabWidget#formBuilder\\.inspectorTabs::pane, QTabWidget#formBuilder\\.leftTabs::pane {"
            " background: %s; color: %s; border: 1px solid %s; }"
            "QTabWidget#formBuilder\\.inspectorTabs QTabBar::tab,"
            " QTabWidget#formBuilder\\.leftTabs QTabBar::tab {"
            " background: %s; color: %s; border: 1px solid %s; padding: %dpx %dpx; }"
            "QTabWidget#formBuilder\\.inspectorTabs QTabBar::tab:selected,"
            " QTabWidget#formBuilder\\.leftTabs QTabBar::tab:selected { background: %s; color: %s; }"
            % (
                chrome.panel,
                chrome.paint("text", "panel"),
                chrome.border,
                chrome.panel,
                chrome.paint("text", "panel"),
                chrome.border,
                int(Space.XS),
                int(Space.S),
                chrome.row_selected,
                chrome.paint("text", "row_selected"),
            )
        )
        tools = _flat_tools(
            chrome,
            (
                "QToolButton#formBuilder\\.leftRail\\.outline",
                "QToolButton#formBuilder\\.leftRail\\.insert",
                "QToolButton#formBuilder\\.rightRail\\.properties",
                "QToolButton#formBuilder\\.rightRail\\.behavior",
                "QToolButton#formBuilder\\.sectionAdd",
                "QToolButton#formBuilder\\.sectionSearch",
            ),
        )
        self.setStyleSheet(
            panes + tree + labels + drawer + tabs + tools + _search_qss() + _pin_qss(chrome) + _problem_summary_qss(chrome)
        )
        self.canvas.apply_theme(tokens)

    def open_left(self) -> None:
        self._open_drawer("left")

    def open_right(self) -> None:
        self._open_drawer("right")

    def close_drawers(self) -> None:
        if not self._left_open and not self._right_open:
            return
        self._park_drawer_child()
        self._left_open = False
        self._right_open = False
        self._drawer.hide()
        plan = self._plan
        if plan is not None:
            self.apply_plan(plan)
        self._notify_drawer()

    def drawer_open(self) -> bool:
        return self._left_open or self._right_open

    def focus_outline(self) -> None:
        if self._plan is not None and not self._plan.left_docked:
            self.open_left()
        if self._plan is not None and self._plan.stack_left:
            self._left_tabs.setCurrentWidget(self.outline)
        self.outline.tree.setFocus()

    def focus_insert(self) -> None:
        if self._plan is not None and not self._plan.left_docked:
            self.open_left()
        if self._plan is not None and self._plan.stack_left:
            self._left_tabs.setCurrentWidget(self.insert)
        self.insert.body.setFocus()

    def focus_inspector(self) -> None:
        self._focus_inspector_tab(0)

    def _focus_inspector_tab(self, index: int) -> None:
        if self._plan is not None and not self._plan.inspector_docked:
            self.open_right()
        self.inspector.tabs.setCurrentIndex(index)
        page = self.inspector.tabs.widget(index)
        if page is not None:
            page.setFocus()

    def resizeEvent(self, event: object) -> None:  # noqa: N802
        super().resizeEvent(event)  # type: ignore[arg-type]
        if self._plan is not None:
            self._size_panes(self._plan)
        self._place_drawer()

    def _apply_short(self, stacked: bool) -> None:
        if stacked:
            if self._left_tabs.count() == 0:
                self._left_tabs.addTab(self.outline, "Outline")
                self._left_tabs.addTab(self.insert, "Insert")
            self._left_split.hide()
            self._left_tabs.show()
            return
        if self._left_split.indexOf(self.outline) < 0:
            self._left_tabs.removeTab(self._left_tabs.indexOf(self.outline))
            self._left_tabs.removeTab(self._left_tabs.indexOf(self.insert))
            self._left_split.addWidget(self.outline)
            self._left_split.addWidget(self.insert)
        self.outline.show()
        self.insert.show()
        self._left_tabs.hide()
        self._left_split.show()
        height = max(self._left_split.height(), 240)
        top = height * 55 // 100
        self._left_split.setSizes([top, max(80, height - top)])

    def _show_rail(self, side: str) -> None:
        if side == "left" and not self._left_open:
            self._left_stack.setCurrentWidget(self._left_rail)
        if side == "right" and not self._right_open:
            self._right_stack.setCurrentWidget(self._right_rail)

    def _dock(self, side: str) -> None:
        if side == "left":
            self._left_open = False
            self._return_body("left")
            self._left_stack.setCurrentWidget(self._left_body)
        else:
            self._right_open = False
            self._return_body("right")
            self._right_stack.setCurrentWidget(self.inspector)
        if not self._left_open and not self._right_open:
            self._drawer.hide()
        self._notify_drawer()

    def _open_drawer(self, side: str) -> None:
        self._park_drawer_child()
        self._left_open = side == "left"
        self._right_open = side == "right"
        self._drawer_side = side
        body = self._left_body if side == "left" else self.inspector
        self._drawer_host_layout.addWidget(body)
        body.show()
        if side == "left":
            self._left_stack.setCurrentWidget(self._left_rail)
        else:
            self._right_stack.setCurrentWidget(self._right_rail)
        self._drawer.show()
        self._drawer.raise_()
        self._place_drawer()
        self._notify_drawer()

    def _notify_drawer(self) -> None:
        listener = self._drawer_listener
        if listener is not None:
            listener()

    def _apply_padding(self, padding: int) -> None:
        for pane in (self.outline, self.insert, self.inspector):
            layout = pane.layout()
            if layout is not None:
                layout.setContentsMargins(padding, padding, padding, padding)

    def _park_drawer_child(self) -> None:
        if self._drawer_host_layout.count() == 0:
            return
        self._return_body(self._drawer_side)

    def _return_body(self, side: str) -> None:
        if side == "left":
            if self._left_body.parent() is not self._left_stack:
                self._left_stack.insertWidget(0, self._left_body)
        elif side == "right":
            if self.inspector.parent() is not self._right_stack:
                self._right_stack.insertWidget(0, self.inspector)

    def _pin_clicked(self) -> None:
        if self._drawer_side == "left":
            self._on_pin_left()
        elif self._drawer_side == "right":
            self._on_pin_inspector()

    def _place_drawer(self) -> None:
        if self._drawer.isHidden() or self._plan is None:
            return
        width = self._plan.drawer_width if self._drawer_side == "left" else self._plan.inspector_drawer
        x = RAIL_WIDTH if self._drawer_side == "left" else max(0, self.width() - RAIL_WIDTH - width)
        self._drawer.setGeometry(x, 0, width, self.height())
        self._drawer.raise_()

    def _remember_widths(self, _pos: int, _index: int) -> None:
        if self._applying:
            return
        plan = self._plan
        if plan is None or plan.density != "wide" or not plan.left_docked or not plan.inspector_docked:
            return
        sizes = self._splitter.sizes()
        if len(sizes) < 3:
            return
        self._on_widths(sizes[0], sizes[2])

    def _size_panes(self, plan: LayoutPlan) -> None:
        left = self._left_stack
        right = self._right_stack
        if plan.density == "wide" and plan.left_docked:
            left.setMinimumWidth(LEFT_MIN)
            left.setMaximumWidth(LEFT_MAX)
        else:
            left.setMinimumWidth(plan.left_width)
            left.setMaximumWidth(plan.left_width)
        if plan.density == "wide" and plan.inspector_docked:
            right.setMinimumWidth(INSPECTOR_MIN)
            right.setMaximumWidth(INSPECTOR_MAX)
        else:
            right.setMinimumWidth(plan.inspector_width)
            right.setMaximumWidth(plan.inspector_width)
        handle = self._splitter.handleWidth()
        canvas = max(0, self.width() - plan.left_width - plan.inspector_width - handle * 2)
        self._applying = True
        try:
            self._splitter.setSizes([plan.left_width, canvas, plan.inspector_width])
        finally:
            self._applying = False


__all__ = ["FormToolbar", "FormWorkbench", "NoticeBar"]
