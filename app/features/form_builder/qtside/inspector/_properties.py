
from __future__ import annotations

from collections import OrderedDict
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from app.features.form_builder.engine.commands.base import Command, CommandOutcome
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.values import EnumValue, SetValue, Value
from app.features.form_builder.qtside.inspector._services import Dropped, Rejected, Services, rejection_text
from app.features.form_builder.qtside.inspector.api import (
    NOT_SET_TEXT,
    Editor,
    EnumSpec,
    GroupBody,
    GroupBodyFactory,
    GROUP_ORDER,
    GroupId,
    LockedRow,
    Match,
    Mixed,
    OpenRow,
    Row,
    RowValue,
    Unset,
    set_style_flag,
)
from app.features.form_builder.qtside.inspector.model import (
    BodyView,
    FormBody,
    GroupView,
    value_text,
)
from app.qt.QtCore import QEvent, Qt
from app.qt.qt_compat import delete_now
from app.qt.QtGui import QFont
from app.qt.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

_DRAG = "Drag the page's right or bottom edge to try other sizes."
_LABEL_WIDE = 104
_LABEL_COMPACT = 96

class PropertiesPage(QWidget):

    def __init__(self, services: Services, on_search: Callable[[], None], parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.inspectorBody")
        self._services = services
        self._on_search = on_search
        self._match_color = ""
        self._expanded: Dict[GroupId, bool] = {group: group is not GroupId.ALL for group in GROUP_ORDER}
        self._label_width = _LABEL_WIDE
        self._show_qt = False
        self._qt_store: object = None
        self._link_color = ""
        self._search = QLineEdit(self)
        self._search.setObjectName("formBuilder.inspectorSearch")
        self._search.setPlaceholderText("Find a property")
        self._search.setAccessibleName("Find a property")
        self._search.textChanged.connect(self._search_changed)
        self._pill = QLabel(self)
        self._pill.setObjectName("formBuilder.inspectorFilter")
        self._pill.setTextFormat(Qt.RichText)
        self._pill.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self._pill.setOpenExternalLinks(False)
        self._pill.linkActivated.connect(lambda _link: self.clear_search())
        self._pill.hide()
        self._more = QToolButton(self)
        self._more.setObjectName("formBuilder.inspectorMenu")
        self._more.setText("\u22ef")
        self._more.setAccessibleName("Inspector menu")
        self._more.setAutoRaise(True)
        self._more.setPopupMode(_popup_mode())
        menu = QMenu(self._more)
        self._qt_names_action = menu.addAction("Qt names")
        self._qt_names_action.setCheckable(True)
        self._qt_names_action.toggled.connect(self._on_qt_names)
        self._more.setMenu(menu)
        self._scroll = QScrollArea(self)
        self._scroll.setObjectName("formBuilder.inspectorScroll")
        self._scroll.setAccessibleName("Properties")
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(_no_frame())
        self._scroll.setHorizontalScrollBarPolicy(_scroll_off())
        self._content = QWidget(self._scroll)
        self._content.setObjectName("formBuilder.inspectorContent")
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(8, 4, 8, 8)
        self._content_layout.setSpacing(4)
        self._form = _FormSection(services, self._content)
        self._content_layout.addWidget(self._form)
        self._groups: Dict[GroupId, _Group] = {}
        for group in GROUP_ORDER:
            widget = _Group(services, group, self, self._content)
            self._groups[group] = widget
            self._content_layout.addWidget(widget)
            widget.hide()
        self._content_layout.addStretch(1)
        self._scroll.setWidget(self._content)
        tools = QHBoxLayout()
        tools.setContentsMargins(0, 0, 0, 0)
        tools.setSpacing(0)
        tools.addWidget(self._search, 1)
        tools.addWidget(self._more, 0)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(tools)
        layout.addWidget(self._pill)
        layout.addWidget(self._scroll, 1)
        self.setFocusProxy(self._search)

    @property
    def search(self) -> str:
        return self._search.text()

    def set_problem_link(
        self, count: int, on_show: Optional[Callable[[], None]], color: str
    ) -> None:
        self._form.set_problem_link(count, on_show, color)

    def set_match_color(self, color: str) -> None:
        self._match_color = color

    def set_link_color(self, color: str) -> None:
        self._link_color = color
        self._search_changed(self._search.text())

    def set_compact(self, compact: bool) -> None:
        width = _LABEL_COMPACT if compact else _LABEL_WIDE
        if width == self._label_width:
            return
        self._label_width = width
        self._form.set_label_width(width)
        for group in self._groups.values():
            group.set_label_width(width)

    def set_group_expanded(self, group: object, expanded: bool) -> None:
        if not isinstance(group, GroupId):
            return
        self._expanded[group] = expanded
        widget = self._groups.get(group)
        if widget is not None:
            widget.set_checked(expanded)

    def builds_all_properties(self) -> bool:
        return bool(self.search.strip()) or self._expanded.get(GroupId.ALL, False)

    def note_focus(self, focus: object) -> None:
        self._form.note_focus(focus)
        for group in self._groups.values():
            group.note_focus(focus)

    def bind_qt_names(self, store: object) -> None:
        self._qt_store = store
        reader = getattr(store, "qt_names", None)
        shown = bool(reader()) if callable(reader) else False
        self._qt_names_action.setChecked(shown)

    def qt_names_visible(self) -> bool:
        return self._show_qt

    def request_rebuild(self) -> None:
        self._on_search()

    def apply_colors(self, panel: str, text: str, faint: str, hover: str = "", caption: str = "") -> None:
        """The scroll viewport does not inherit the inspector stylesheet."""
        self.setStyleSheet(
            "QWidget#formBuilder\\.inspectorBody { background: %s; color: %s; }"
            "QLabel { color: %s; background: transparent; }"
            "QCheckBox { color: %s; background: transparent; }"
            % (panel, text, text, text)
        )
        self._scroll.setStyleSheet(
            "QScrollArea#formBuilder\\.inspectorScroll { background: %s; border: none; }" % panel
        )
        viewport = self._scroll.viewport()
        viewport.setAutoFillBackground(False)
        # Scoped: a rule with no selector reaches every row and beats the
        # changed bar's accent.
        viewport.setObjectName("formBuilder.inspectorViewport")
        viewport.setStyleSheet("QWidget#formBuilder\\.inspectorViewport { background: %s; }" % panel)
        self._content.setStyleSheet(
            "QWidget#formBuilder\\.inspectorContent { background: %s; color: %s; }"
            "QLabel { color: %s; background: transparent; }"
            "QLabel#formBuilder\\.rowQtName, QLabel#formBuilder\\.rowDefault,"
            " QLabel#formBuilder\\.rowMixed, QLabel#formBuilder\\.formCaption { color: %s; }"
            "QCheckBox { color: %s; background: transparent; }"
            # Flat only for the row reset and group headers: an unscoped rule
            # also hid the checked state of the alignment segments.
            "QToolButton[fbFlat=\"true\"] { color: %s; background: transparent; border: none; }"
            "QSpinBox[fbState=\"unset\"], QDoubleSpinBox[fbState=\"unset\"], QComboBox[fbState=\"unset\"],"
            " QLineEdit[fbState=\"unset\"], QFontComboBox[fbState=\"unset\"], QCheckBox[fbState=\"unset\"]"
            " { color: %s; }"
            "QSpinBox[fbState=\"mixed\"], QDoubleSpinBox[fbState=\"mixed\"], QComboBox[fbState=\"mixed\"],"
            " QLineEdit[fbState=\"mixed\"], QFontComboBox[fbState=\"mixed\"], QCheckBox[fbState=\"mixed\"],"
            " QListWidget[fbState=\"mixed\"] { color: %s; font-style: italic; }"
            "QLabel#formBuilder\\.sizeWhy { color: %s; background: %s; }"
            % (panel, text, text, faint, text, text, faint, faint, caption or text, hover or panel)
        )

    def paint(self, body: BodyView) -> None:
        searching = bool(self.search.strip())
        if isinstance(body, FormBody):
            self._form.show()
            self._form.paint(body, self._match_color)
            for group in self._groups.values():
                group.hide()
            return
        self._form.hide()
        present = {view.group: view for view in body.groups}
        for group_id in GROUP_ORDER:
            group = self._groups[group_id]
            view = present.get(group_id)
            if view is None:
                group.hide()
                continue
            group.show()
            expanded = True if searching else self._expanded[group_id]
            group.paint(view, expanded, searching, self._match_color, body.owners, self._show_qt)

    def focus_search(self) -> None:
        self._search.setFocus()
        self._search.selectAll()

    def clear_search(self) -> None:
        self._search.clear()

    def focused_row_invalid(self) -> bool:
        focus = QApplication.focusWidget()
        if focus is None:
            return False
        row = self._row_holding(focus)
        return row is not None and row.is_invalid()

    def focused_row_dirty(self) -> bool:
        focus = QApplication.focusWidget()
        if focus is None:
            return False
        row = self._row_holding(focus)
        return row is not None and row.is_dirty()

    def revert_focused_row(self) -> None:
        focus = QApplication.focusWidget()
        if focus is None:
            return
        row = self._row_holding(focus)
        if row is not None:
            row.revert()

    def _search_changed(self, text: str) -> None:
        if text.strip():
            style = ""
            if self._link_color:
                style = ' style="color:%s"' % self._link_color
            self._pill.setText(
                "Filtered: %s \u00b7 <a href=\"clear\"%s>Clear</a>" % (_escape(text.strip()), style)
            )
            self._pill.show()
        else:
            self._pill.hide()
        self._on_search()

    def _on_qt_names(self, checked: bool) -> None:
        self._show_qt = bool(checked)
        writer = getattr(self._qt_store, "set_qt_names", None)
        if callable(writer):
            writer(self._show_qt)
        for group in self._groups.values():
            group.retint(self._show_qt)
        self._form.retint(self._show_qt)

    def _row_holding(self, focus: QWidget) -> Optional["_Row"]:
        found = self._form.row_holding(focus)
        if found is not None:
            return found
        for group in self._groups.values():
            found = group.row_holding(focus)
            if found is not None:
                return found
        return None

    def _set_expanded(self, group: GroupId, expanded: bool) -> None:
        self._expanded[group] = expanded

class _FormSection(QWidget):
    def __init__(self, services: Services, parent: QWidget) -> None:
        super().__init__(parent)
        self._services = services
        self._show_qt = False
        self._match_color = ""
        self._window = _Row(services, self)
        self._window.hide()
        self._size = QLabel(self)
        self._size.setObjectName("formBuilder.formDesignSize")
        self._drag = QLabel(_DRAG, self)
        self._drag.setWordWrap(True)
        self._layout_name = QLabel(self)
        self._order = QLabel(self)
        self._order.setWordWrap(True)
        self._problems = QLabel(self)
        self._problems.setObjectName("formBuilder.inspectorProblems")
        self._problems.setAccessibleName("Problems")
        flags = getattr(Qt, "TextInteractionFlag", Qt)
        self._problems.setTextInteractionFlags(
            flags.LinksAccessibleByMouse | flags.LinksAccessibleByKeyboard
        )
        self._problems.linkActivated.connect(self._follow_problem_link)
        self._problem_count: Optional[int] = None
        self._on_show_problems: Optional[Callable[[], None]] = None
        self._link_color = ""
        self._last_problems = ""
        self._files = QLabel(self)
        self._files.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self._layout = layout
        layout.addWidget(_caption(self, "window", "Window"))
        layout.addWidget(self._window)
        layout.addWidget(self._size)
        layout.addWidget(self._drag)
        layout.addWidget(_caption(self, "layout", "Layout"))
        layout.addWidget(self._layout_name)
        layout.addWidget(_caption(self, "tabOrder", "Tab order"))
        layout.addWidget(self._order)
        layout.addWidget(_caption(self, "problems", "Problems"))
        layout.addWidget(self._problems)
        layout.addWidget(_caption(self, "files", "Files"))
        layout.addWidget(self._files)

    def paint(self, body: FormBody, match_color: str) -> None:
        self._match_color = match_color
        window = body.window
        if window is None:
            self._window.hide()
        else:
            self._window.show()
            self._window.paint(window, match_color, self._show_qt)
            self._order_title()
        self._size.setText(body.design_size)
        self._layout_name.setText(body.root_layout)
        self._order.setText("\n".join(body.tab_order))
        self._last_problems = body.problems
        self._paint_problems()
        self._files.setText(body.files)

    def set_label_width(self, width: int) -> None:
        self._window.set_label_width(width)

    def note_focus(self, focus: object) -> None:
        self._window.note_focus(focus)

    def retint(self, show_qt: bool) -> None:
        self._show_qt = show_qt
        self._window.retint(show_qt)

    def _order_title(self) -> None:
        edit = self._window.findChild(QLineEdit)
        if edit is not None:
            QWidget.setTabOrder(edit, self._problems)

    def set_problem_link(
        self, count: int, on_show: Optional[Callable[[], None]], color: str
    ) -> None:
        """UX-PROB-003: the form view's problem line links to the Problems panel."""
        self._problem_count = count
        self._on_show_problems = on_show
        self._link_color = color
        self._paint_problems()

    def _paint_problems(self) -> None:
        count = self._problem_count
        if not count or self._on_show_problems is None:
            self._problems.setTextFormat(getattr(Qt, "PlainText"))
            self._problems.setText(self._last_problems)
            return
        noun = "problem" if count == 1 else "problems"
        style = ""
        if self._link_color:
            style = ' style="color:%s; text-decoration: underline;"' % self._link_color
        self._problems.setTextFormat(getattr(Qt, "RichText"))
        self._problems.setText(
            '%d %s. <a href="problems"%s>Show in Problems</a>' % (count, noun, style)
        )

    def _follow_problem_link(self, href: str) -> None:
        callback = self._on_show_problems
        if href == "problems" and callback is not None:
            callback()

    def row_holding(self, focus: QWidget) -> Optional["_Row"]:
        row = self._window
        if row is not None and (focus is row or row.isAncestorOf(focus)):
            return row
        return None

class _Group(QWidget):

    def __init__(self, services: Services, group: GroupId, page: PropertiesPage, parent: QWidget) -> None:
        super().__init__(parent)
        self._services = services
        self._group = group
        self._page = page
        self._view: Optional[GroupView] = None
        self._owners: Tuple[NodeId, ...] = ()
        self._searching = False
        self._match_color = ""
        self._rows: Dict[str, _Row] = {}
        self._spare: "OrderedDict[str, _Row]" = OrderedDict()
        self._titles: List[QLabel] = []
        self._qt_names = False
        self._custom: Optional[GroupBody] = None
        self._host: Optional[_GroupHost] = None
        self._toggle = QToolButton(self)
        self._toggle.setObjectName("formBuilder.group.%s" % group.value)
        self._toggle.setProperty("fbFlat", "true")
        self._toggle.setText(group.title.upper())
        self._toggle.setFont(_overline_font())
        self._toggle.setCheckable(True)
        self._toggle.setChecked(page._expanded[group])
        self._toggle.setToolButtonStyle(_beside())
        self._toggle.setArrowType(_arrow(page._expanded[group]))
        self._toggle.clicked.connect(lambda: self._toggled(self._toggle.isChecked()))
        self._body = QWidget(self)
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(0, 0, 0, 4)
        self._body_layout.setSpacing(2)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._toggle)
        layout.addWidget(self._body)

    def paint(
        self,
        view: GroupView,
        expanded: bool,
        searching: bool,
        match_color: str,
        owners: Tuple[NodeId, ...],
        qt_names: bool = False,
    ) -> None:
        self._view = view
        self._owners = owners
        self._searching = searching
        self._match_color = match_color
        self._qt_names = qt_names
        self._toggle.setText(view.group.title.upper())
        self._toggle.setChecked(expanded)
        self._toggle.setArrowType(_arrow(expanded))
        if not expanded:
            self._body.hide()
            self._drop_rows()
            return
        self._body.show()
        factory = self._services.catalog.group_body(view.group)
        if factory is not None:
            self._drop_rows()
            self._paint_custom(view, factory)
            return
        self._hide_custom()
        self._paint_rows(view, match_color)

    def set_label_width(self, width: int) -> None:
        for row in self._rows.values():
            row.set_label_width(width)

    def set_checked(self, expanded: bool) -> None:
        self._toggle.setChecked(expanded)
        self._toggle.setArrowType(_arrow(expanded))

    def note_focus(self, focus: object) -> None:
        for row in self._rows.values():
            row.note_focus(focus)

    def retint(self, show_qt: bool) -> None:
        self._qt_names = show_qt
        for row in self._rows.values():
            row.retint(show_qt)

    def row_holding(self, focus: QWidget) -> Optional["_Row"]:
        for row in self._rows.values():
            if focus is row or row.isAncestorOf(focus):
                return row
        return None

    def _toggled(self, checked: bool) -> None:
        if self._searching:
            self._toggle.setChecked(True)
            self._toggle.setArrowType(_arrow(True))
            return
        expanded = bool(checked)
        self._toggle.setArrowType(_arrow(expanded))
        self._page._set_expanded(self._group, expanded)
        if self._group is GroupId.ALL:
            if not expanded:
                self._body.hide()
                self._drop_rows()
            self._page.request_rebuild()
            return
        view = self._view
        if view is not None:
            self.paint(view, expanded, False, self._match_color, self._owners, self._qt_names)

    def _paint_custom(self, view: GroupView, factory: GroupBodyFactory) -> None:
        if self._custom is None:
            self._host = _GroupHost(self._services, self._owners)
            self._custom = factory(self._host, self._body)
            self._body_layout.addWidget(self._custom.widget)
        if self._host is not None:
            self._host.set_frame(self._owners, self._qt_names)
        self._custom.widget.show()
        self._custom.show(view.rows())

    def _hide_custom(self) -> None:
        custom = self._custom
        if custom is not None:
            custom.widget.hide()

    def _paint_rows(self, view: GroupView, match_color: str) -> None:
        wanted = [row.key for block in view.blocks for row in block.rows]
        for key in [key for key in self._rows if key not in wanted]:
            self._park(key, self._rows.pop(key))
        title_at = 0
        for block in view.blocks:
            if block.title:
                label = self._title_label(title_at)
                title_at += 1
                label.setText(block.title)
                label.show()
                self._body_layout.addWidget(label)
            for row in block.rows:
                widget = self._rows.get(row.key)
                if widget is None:
                    widget = self._spare.pop(row.key, None)
                    if widget is None:
                        widget = _Row(self._services, self._body)
                        widget.set_label_width(self._page._label_width)
                    self._rows[row.key] = widget
                # Paint first: a hidden row builds its editor without a polish
                # per child, and the one show below polishes the row at once.
                widget.paint(row, match_color, self._qt_names)
                self._body_layout.addWidget(widget)
                widget.show()
        for extra in self._titles[title_at:]:
            extra.hide()
            self._body_layout.removeWidget(extra)

    def _drop_rows(self) -> None:
        for key in list(self._rows):
            self._park(key, self._rows.pop(key))
        for title in self._titles:
            title.hide()

    def _title_label(self, index: int) -> QLabel:
        while len(self._titles) <= index:
            label = QLabel(self._body)
            label.setObjectName("formBuilder.blockTitle")
            label.setFont(_overline_font())
            self._titles.append(label)
        return self._titles[index]

    def _park(self, key: str, widget: _Row) -> None:
        focus = QApplication.focusWidget()
        if focus is not None and (focus is widget or widget.isAncestorOf(focus)):
            self._page.setFocus()
        self._body_layout.removeWidget(widget)
        widget.hide()
        previous = self._spare.pop(key, None)
        if previous is not None:
            delete_now(previous)
        self._spare[key] = widget
        while len(self._spare) > 160:
            delete_now(self._spare.popitem(last=False)[1])

