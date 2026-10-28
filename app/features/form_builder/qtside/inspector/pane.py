
from __future__ import annotations

from enum import Enum
from typing import Callable, Dict, Optional, Tuple

from app.features.form_builder.engine.diagnostics import FormDiagnostic
from app.features.form_builder.engine.events import PRIORITY_VIEWS, ChangeSet
from app.features.form_builder.engine.query.selection import SelectionChange
from app.features.form_builder.engine.query.tree import effective_tab_order
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.qtside.inspector._behavior import BehaviorPage
from app.features.form_builder.qtside.inspector._header import Header
from app.features.form_builder.qtside.inspector._live import live_classes
from app.features.form_builder.qtside.inspector._properties import PropertiesPage
from app.features.form_builder.qtside.inspector._services import Services
from app.features.form_builder.qtside.inspector.editors import default_catalog
from app.features.form_builder.qtside.inspector.model import (
    EscAction,
    OneBehavior,
    esc_action,
    project,
    inspected_ids,
    project_header,
    tab_order_stale,
)
from app.features.form_builder.qtside.realize import Realizer
from app.features.form_builder.qtside.theme.chrome import LAYOUT_CONFIRM_NAME, FormChrome, popover_style
from app.qt.QtCore import QEvent, QObject, QTimer, Qt
from app.qt.QtGui import QKeyEvent, QKeySequence, QShowEvent
from app.qt.QtWidgets import (
    QApplication,
    QLabel,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from app.qt.qt_compat import enum_value

class TabId(str, Enum):

    PROPERTIES = "properties"
    BEHAVIOR = "behavior"
    DATA = "data"


def _cover_tabs(order: Tuple[TabId, ...]) -> Tuple[TabId, ...]:
    if set(order) != set(TabId) or len(order) != len(set(order)):
        raise RuntimeError("TAB_ORDER must list each TabId once")
    return order


TAB_ORDER: Tuple[TabId, ...] = _cover_tabs((TabId.PROPERTIES, TabId.BEHAVIOR, TabId.DATA))

class InspectorPane(QWidget):

    header: Header
    tabs: QTabWidget

    def __init__(
        self,
        session: FormSession,
        realizer: Realizer,
        *,
        data_tab: bool,
        on_leave: Callable[[], None],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.inspector")
        self._services = Services(session, default_catalog(), realizer)
        self._realizer = realizer
        self._on_leave = on_leave
        self._short = False
        self._pending = False
        self._stale = False
        self._dispatched: Optional[Tuple[int, int]] = None
        self._memo = _TabOrderMemo(session)
        self._log_sub: object = None
        self._selection_unsub: Optional[Callable[[], None]] = None
        self._diag_unsub: Optional[Callable[[], None]] = None
        self._filtered_app: Optional[QApplication] = None
        self._problem_count = 0
        self._on_show_problems: Optional[Callable[[], None]] = None
        self._link_color = ""
        self._inspected_ids: frozenset = frozenset()
        self._reset_scroll = False
        self.header = Header(self._services, self)
        self.tabs = QTabWidget(self)
        self.tabs.setObjectName("formBuilder.inspectorTabs")
        self.tabs.setAccessibleName("Inspector")
        self.tabs.tabBar().setAccessibleName("Inspector")
        self.properties = PropertiesPage(self._services, self._schedule, self.tabs)
        self.behavior = BehaviorPage(self._services, realizer, self.tabs)
        self.behavior.set_refresh(self._refresh_now)
        self._tab_index: Dict[TabId, int] = {}
        for tab in TAB_ORDER:
            if tab is TabId.DATA and not data_tab:
                continue
            if tab is TabId.PROPERTIES:
                page: QWidget = self.properties
            elif tab is TabId.BEHAVIOR:
                page = self.behavior
            else:
                page = _data_page(self.tabs)
            self.tabs.addTab(page, tab.value.capitalize())
            self._tab_index[tab] = self.tabs.count() - 1
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.header)
        layout.addWidget(self.tabs, 1)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.flush)
        self._app: Optional[QApplication] = None
        app = QApplication.instance()
        if isinstance(app, QApplication):
            self._app = app
            app.focusChanged.connect(self._on_app_focus)
        self._log_sub = session.log.subscribe(self._on_log, priority=PRIORITY_VIEWS)
        self._selection_unsub = session.selection.subscribe(self._on_selection)
        self._diag_unsub = session.diagnostics.subscribe(self._on_diagnostics)
        self._paint_header()
        self._schedule()

    def set_short(self, short: bool) -> None:
        self._short = short
        self._paint_header()

    def set_problem_summary(self, count: int, on_show: Callable[[], None]) -> None:
        """Problems for this form, from the shell's rows (UX-PROB-003)."""
        self._problem_count = count
        self._on_show_problems = on_show
        self.properties.set_problem_link(count, on_show, self._link_color)

    def set_link_color(self, color: str) -> None:
        """The palette link colour fails contrast on dark panels; a token is passed in."""
        self._link_color = color
        self.header.set_link_color(color)
        self.properties.set_link_color(color)
        self.properties.set_problem_link(self._problem_count, self._on_show_problems, color)

    def set_compact(self, compact: bool) -> None:
        self.properties.set_compact(compact)

    def bind_settings(self, store: object) -> None:
        self.properties.bind_qt_names(store)

    def set_group_expanded(self, group: object, expanded: bool) -> None:
        self.properties.set_group_expanded(group, expanded)

    def apply_chrome(self, chrome: FormChrome) -> None:
        self._services.set_chrome(chrome)
        self.setStyleSheet(_stylesheet(chrome))
        self.properties.apply_colors(
            chrome.panel, chrome.text, chrome.faint, chrome.row_hover, caption=chrome.muted
        )
        self.properties.set_match_color(chrome.search_match_bg)
        self.behavior.apply_colors(chrome.panel, chrome.text)
        data = self.findChild(QWidget, "formBuilder.dataBody")
        if data is not None:
            data.setStyleSheet(
                "QWidget#formBuilder\\.dataBody { background: %s; color: %s; }"
                "QLabel { color: %s; }"
                % (chrome.panel, chrome.faint, chrome.faint)
            )
        self._schedule()

    def focus_tab(self, tab: TabId) -> None:
        index = self._tab_index.get(tab)
        if index is None:
            return
        self.tabs.setCurrentIndex(index)
        if tab is TabId.PROPERTIES:
            self.properties.focus_search()
            return
        page = self.tabs.widget(index)
        if page is not None:
            page.setFocus()

    def begin_rename(self) -> None:
        self.header.begin_rename()

    def flush(self) -> None:
        if not self._pending and not self._stale:
            return
        if not self.isVisible():
            self._stale = True
            self._pending = False
            self._timer.stop()
            return
        self._pending = False
        self._stale = False
        self._timer.stop()
        reset_scroll = self._reset_scroll
        self._reset_scroll = False
        session = self._services.session
        document = session.document
        ids = inspected_ids(document, session.selection.state.ids) or (document.root.id,)
        include_all = self.properties.builds_all_properties()
        # Layout rows read their choices and defaults from the realized layout.
        layouts = tuple(layout.id for layout in map(document.layout_of, ids) if layout is not None)
        live = live_classes(
            self._realizer,
            document,
            ids + layouts,
            with_values=True,
        )
        root = self._realizer.root_widget
        live_size = None if root is None else (root.width(), root.height())
        pages = project(
            session,
            self._services.catalog,
            search=self.properties.search,
            live=live,
            tab_order=self._memo.get,
            include_all=include_all,
            live_size=live_size,
        )
        with self._services.painting():
            self.properties.paint(pages.body)
            self.behavior.paint(pages.behavior)
        if reset_scroll:
            self.properties.reveal_after_selection()
        title = "Behavior"
        behavior = pages.behavior
        if isinstance(behavior, OneBehavior) and behavior.connections:
            title = "Behavior (%d)" % len(behavior.connections)
        index = self._tab_index.get(TabId.BEHAVIOR)
        # setTabText relays out the styled tab bar even for the same text.
        if index is not None and self.tabs.tabText(index) != title:
            self.tabs.setTabText(index, title)

    def dispose(self) -> None:
        self._timer.stop()
        app = self._app
        if app is not None:
            try:
                app.focusChanged.disconnect(self._on_app_focus)
            except (RuntimeError, TypeError):
                pass
            self._app = None
        self._remove_filter()
        subscription = self._log_sub
        close = getattr(subscription, "close", None)
        if callable(close):
            close()
        self._log_sub = None
        if self._selection_unsub is not None:
            self._selection_unsub()
            self._selection_unsub = None
        if self._diag_unsub is not None:
            self._diag_unsub()
            self._diag_unsub = None

    def event(self, event: QEvent) -> bool:
        if (
            event.type() == QEvent.ShortcutOverride
            and isinstance(event, QKeyEvent)
            and self._override(event)
        ):
            event.accept()
            self._dispatch_claimed(event)
            return True
        return super().event(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if self._on_key(event):
            event.accept()
            return
        super().keyPressEvent(event)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if not isinstance(event, QKeyEvent):
            return False
        kind = event.type()
        if kind != QEvent.ShortcutOverride and kind != QEvent.KeyPress:
            return False
        if not self._owns(watched):
            return False
        if kind == QEvent.ShortcutOverride and _key(event) in (_code(Qt.Key_Tab), _code(Qt.Key_Backtab)):
            # A deferred flush would rebuild the tab chain after this key, so
            # Tab from a just-edited row leaves the form. Paint links the rows
            # before Qt moves focus. Rebuilding a chain that is already current
            # scrambles Shift+Tab.
            if self._pending:
                self.flush()
            self.properties.ensure_tab_chain()
        if kind == QEvent.ShortcutOverride and self._override(event):
            event.accept()
            self._dispatch_claimed(event)
            return True
        if event.type() == QEvent.KeyPress and self._on_key(event):
            return True
        return False

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        if self._stale or self._pending:
            self._pending = False
            self._stale = False
            self._schedule()

    def _on_log(self, changeset: ChangeSet) -> None:
        self._memo.invalidate(changeset)
        self._paint_header()
        self._schedule()

    def _on_selection(self, _change: SelectionChange) -> None:
        document = self._services.session.document
        ids = frozenset(inspected_ids(document, self._services.session.selection.state.ids))
        if ids != self._inspected_ids:
            self._inspected_ids = ids
            self._reset_scroll = True
        self._paint_header()
        self._schedule()

    def _refresh_now(self) -> None:
        self._pending = True
        self.flush()

    def _on_diagnostics(self, _found: Tuple[FormDiagnostic, ...]) -> None:
        self._schedule()

    def _paint_header(self) -> None:
        self.header.paint(project_header(self._services.session), self._short)

    def _schedule(self) -> None:
        if self._pending:
            return
        self._pending = True
        if not self.isVisible():
            self._stale = True
            return
        self._timer.start(0)

    def _on_app_focus(self, _old: object, new: object) -> None:
        self._sync_filter(new)
        self.properties.note_focus(new)
        self.behavior.note_focus(new)

    def _sync_filter(self, focus: object) -> None:
        app = self._app
        if app is None:
            return
        if _inside(self, focus):
            if self._filtered_app is None:
                app.installEventFilter(self)
                self._filtered_app = app
            return
        self._remove_filter()

    def _remove_filter(self) -> None:
        app = self._filtered_app
        if app is None:
            return
        app.removeEventFilter(self)
        self._filtered_app = None

    def _owns(self, watched: object) -> bool:
        if watched is self:
            return True
        if isinstance(watched, QWidget) and self.isAncestorOf(watched):
            return True
        focus = QApplication.focusWidget()
        if focus is None or not (focus is self or self.isAncestorOf(focus)):
            return False
        return isinstance(watched, QWidget) and watched is focus.window()

    def _override(self, event: QKeyEvent) -> bool:
        key = _key(event)
        mods = _mods(event)
        if key == _code(Qt.Key_F2) and mods == 0:
            return True
        if _is_find(event):
            return True
        if key == _code(Qt.Key_Escape) and mods == 0 and (
            self.behavior.has_draft() or self._esc() is not EscAction.LEAVE
        ):
            return True
        return False

    def _on_key(self, event: QKeyEvent) -> bool:
        token = (_key(event), _mods(event))
        if self._dispatched == token:
            self._dispatched = None
            return True
        if self._override(event):
            self._dispatch_claimed(event)
            return True
        if _key(event) == _code(Qt.Key_Escape) and _mods(event) == 0 and self._esc() is EscAction.LEAVE:
            self._on_leave()
            return True
        return False

    def _dispatch_claimed(self, event: QKeyEvent) -> None:
        token = (_key(event), _mods(event))
        if self._dispatched == token:
            return
        self._dispatched = token
        QTimer.singleShot(0, self._clear_dispatched)
        key = token[0]
        if key == _code(Qt.Key_F2):
            self.header.begin_rename()
            return
        if key == _code(Qt.Key_Escape):
            if self.behavior.discard_draft():
                return
            action = self._esc()
            if action is EscAction.CLEAR_SEARCH:
                self.properties.clear_search()
                return
            if action is EscAction.REVERT_FIELD:
                if self.header.has_invalid_name() or self.header.has_pending_name():
                    self.header.revert_name()
                else:
                    self.properties.revert_focused_row()
            return
        self.properties.focus_search()

    def _clear_dispatched(self) -> None:
        self._dispatched = None

    def _esc(self) -> EscAction:
        invalid = self.header.has_invalid_name() or self.properties.focused_row_invalid()
        # Typed but not committed: Esc cancels it rather than letting the
        # focus-out that follows commit it (UX-TEXT-003).
        dirty = self.header.has_pending_name() or self.properties.focused_row_dirty()
        return esc_action(self.properties.search, invalid, dirty)

class _TabOrderMemo:
    def __init__(self, session: FormSession) -> None:
        self._session = session
        self._names: Optional[Tuple[str, ...]] = None

    def invalidate(self, changeset: ChangeSet) -> None:
        if tab_order_stale(changeset):
            self._names = None

    def get(self) -> Tuple[str, ...]:
        if self._names is None:
            self._names = tuple(effective_tab_order(self._session.document))
        return self._names

def _data_page(parent: QWidget) -> QWidget:
    page = QWidget(parent)
    page.setObjectName("formBuilder.dataBody")
    layout = QVBoxLayout(page)
    button = QPushButton("Connect this form to a table", page)
    button.setEnabled(False)
    caption = QLabel("Not built yet (M8)", page)
    layout.addWidget(button)
    layout.addWidget(caption)
    layout.addStretch(1)
    return page

def _stylesheet(chrome: FormChrome) -> str:
    width = chrome.focus_width if chrome.focus_width > 0 else 1
    return (
        "QWidget#formBuilder\\.inspector { background: %s; color: %s; }"
        "QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QKeySequenceEdit,"
        " QListWidget, QFontComboBox {"
        " background: %s; color: %s; border: 1px solid %s; }"
        "QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus,"
        " QPlainTextEdit:focus, QKeySequenceEdit:focus, QListWidget:focus, QFontComboBox:focus {"
        " border: %dpx solid %s; }"
        "QLabel { color: %s; background: transparent; }"
        "QCheckBox { color: %s; background: transparent; }"
        "QLabel#formBuilder\\.inspectorClass, QLabel#formBuilder\\.rowQtName,"
        " QWidget#formBuilder\\.inspectorGlyph { color: %s; }"
        "QSpinBox[fbState=\"unset\"], QDoubleSpinBox[fbState=\"unset\"], QComboBox[fbState=\"unset\"],"
        " QLineEdit[fbState=\"unset\"], QFontComboBox[fbState=\"unset\"], QCheckBox[fbState=\"unset\"]"
        " { color: %s; }"
        "QSpinBox[fbState=\"mixed\"], QDoubleSpinBox[fbState=\"mixed\"], QComboBox[fbState=\"mixed\"],"
        " QLineEdit[fbState=\"mixed\"], QFontComboBox[fbState=\"mixed\"], QCheckBox[fbState=\"mixed\"],"
        " QListWidget[fbState=\"mixed\"] { color: %s; font-style: italic; }"
        "QLabel#formBuilder\\.rowDefault, QLabel#formBuilder\\.rowMixed { color: %s; }"
        "QLabel#formBuilder\\.rowError, QLabel#formBuilder\\.inspectorNameError { color: %s; }"
        "QFrame#formBuilder\\.rowChanged { background: transparent; border: none; }"
        "QFrame#formBuilder\\.rowChanged[fbChanged=\"true\"] { background: %s; }"
        # Strong weight. These outrank the shell's chrome font-weight rule,
        # which a setFont weight does not (UX-INSP-001, UX-INSP-006).
        "QLabel[fbChanged=\"true\"], QLineEdit#formBuilder\\.inspectorName { font-weight: 600; }"
        # Segments are drawn by the sheet in every state: a native button is
        # bright on a dark panel, and the shell's checked text is unreadable.
        "QToolButton[fbSegment=\"true\"] { background: %s; color: %s; border: 1px solid %s; }"
        "QToolButton[fbSegment=\"true\"][fbOutline=\"true\"] {"
        " background: %s; color: %s; border: 1px dashed %s; }"
        "QToolButton[fbSegment=\"true\"]:disabled { background: %s; color: %s; border: none; }"
        "QToolButton[fbSegment=\"true\"]:checked { background: %s; color: %s; border: 1px solid %s; }"
        "QLabel#formBuilder\\.sizeWhy { color: %s; background: %s; }"
        "%s"
        % (
            chrome.panel,
            chrome.text,
            chrome.input,
            chrome.text,
            chrome.border,
            width,
            chrome.accent,
            chrome.text,
            chrome.text,
            chrome.muted,
            chrome.faint,
            chrome.faint,
            chrome.faint,
            chrome.error,
            chrome.accent,
            chrome.input,
            chrome.text,
            chrome.border,
            chrome.input,
            chrome.text,
            chrome.accent,
            chrome.panel,
            chrome.faint,
            chrome.selected,
            chrome.text,
            chrome.accent,
            chrome.muted,
            chrome.row_hover,
            popover_style(LAYOUT_CONFIRM_NAME, chrome),
        )
    )

def _inside(pane: QWidget, focus: object) -> bool:
    return isinstance(focus, QWidget) and (focus is pane or pane.isAncestorOf(focus))


def _key(event: QKeyEvent) -> int:
    return int(enum_value(event.key()))

def _mods(event: QKeyEvent) -> int:
    return int(enum_value(event.modifiers()))

def _code(value: object) -> int:
    return int(enum_value(value))

def _is_find(event: QKeyEvent) -> bool:
    sequence = QKeySequence(_mods(event) | _key(event))
    found = QKeySequence(QKeySequence.Find)
    return found.matches(sequence) == QKeySequence.ExactMatch
