"""The inspector widget a host constructs."""

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
    project_header,
    tab_order_stale,
)
from app.features.form_builder.qtside.realize import Realizer
from app.features.form_builder.qtside.theme.chrome import FormChrome
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
    """Declaration order is tab order. DATA exists only when the pane is built with data_tab."""

    PROPERTIES = "properties"
    BEHAVIOR = "behavior"
    DATA = "data"


class InspectorPane(QWidget):
    """Shows session.selection. Subscribes itself. Writes only through Services."""

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
        self._services = Services(session, default_catalog())
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
        self.header = Header(self._services, self)
        self.tabs = QTabWidget(self)
        self.tabs.setObjectName("formBuilder.inspectorTabs")
        self.properties = PropertiesPage(self._services, self._schedule, self.tabs)
        self.behavior = BehaviorPage(self._services, realizer, self.tabs)
        self._tab_index: Dict[TabId, int] = {}
        for tab in TabId:
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
        app = QApplication.instance()
        if isinstance(app, QApplication):
            app.installEventFilter(self)
            self._filtered_app = app
        self._log_sub = session.log.subscribe(self._on_log, priority=PRIORITY_VIEWS)
        self._selection_unsub = session.selection.subscribe(self._on_selection)
        self._diag_unsub = session.diagnostics.subscribe(self._on_diagnostics)
        self._paint_header()
        self._schedule()

    def set_short(self, short: bool) -> None:
        """The short drawer. Name and class share one line."""
        self._short = short
        self._paint_header()

    def apply_chrome(self, chrome: FormChrome) -> None:
        """One stylesheet for the pane, built from ``chrome``."""
        self.setStyleSheet(_stylesheet(chrome))
        self.properties.apply_colors(chrome.panel, chrome.text, chrome.faint)
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
        """Show ``tab`` and focus its first field. Properties focuses search."""
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
        """Focus the name field with its text selected. No-op when several nodes are selected."""
        self.header.begin_rename()

    def flush(self) -> None:
        """Run a pending body repaint now. Returns at once when nothing is pending."""
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
        session = self._services.session
        ids = session.selection.state.ids or (session.document.root.id,)
        live = live_classes(self._realizer, session.document, ids)
        pages = project(
            session,
            self._services.catalog,
            search=self.properties.search,
            live=live,
            tab_order=self._memo.get,
        )
        with self._services.painting():
            self.properties.paint(pages.body)
            self.behavior.paint(pages.behavior)
        title = "Behavior"
        behavior = pages.behavior
        if isinstance(behavior, OneBehavior) and behavior.connections:
            title = "Behavior (%d)" % len(behavior.connections)
        index = self._tab_index.get(TabId.BEHAVIOR)
        if index is not None:
            self.tabs.setTabText(index, title)

    def dispose(self) -> None:
        """Close the three subscriptions and stop the timer. Idempotent."""
        self._timer.stop()
        app = self._filtered_app
        if app is not None:
            app.removeEventFilter(self)
            self._filtered_app = None
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
        if not self._owns(watched) or not isinstance(event, QKeyEvent):
            return False
        if event.type() == QEvent.ShortcutOverride and self._override(event):
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
        self._paint_header()
        self._schedule()

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
        if key == _code(Qt.Key_Escape) and mods == 0 and self._esc() is not EscAction.LEAVE:
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
            action = self._esc()
            if action is EscAction.CLEAR_SEARCH:
                self.properties.clear_search()
                return
            if action is EscAction.REVERT_FIELD:
                if self.header.has_invalid_name():
                    self.header.revert_name()
                else:
                    self.properties.revert_focused_row()
            return
        self.properties.focus_search()

    def _clear_dispatched(self) -> None:
        self._dispatched = None

    def _esc(self) -> EscAction:
        invalid = self.header.has_invalid_name() or self.properties.focused_row_invalid()
        return esc_action(self.properties.search, invalid)


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
        "QLabel#formBuilder\\.inspectorClass, QLabel#formBuilder\\.rowQtName,"
        " QLabel#formBuilder\\.inspectorGlyph { color: %s; }"
        "QLabel#formBuilder\\.rowDefault, QLabel#formBuilder\\.rowMixed { color: %s; }"
        "QLabel#formBuilder\\.rowError, QLabel#formBuilder\\.inspectorNameError { color: %s; }"
        "QFrame#formBuilder\\.rowChanged { background: %s; border: none; }"
        % (
            chrome.panel,
            chrome.text,
            chrome.input,
            chrome.text,
            chrome.border,
            width,
            chrome.accent,
            chrome.text,
            chrome.muted,
            chrome.faint,
            chrome.error,
            chrome.accent,
        )
    )


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