_BAR_SLOT = 8

class _Row(QWidget):

    def __init__(self, services: Services, parent: QWidget) -> None:
        super().__init__(parent)
        self._services = services
        self._view: Optional[Row] = None
        self._editor: Optional[Editor] = None
        self._editor_key = ""
        self._spec_element = ""
        self._enum: Optional[EnumSpec] = None
        self._invalid = False
        self._fallback: Optional[QLabel] = None
        self._hovered = False
        self._qt_names = False
        self._match_color = ""
        self._painted_widget: Optional[QWidget] = None
        self._painted_sheet = ""
        # The changed bar, the Qt name, the reset button and the caption are
        # hidden on most rows. They are made on first use: a first build of
        # All properties shows about 60 rows, and each widget costs a polish.
        self._bar: Optional[QFrame] = None
        self._qt: Optional[QLabel] = None
        self._reset: Optional[QToolButton] = None
        self._caption: Optional[QLabel] = None
        self._label = QLabel(self)
        self._label.setWordWrap(True)
        self._label_col = QWidget(self)
        self._label_col.setFixedWidth(_LABEL_WIDE)
        self._column = QVBoxLayout(self._label_col)
        self._column.setContentsMargins(0, 0, 0, 0)
        self._column.setSpacing(0)
        self._column.addWidget(self._label)
        self._slot = QWidget(self)
        self._slot_layout = QVBoxLayout(self._slot)
        self._slot_layout.setContentsMargins(0, 0, 0, 0)
        self._line = QHBoxLayout()
        # Until a row is first changed, the margin holds the bar's 2 px and
        # the 6 px spacing after it, so every row's columns line up.
        self._line.setContentsMargins(_BAR_SLOT, 0, 0, 0)
        self._line.setSpacing(6)
        self._line.addWidget(self._label_col, 0)
        self._line.addWidget(self._slot, 1)
        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(0, 2, 0, 2)
        self._outer.setSpacing(2)
        self._outer.addLayout(self._line)

    def _bar_widget(self) -> QFrame:
        if self._bar is None:
            bar = QFrame(self)
            bar.setObjectName("formBuilder.rowChanged")
            bar.setFixedWidth(2)
            bar.setMinimumHeight(18)
            # The bar stays shown once made and fbChanged picks its colour,
            # so the columns do not move when a row is reset.
            self._line.setContentsMargins(0, 0, 0, 0)
            self._line.insertWidget(0, bar, 0)
            self._bar = bar
        return self._bar

    def _qt_label(self) -> QLabel:
        if self._qt is None:
            label = QLabel(self._label_col)
            label.setObjectName("formBuilder.rowQtName")
            label.hide()
            self._column.addWidget(label)
            self._qt = label
        return self._qt

    def _reset_button(self) -> QToolButton:
        if self._reset is None:
            button = QToolButton(self)
            button.setObjectName("formBuilder.rowReset")
            button.setProperty("fbFlat", "true")
            button.setText("\u21ba")
            button.setFixedSize(16, 16)
            button.setAccessibleName("Reset")
            button.setToolTip("Reset: remove this property from the file")
            button.clicked.connect(self._reset_clicked)
            button.hide()
            self._line.addWidget(button, 0)
            self._reset = button
        return self._reset

    def _caption_label(self) -> QLabel:
        if self._caption is None:
            label = QLabel(self)
            label.setWordWrap(True)
            label.hide()
            self._outer.addWidget(label)
            self._caption = label
        return self._caption

    def is_invalid(self) -> bool:
        return self._invalid

    def is_dirty(self) -> bool:
        """The editor shows text the user typed and has not committed."""
        dirty = getattr(self._editor, "is_dirty", None)
        return bool(dirty()) if callable(dirty) else False

    def paint(self, view: Row, match_color: str, qt_names: bool = False) -> None:
        self.setObjectName("formBuilder.row.%s" % view.key)
        previous = self._view
        self._view = view
        self._qt_names = qt_names
        self._match_color = match_color
        self._label.setToolTip(_tip(view))
        self._paint_label(view, match_color)
        self._paint_qt(view, match_color)
        changed = view.changed
        if changed:
            set_style_flag(self._bar_widget(), "fbChanged", "true")
        elif self._bar is not None:
            set_style_flag(self._bar, "fbChanged", "false")
        if isinstance(view, LockedRow):
            self._show_locked(view, match_color)
            self._sync_reset()
            return
        if self._needs_new_editor(previous, view):
            self._invalid = False
            self._build_editor(view)
        self._paint_value_match(view, match_color)
        if not self._invalid and self._editor is not None:
            self._editor.show(view.value)
        self._sync_reset()

    def set_label_width(self, width: int) -> None:
        self._label_col.setFixedWidth(width)

    def note_focus(self, focus: object) -> None:
        del focus
        self._sync_reset()

    def retint(self, show_qt: bool) -> None:
        view = self._view
        if view is None:
            return
        self._qt_names = show_qt
        self._paint_qt(view, self._match_color)

    def enterEvent(self, event: QEvent) -> None:  # noqa: N802
        self._hovered = True
        self._sync_reset()
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:  # noqa: N802
        self._hovered = False
        self._sync_reset()
        super().leaveEvent(event)

    def commit(self, value: Value) -> None:
        view = self._view
        if not isinstance(view, OpenRow):
            return
        result = self._services.execute(view.write.edit(value, self._services.token(view.key)))
        if isinstance(result, Dropped):
            return
        if isinstance(result, Rejected):
            self._invalid = True
            self._set_caption(rejection_text(result), error=True)
            return
        self._invalid = False
        skipped = result.result if isinstance(result, CommandOutcome) else None
        if isinstance(skipped, tuple) and skipped:
            self._set_caption(
                "Not applied to %d widgets that lack this property." % len(skipped),
                error=False,
            )
            return
        self._set_caption("", error=False)

    def invalid(self, message: str) -> None:
        self._invalid = True
        self._set_caption(message, error=True)

    def enum_value(self, enum: EnumSpec, names: Sequence[str]) -> Value:
        style = self._services.session.document.enum_style()
        spelled = [_spell(enum, name, style) for name in names]
        if enum.is_flag:
            return SetValue("|".join(spelled))
        if len(spelled) == 1:
            return EnumValue(spelled[0])
        return SetValue("|".join(spelled))

    def revert(self) -> None:
        self._invalid = False
        self._set_caption("", error=False)
        view = self._view
        if isinstance(view, OpenRow) and self._editor is not None:
            self._editor.show(view.value)

    def show_value(self, value: RowValue) -> None:
        if self._editor is not None and not self._invalid:
            self._editor.show(value)

    def _reset_clicked(self) -> None:
        view = self._view
        if not isinstance(view, OpenRow):
            return
        self._invalid = False
        self._services.execute(view.write.reset())

    def _needs_new_editor(self, previous: Optional[Row], view: OpenRow) -> bool:
        if self._editor is None or not isinstance(previous, OpenRow):
            return True
        return previous.editor != view.editor or previous.spec != view.spec

    def _build_editor(self, view: OpenRow) -> None:
        self._clear_slot()
        factory = self._services.catalog.editor(view.editor)
        if factory is None:
            self._fallback = QLabel(self._slot)
            self._slot_layout.addWidget(self._fallback)
            self._editor = None
            return
        self._editor = factory(view.spec, self, self._slot)
        _shrink(self._editor.widget)
        _name_editors(self._editor.widget, view.label)
        self._slot_layout.addWidget(self._editor.widget)
        self._editor.widget.show()

    def _show_locked(self, view: LockedRow, match_color: str) -> None:
        self._clear_slot()
        self._editor = None
        text = value_text(view.value) or NOT_SET_TEXT
        label = QLabel(self._slot)
        _shrink(label)
        label.setObjectName(_value_name(view.value))
        if view.match is not None and view.match.where == "value":
            label.setTextFormat(Qt.RichText)
            label.setText(_marked(text, view.match, "value", match_color))
        else:
            label.setText(text)
        self._fallback = label
        self._slot_layout.addWidget(label)
        label.show()
        self._set_caption(view.reason, error=False)

    def _paint_label(self, view: Row, match_color: str) -> None:
        # The weight is a style sheet rule on ``fbChanged``. A setFont weight
        # loses to the shell's chrome font-weight rule.
        set_style_flag(self._label, "fbChanged", "true" if view.changed else "false")
        if view.match is not None and view.match.where == "label":
            self._label.setTextFormat(Qt.RichText)
            self._label.setText(_marked(view.label, view.match, "label", match_color))
            return
        self._label.setTextFormat(Qt.PlainText)
        self._label.setText(view.label)

    def _paint_qt(self, view: Row, match_color: str) -> None:
        match = view.match
        matched = match is not None and match.where == "qt_name"
        if not view.qt_name or not (self._qt_names or matched):
            if self._qt is not None:
                self._qt.hide()
            return
        label = self._qt_label()
        if matched:
            label.setTextFormat(Qt.RichText)
            label.setText(_marked(view.qt_name, match, "qt_name", match_color))
        else:
            label.setTextFormat(Qt.PlainText)
            label.setText(view.qt_name)
        label.show()

    def _sync_reset(self) -> None:
        view = self._view
        changed = isinstance(view, OpenRow) and view.changed
        if not changed:
            if self._reset is not None:
                self._reset.hide()
            return
        focus = QApplication.focusWidget()
        inside = self._hovered or (
            focus is not None and (focus is self or self.isAncestorOf(focus))
        )
        self._reset_button().setVisible(inside)

    def _paint_value_match(self, view: OpenRow, match_color: str) -> None:
        widget = None if self._editor is None else self._editor.widget
        if widget is None:
            return
        match = view.match
        sheet = ""
        if match is not None and match.where == "value" and match_color:
            sheet = "background-color: %s;" % match_color
        # setStyleSheet repolishes the editor even when the text is the same,
        # which costs most of a select when All properties is open.
        if widget is not self._painted_widget:
            self._painted_widget = widget
            self._painted_sheet = widget.styleSheet()
        if sheet == self._painted_sheet:
            return
        widget.setStyleSheet(sheet)
        self._painted_sheet = sheet

    def _clear_slot(self) -> None:
        editor = self._editor
        if editor is not None:
            editor.widget.hide()
            self._slot_layout.removeWidget(editor.widget)
            editor.widget.deleteLater()
        if self._fallback is not None:
            self._fallback.hide()
            self._slot_layout.removeWidget(self._fallback)
            self._fallback.deleteLater()
            self._fallback = None
        self._editor = None

    def _set_caption(self, text: str, *, error: bool) -> None:
        if not text:
            if self._caption is not None:
                self._caption.hide()
                self._caption.clear()
            return
        caption = self._caption_label()
        caption.setObjectName(
            "formBuilder.rowError" if error else "formBuilder.rowNote"
        )
        caption.setText(text)
        caption.show()

class _GroupHost:

    def __init__(self, services: Services, owners: Tuple[NodeId, ...]) -> None:
        self._services = services
        self._owners = owners
        self._qt_names = False

    def set_frame(self, owners: Tuple[NodeId, ...], qt_names: bool) -> None:
        self._owners = owners
        self._qt_names = qt_names

    @property
    def document(self) -> UiDocument:
        return self._services.session.document

    @property
    def owners(self) -> Tuple[NodeId, ...]:
        return self._owners

    @property
    def qt_names(self) -> bool:
        return self._qt_names

    def live(self, owner: NodeId) -> Optional[QWidget]:
        return self._services.live(owner)

    def run(self, label: str, commands: Sequence[Command]) -> Optional[str]:
        result = self._services.execute_all(label, commands)
        if isinstance(result, Rejected):
            return rejection_text(result)
        return None

    def editor_for(self, row: Row, parent: QWidget) -> Editor:
        widget = _Row(self._services, parent)
        widget.paint(row, "")
        return _BoundEditor(widget)

class _BoundEditor:
    def __init__(self, row: _Row) -> None:
        self._row = row

    @property
    def widget(self) -> QWidget:
        return self._row

    def show(self, value: RowValue) -> None:
        self._row.show_value(value)

def _spell(enum: EnumSpec, name: str, style: str) -> str:
    if not name or "::" in name or not enum.scope:
        return name
    if style == "qualified" and enum.type_name and enum.type_name != enum.scope:
        return "%s::%s::%s" % (enum.scope, enum.type_name, name)
    return "%s::%s" % (enum.scope, name)

def _marked(text: str, match: Optional[Match], where: str, color: str) -> str:
    if match is None or match.where != where or not color:
        return _escape(text)
    start = max(0, min(match.start, len(text)))
    end = max(start, min(match.end, len(text)))
    return '%s<span style="background-color:%s;">%s</span>%s' % (
        _escape(text[:start]),
        color,
        _escape(text[start:end]),
        _escape(text[end:]),
    )

def _value_name(value: object) -> str:
    if isinstance(value, Mixed):
        return "formBuilder.rowMixed"
    if isinstance(value, Unset):
        return "formBuilder.rowDefault"
    return "formBuilder.rowValue"

def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )

def _name_editors(root: QWidget, label: str) -> None:
    """Name the editor and the line edit Qt uses as its focus proxy."""
    root.setAccessibleName(label)
    _name_line(root, label)
    for child in root.findChildren(QWidget):
        meta = child.metaObject()
        kind = str(meta.className()) if meta is not None else ""
        if kind not in (
            "QSpinBox",
            "QDoubleSpinBox",
            "QLineEdit",
            "QComboBox",
            "QFontComboBox",
            "QPlainTextEdit",
            "QKeySequenceEdit",
        ):
            continue
        if not child.accessibleName():
            child.setAccessibleName(label)
        _name_line(child, child.accessibleName() or label)


def _name_line(widget: QWidget, label: str) -> None:
    line = getattr(widget, "lineEdit", None)
    if not callable(line):
        return
    editor = line()
    if isinstance(editor, QWidget) and not editor.accessibleName():
        editor.setAccessibleName(label)


def _shrink(widget: QWidget) -> None:
    policy = getattr(QSizePolicy, "Policy", QSizePolicy)
    widget.setSizePolicy(getattr(policy, "Ignored"), getattr(policy, "Preferred"))
    widget.setMinimumWidth(0)

def _no_frame() -> QFrame.Shape:
    return getattr(getattr(QFrame, "Shape", QFrame), "NoFrame")

def _scroll_off() -> Qt.ScrollBarPolicy:
    return getattr(getattr(Qt, "ScrollBarPolicy", Qt), "ScrollBarAlwaysOff")

def _popup_mode() -> QToolButton.ToolButtonPopupMode:
    return getattr(getattr(QToolButton, "ToolButtonPopupMode", QToolButton), "InstantPopup")

def _beside() -> Qt.ToolButtonStyle:
    return getattr(getattr(Qt, "ToolButtonStyle", Qt), "ToolButtonTextBesideIcon")

def _arrow(expanded: bool) -> Qt.ArrowType:
    name = "DownArrow" if expanded else "RightArrow"
    arrows = getattr(Qt, "ArrowType", Qt)
    return getattr(arrows, name, getattr(Qt, name))

def _weight(name: str) -> QFont.Weight:
    return getattr(getattr(QFont, "Weight", QFont), name)

def _overline_font() -> QFont:
    font = QFont()
    font.setPixelSize(10)
    font.setWeight(_weight("DemiBold"))
    font.setLetterSpacing(QFont.AbsoluteSpacing, 0.5)
    return font

def _caption(parent: QWidget, name: str, text: str) -> QLabel:
    label = QLabel(text, parent)
    label.setObjectName("formBuilder.formCaption.%s" % name)
    label.setFont(_overline_font())
    return label

def _tip(view: Row) -> str:
    if view.qt_name and view.help:
        return "%s \u2014 %s" % (view.qt_name, view.help)
    return view.qt_name or view.help
