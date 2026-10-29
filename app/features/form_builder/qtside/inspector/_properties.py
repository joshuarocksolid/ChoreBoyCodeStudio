
from __future__ import annotations

import dataclasses
import importlib
import logging
import pkgutil
from collections import OrderedDict
from types import ModuleType
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple, Union

from app.features.form_builder.engine.commands.base import Command
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.values import EnumValue, SetValue, Value
from app.features.form_builder.qtside.inspector._services import Dropped, Rejected, Services, rejection_text
from app.features.form_builder.qtside.inspector.editors._popover import SummaryButton
from app.features.form_builder.qtside.inspector.editors._editor_kit import warning_color
from app.features.form_builder.qtside.theme.chrome import FormChrome, control_qss
from app.features.form_builder.qtside.inspector.api import (
    NOT_SET_TEXT,
    Editor,
    EditSession,
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
    Written,
    set_style_flag,
)
from app.features.form_builder.qtside.inspector.model import (
    BodyView,
    FormBody,
    GroupView,
    form_shortcuts,
    value_text,
)
from app.qt.QtCore import QEvent, QObject, QPoint, Qt, QTimer
from app.qt.qt_compat import delete_now, wrapper_is_valid
from app.qt.QtGui import QFont
from app.qt.QtWidgets import (
    QAbstractSlider,
    QAbstractSpinBox,
    QApplication,
    QBoxLayout,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QMenu,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)

_DRAG = "Drag the page's right or bottom edge to try other sizes."
_LABEL_WIDE = 104
_LABEL_COMPACT = 96

@dataclasses.dataclass(frozen=True)
class FormGroupSpec:
    """A group shown in the inspector while the form itself is selected (M5.0s).

    ``factory(host, parent)`` returns a ``GroupBody`` (the type in ``api``),
    once per inspector. ``host.document`` is the form, ``host.owners`` is
    ``(root id,)`` and ``host.run(label, commands)`` is one undo step. The
    body's ``show(rows)`` is called with an empty tuple after every change to
    the form. ``applies(document)`` hides the group when it is False.
    """

    key: str
    title: str
    factory: GroupBodyFactory
    order: int = 100
    applies: Optional[Callable[[UiDocument], bool]] = None
    module: str = ""


class FormGroupRegistry:
    """Form groups in ``(order, key)`` order. Groups follow the built-in Window ... Files sections."""

    def __init__(self) -> None:
        self._specs: List[FormGroupSpec] = []

    def add(
        self,
        key: str,
        title: str,
        factory: GroupBodyFactory,
        *,
        order: int = 100,
        applies: Optional[Callable[[UiDocument], bool]] = None,
        module: str = "",
    ) -> None:
        if not key or not title:
            raise ValueError("a form group needs a key and a title")
        if any(spec.key == key for spec in self._specs):
            raise ValueError("form group %s is already registered" % key)
        self._specs.append(FormGroupSpec(key, title, factory, order, applies, module))

    def scope(self, module: str) -> "_FormGroupScope":
        return _FormGroupScope(self, module)

    def groups(self) -> Tuple[FormGroupSpec, ...]:
        return tuple(sorted(self._specs, key=lambda spec: (spec.order, spec.key)))


class _FormGroupScope:
    def __init__(self, registry: FormGroupRegistry, module: str) -> None:
        self._registry = registry
        self._module = module

    def add(
        self,
        key: str,
        title: str,
        factory: GroupBodyFactory,
        *,
        order: int = 100,
        applies: Optional[Callable[[UiDocument], bool]] = None,
    ) -> None:
        self._registry.add(key, title, factory, order=order, applies=applies, module=self._module)


def load_form_groups(*packages: ModuleType) -> FormGroupRegistry:
    """Call ``register_form_groups(registry)`` in each public module of ``packages``, in sorted name order.

    A module opts in by defining that function next to its ``register``; it
    needs no import from the inspector. A module that fails is logged and skipped.
    """
    registry = FormGroupRegistry()
    for package in packages:
        for info in sorted(pkgutil.iter_modules(package.__path__), key=lambda found: found.name):
            if info.name.startswith("_"):
                continue
            try:
                module = importlib.import_module("%s.%s" % (package.__name__, info.name))
                register = getattr(module, "register_form_groups", None)
                if callable(register):
                    register(registry.scope(module.__name__))
            except Exception:
                logger.exception("form group contributor %s failed", info.name)
    return registry


_FORM_GROUPS: Optional[FormGroupRegistry] = None


def default_form_groups() -> FormGroupRegistry:
    """Form groups of the ``editors`` package, loaded once."""
    global _FORM_GROUPS
    if _FORM_GROUPS is None:
        from app.features.form_builder.qtside.inspector import editors

        _FORM_GROUPS = load_form_groups(editors)
    return _FORM_GROUPS


class PropertiesPage(QWidget):

    def __init__(self, services: Services, on_search: Callable[[], None], parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.inspectorBody")
        self._services = services
        self._on_search = on_search
        self._match_color = ""
        self._expanded: Dict[GroupId, bool] = {group: group is not GroupId.ALL for group in GROUP_ORDER}
        self._label_width = _LABEL_WIDE
        self._compact = False
        self._show_qt = False
        self._sort = False
        self._pending_focus = ""
        self._qt_store: object = None
        self._link_color = ""
        self._tab_key: Optional[Tuple[QWidget, ...]] = None
        # Paint only marks the chain stale. Walking every stop costs ~2-3 ms
        # per select with All properties open, so the pane relinks just before
        # a Tab moves focus inside it or focus enters it (ensure_tab_chain).
        self._chain_dirty = False
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
        self._sort_action = menu.addAction("Sort all properties A\u2013Z")
        self._sort_action.setCheckable(True)
        self._sort_action.toggled.connect(self._on_sort)
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
        self._form_groups: List[_FormGroup] = []
        for spec in default_form_groups().groups():
            box = _FormGroup(services, spec, self._content)
            self._form_groups.append(box)
            self._content_layout.addWidget(box)
            box.hide()
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
        self._compact = bool(compact)
        self._apply_label_budget()

    def resizeEvent(self, event: QEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._apply_label_budget()

    def _apply_label_budget(self) -> None:
        narrow = self._scroll.viewport().width() - 16 < _NARROW_ROW
        width = _LABEL_COMPACT if (self._compact or narrow) else _LABEL_WIDE
        if width == self._label_width:
            return
        self._label_width = width
        self._form.set_label_width(width)
        for group in self._groups.values():
            group.set_label_width(width)

    def set_group_expanded(self, group: object, expanded: bool) -> None:
        if not isinstance(group, GroupId):
            return
        changed = self._expanded.get(group) != expanded
        self._expanded[group] = expanded
        widget = self._groups.get(group)
        if widget is None:
            return
        widget.set_checked(expanded)
        if changed:
            # Same path as a click: All properties needs a rebuild to build its
            # rows, and other groups repaint, so the body is not left hidden.
            widget.apply_expanded(expanded)

    def builds_all_properties(self) -> bool:
        return bool(self.search.strip()) or self._expanded.get(GroupId.ALL, False)

    def ensure_tab_chain(self) -> None:
        """Relink the stops if a paint changed them since the last link."""
        if not self._chain_dirty:
            return
        self._chain_dirty = False
        self._chain_tabs()

    def note_focus(self, focus: object) -> None:
        if isinstance(focus, QWidget) and (focus is self or self.isAncestorOf(focus)):
            self.ensure_tab_chain()
        self._form.note_focus(focus)
        for group in self._groups.values():
            group.note_focus(focus)

    def bind_qt_names(self, store: object) -> None:
        self._qt_store = store
        reader = getattr(store, "qt_names", None)
        shown = bool(reader()) if callable(reader) else False
        self._qt_names_action.setChecked(shown)
        sort_reader = getattr(store, "sort_properties", None)
        sorting = bool(sort_reader()) if callable(sort_reader) else False
        self._sort_action.setChecked(sorting)

    def cancel_inline_form(self) -> bool:
        """Close the custom-property form when focus is in it. True when it closed."""
        adder = self._groups[GroupId.ALL]._adder
        cancel = getattr(adder, "cancel_if_focused", None)
        return bool(cancel()) if callable(cancel) else False

    def sorts_properties(self) -> bool:
        return self._sort

    def focus_property(self, name: str) -> None:
        self._pending_focus = name

    def qt_names_visible(self) -> bool:
        return self._show_qt

    def request_rebuild(self) -> None:
        self._on_search()

    def apply_colors(
        self,
        panel: str,
        text: str,
        faint: str,
        hover: str = "",
        caption: str = "",
        error: str = "",
        chrome: Optional[FormChrome] = None,
    ) -> None:
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
            " QLineEdit[fbState=\"unset\"], QFontComboBox[fbState=\"unset\"], QCheckBox[fbState=\"unset\"],"
            " QPushButton#formBuilder\\.summary[fbState=\"unset\"]"
            " { color: %s; }"
            "QSpinBox[fbState=\"mixed\"], QDoubleSpinBox[fbState=\"mixed\"], QComboBox[fbState=\"mixed\"],"
            " QLineEdit[fbState=\"mixed\"], QFontComboBox[fbState=\"mixed\"], QCheckBox[fbState=\"mixed\"],"
            " QListWidget[fbState=\"mixed\"], QPushButton#formBuilder\\.summary[fbState=\"mixed\"]"
            " { color: %s; font-style: italic; }"
            "QLabel#formBuilder\\.sizeWhy { color: %s; background: %s; }"
            "QLabel#formBuilder\\.layout\\.followsWindow { color: %s; background: transparent; }"
            "QToolButton[fbSegment=\"true\"]:disabled { background: %s; color: %s; border: none; }"
            # This sheet's bare QLabel rule is nearer than the pane's, so the
            # refusal colour (UX-PED-008) is repeated here.
            "QLabel#formBuilder\\.rowError, QLabel#formBuilder\\.inspectorNameError { color: %s; }"
            "%s"
            % (
                panel,
                text,
                text,
                faint,
                text,
                text,
                faint,
                faint,
                caption or text,
                hover or panel,
                caption or text,
                panel,
                faint,
                error or text,
                control_qss(chrome) if chrome is not None else "",
            )
        )

    def paint(self, body: BodyView) -> None:
        searching = bool(self.search.strip())
        if isinstance(body, FormBody):
            self._form.show()
            self._form.paint(body, self._match_color)
            for group in self._groups.values():
                group.hide()
            document = self._services.session.document
            for box in self._form_groups:
                box.paint(document)
            self._chain_dirty = True
            return
        self._form.hide()
        for box in self._form_groups:
            box.hide()
        present = {view.group: view for view in body.groups}
        for group_id in GROUP_ORDER:
            group = self._groups[group_id]
            view = present.get(group_id)
            if view is None:
                group.hide()
                continue
            group.show()
            expanded = True if searching else self._expanded[group_id]
            group.paint(
                view, expanded, searching, self._match_color, body.owners, self._show_qt, self._sort,
            )
        self._chain_dirty = True
        pending = self._pending_focus
        if pending:
            self._pending_focus = ""
            QTimer.singleShot(0, lambda name=pending: self._groups[GroupId.ALL].focus_key(name))

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

    def reveal_after_selection(self) -> None:
        focus = QApplication.focusWidget()
        row = None if not isinstance(focus, QWidget) else self._row_holding(focus)
        if row is not None and row.isVisible():
            self._scroll.ensureWidgetVisible(row)
            return
        self._scroll.verticalScrollBar().setValue(0)

    def _chain_tabs(self) -> None:
        stops = _stops_under(self)
        known = self._tab_key
        if known is not None and len(known) == len(stops) and all(a is b for a, b in zip(known, stops)):
            return
        self._tab_key = tuple(stops)
        previous: Optional[QWidget] = None
        for stop in stops:
            if previous is not None:
                QWidget.setTabOrder(previous, stop)
            previous = stop

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

    def _on_sort(self, checked: bool) -> None:
        self._sort = bool(checked)
        writer = getattr(self._qt_store, "set_sort_properties", None)
        if callable(writer):
            writer(self._sort)
        self.request_rebuild()

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

class _FormGroup(QWidget):
    """One registered form group: an overline toggle over the contributor's body."""

    def __init__(self, services: Services, spec: FormGroupSpec, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.formGroup.%s" % spec.key)
        self._services = services
        self._spec = spec
        self._expanded = True
        self._custom: Optional[GroupBody] = None
        self._host = _GroupHost(services, ())
        self._toggle = QToolButton(self)
        self._toggle.setObjectName("formBuilder.group.%s" % spec.key)
        self._toggle.setProperty("fbFlat", "true")
        self._toggle.setText(spec.title.upper())
        self._toggle.setFont(_overline_font())
        self._toggle.setCheckable(True)
        self._toggle.setChecked(True)
        self._toggle.setAccessibleName("%s group" % spec.title)
        self._toggle.setToolButtonStyle(_beside())
        self._toggle.setArrowType(_arrow(True))
        self._toggle.clicked.connect(self._toggled)
        self._body = QWidget(self)
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(0, 0, 0, 4)
        self._body_layout.setSpacing(2)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._toggle)
        layout.addWidget(self._body)

    def paint(self, document: UiDocument) -> None:
        applies = self._spec.applies
        try:
            wanted = applies is None or bool(applies(document))
        except Exception:
            logger.exception("form group %s could not say if it applies", self._spec.key)
            wanted = False
        if not wanted:
            self.hide()
            return
        self.show()
        self._body.setVisible(self._expanded)
        if not self._expanded:
            return
        try:
            if self._custom is None:
                self._host.set_frame((document.root.id,), False)
                self._custom = self._spec.factory(self._host, self._body)
                self._body_layout.addWidget(self._custom.widget)
            self._host.set_frame((document.root.id,), False)
            self._custom.show(())
        except Exception:
            logger.exception("form group %s failed", self._spec.key)
            self.hide()

    def _toggled(self, checked: bool) -> None:
        self._expanded = bool(checked)
        self._toggle.setArrowType(_arrow(self._expanded))
        self._body.setVisible(self._expanded)


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
        self._show_origin = False
        self._custom: Optional[GroupBody] = None
        self._host: Optional[_GroupHost] = None
        self._toggle = QToolButton(self)
        self._toggle.setObjectName("formBuilder.group.%s" % group.value)
        self._toggle.setProperty("fbFlat", "true")
        self._toggle.setText(group.title.upper())
        self._toggle.setFont(_overline_font())
        self._toggle.setCheckable(True)
        self._toggle.setAccessibleName("%s group" % group.title)
        self._toggle.setChecked(page._expanded[group])
        self._toggle.setToolButtonStyle(_beside())
        self._toggle.setArrowType(_arrow(page._expanded[group]))
        self._toggle.clicked.connect(lambda: self._toggled(self._toggle.isChecked()))
        self._body = QWidget(self)
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(0, 0, 0, 4)
        self._body_layout.setSpacing(2)
        self._adder: Optional[object] = None
        if group is GroupId.ALL:
            from app.features.form_builder.qtside.inspector.editors.custom_props import CustomPropertyAdder

            adder = CustomPropertyAdder(self._body)
            adder.set_handlers(self._run_custom, self._explain_custom, page.focus_property)
            self._adder = adder
            self._body_layout.addWidget(adder)
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
        show_origin: bool = False,
    ) -> None:
        self._view = view
        self._owners = owners
        self._searching = searching
        self._match_color = match_color
        self._qt_names = qt_names
        self._show_origin = show_origin
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

    def focus_key(self, key: str) -> None:
        row = self._rows.get(key)
        if row is None:
            return
        self._page._scroll.ensureWidgetVisible(row)
        edit = row.findChild(QLineEdit)
        if edit is not None:
            edit.setFocus()
            return
        row.setFocus()

    def _run_custom(self, label: str, commands: Sequence[Command]) -> object:
        return self._services.execute_all(label, commands)

    def _explain_custom(self, name: str) -> Optional[str]:
        from app.features.form_builder.qtside.inspector.editors.custom_props import explain_name

        return explain_name(self._services.session.document, self._owners, name)

    def apply_expanded(self, expanded: bool) -> None:
        if self._searching:
            return
        self._toggled(expanded)

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
            self._page._chain_tabs()
            return
        view = self._view
        if view is not None:
            self.paint(view, expanded, False, self._match_color, self._owners, self._qt_names)
        self._page._chain_tabs()

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
                widget.paint(row, match_color, self._qt_names, self._show_origin)
                self._body_layout.addWidget(widget)
                widget.show()
        for extra in self._titles[title_at:]:
            extra.hide()
            self._body_layout.removeWidget(extra)
        adder = self._adder
        if adder is not None:
            has_custom = any(block.title == "Custom properties" for block in view.blocks)
            adder.set_owners(self._owners)  # type: ignore[attr-defined]
            adder.set_heading(not has_custom and not self._show_origin)  # type: ignore[attr-defined]
            adder.show()  # type: ignore[attr-defined]
            self._body_layout.addWidget(adder)  # type: ignore[arg-type]

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
_UNBOUNDED = 16777215
_STACK_GAP = 2
# UX-PED-002: label 96 + gap 8 + editor. The label budget holds the changed
# bar's slot, so the editor column is the row width less 104 at 236 px.
_ROW_GAP = 8
# Below this row width the label uses the compact budget, whatever the window density.
_NARROW_ROW = 300

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
        self._show_origin = False
        self._custom_menu: Optional[QToolButton] = None
        self._type_menu: Optional[QMenu] = None
        self._match_color = ""
        self._painted_widget: Optional[QWidget] = None
        self._painted_sheet = ""
        self._session_key = ""
        # The changed bar, the Qt name, the reset button and the caption are
        # hidden on most rows. They are made on first use: a first build of
        # All properties shows about 60 rows, and each widget costs a polish.
        self._bar: Optional[QFrame] = None
        self._qt: Optional[QLabel] = None
        self._reset: Optional[QToolButton] = None
        self._caption: Optional[QLabel] = None
        self._extra_caption: Optional[QWidget] = None
        self._label = QLabel(self)
        self._elided_key: Optional[Tuple[str, int, str]] = None
        self._elided_text = ""
        self._label.setWordWrap(False)
        self._label_col = QWidget(self)
        self._label_px = _LABEL_WIDE
        self._stacked = False
        self._label_col.setFixedWidth(_LABEL_WIDE - _BAR_SLOT)
        self._column = QVBoxLayout(self._label_col)
        self._column.setContentsMargins(0, 0, 0, 0)
        self._column.setSpacing(0)
        self._column.addWidget(self._label)
        self._slot = QWidget(self)
        self._slot_layout = QVBoxLayout(self._slot)
        self._slot_layout.setContentsMargins(0, 0, 0, 0)
        # One line until an editor asks to stack. The nested head (bar + label)
        # is built only then: a select of All properties builds dozens of rows,
        # and that extra layout showed up in the profile. Until a row is first
        # changed, the line's left margin holds the bar's 2 px and the 6 px
        # after it, so the columns line up.
        self._head: Optional[QHBoxLayout] = None
        self._line = QHBoxLayout()
        self._line.setContentsMargins(_BAR_SLOT, 0, 0, 0)
        self._line.setSpacing(_ROW_GAP)
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
            self._bar = bar
            self._seat_bar()
        return self._bar

    def _seat_bar(self) -> None:
        bar = self._bar
        if bar is None:
            return
        # The bar and its 6 px sit in the head in both directions, so the
        # label starts at _BAR_SLOT whatever the row gap is.
        head = self._ensure_head()
        head.setContentsMargins(0, 0, 0, 0)
        if self._line.indexOf(bar) >= 0:
            self._line.removeWidget(bar)
        if head.indexOf(bar) < 0:
            head.insertWidget(0, bar, 0)

    def _ensure_head(self) -> QHBoxLayout:
        """The bar-and-label line, created the first time a row stacks."""
        head = self._head
        if head is not None:
            return head
        head = QHBoxLayout()
        head.setSpacing(6)
        head.setContentsMargins(0 if self._bar is not None else _BAR_SLOT, 0, 0, 0)
        self._line.removeWidget(self._label_col)
        if self._bar is not None:
            self._line.removeWidget(self._bar)
        head.addWidget(self._label_col, 0)
        if self._bar is not None:
            head.insertWidget(0, self._bar, 0)
            head.setContentsMargins(0, 0, 0, 0)
        self._line.setContentsMargins(0, 0, 0, 0)
        self._line.insertLayout(0, head, 0)
        self._head = head
        return head

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
            self._reset = button
            self._place_reset()
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

    @property
    def row_label(self) -> str:
        return self.label

    @property
    def label(self) -> str:
        view = self._view
        if view is None:
            return ""
        return view.label

    @property
    def qt_name(self) -> str:
        view = self._view
        if view is None:
            return ""
        return view.qt_name

    @property
    def row_widget(self) -> QWidget:
        return self

    @property
    def is_custom(self) -> bool:
        """A custom (dynamic) property row. Its popover title is the name alone."""
        view = self._view
        return isinstance(view, OpenRow) and bool(view.dynamic)

    def document(self) -> UiDocument:
        return self._services.session.document

    def owner_ids(self) -> Tuple[NodeId, ...]:
        view = self._view
        write = getattr(view, "write", None)
        owners = getattr(write, "owners", None)
        if owners:
            return tuple(owners)
        owner = getattr(write, "owner", None)
        if owner is not None:
            return (owner,)
        return ()

    def qt_names(self) -> bool:
        return self._qt_names

    def form_shortcuts(self) -> Mapping[str, str]:
        return form_shortcuts(self._services.session.document)

    def reset(self) -> None:
        """Remove this property from the file. One undo step, outside the edit session."""
        self._reset_clicked()

    def paint(self, view: Row, match_color: str, qt_names: bool = False, show_origin: bool = False) -> None:
        self.setObjectName("formBuilder.row.%s" % view.key)
        self._session_key = view.key
        previous = self._view
        self._view = view
        self._qt_names = qt_names
        self._show_origin = show_origin
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
        elif self._editor is not None and (previous is None or previous.label != view.label):
            # A spared row keeps its editor. Rename only when the label changed,
            # so a select does not walk every child of every row.
            _name_editors(self._editor.widget, view.label)
        self._paint_value_match(view, match_color)
        self._place_caption()
        if not self._invalid and self._editor is not None:
            self._editor.show(view.value)
            self._show_canvas_refusal(view)
        self._elide_label()
        self._sync_reset()

    def set_label_width(self, width: int) -> None:
        self._label_px = width
        self._apply_label_width()

    def resizeEvent(self, event: QEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._sync_stacked()
        self._move_reset()
        self._elide_label()

    def _apply_label_width(self) -> None:
        if self._stacked:
            self._label_col.setMinimumWidth(0)
            self._label_col.setMaximumWidth(_UNBOUNDED)
        else:
            self._label_col.setFixedWidth(max(0, self._label_px - _BAR_SLOT))

    def _label_needs_line(self) -> bool:
        """A phrase that does not fit the 96 px column stacks (UX-PED-002).

        A single long name, such as ``inputMethodHints``, still elides. The
        tooltip keeps the full name.
        """
        view = self._view
        if view is None or not view.label or " " not in view.label:
            return False
        budget = max(0, self._label_px - _BAR_SLOT)
        return self._label.fontMetrics().horizontalAdvance(view.label) > budget

    def _sync_stacked(self) -> None:
        """Stack the label over the editor when the editor asks for it at this width (UX-PED-002)."""
        editor = self._editor
        wants = getattr(editor, "wants_stacked", None)
        stacked = bool(callable(wants) and wants(self.width())) or self._label_needs_line()
        if stacked == self._stacked:
            return
        self._stacked = stacked
        if stacked:
            self._ensure_head()
        direction = getattr(QBoxLayout, "Direction", QBoxLayout)
        self._line.setDirection(
            getattr(direction, "TopToBottom") if stacked else getattr(direction, "LeftToRight")
        )
        self._line.setSpacing(_STACK_GAP if stacked else _ROW_GAP)
        self._label.setWordWrap(stacked)
        self._apply_label_width()
        self._place_reset()
        if self._bar is not None:
            self._seat_bar()

    def _place_reset(self) -> None:
        """The reset button overlays the right edge of the label, so the editor keeps its width."""
        button = self._reset
        if button is None:
            return
        self._line.removeWidget(button)
        if self._head is not None:
            self._head.removeWidget(button)
        button.setParent(self)
        self._move_reset()

    def _move_reset(self) -> None:
        button = self._reset
        if button is None:
            return
        label = self._label
        point = label.mapTo(self, QPoint(max(0, label.width() - button.width()), 0))
        button.move(point)
        button.raise_()

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

    def commit(self, value: Value, session: Optional[EditSession] = None) -> None:
        view = self._view
        if not isinstance(view, OpenRow):
            return
        if session is None:
            session = self._services.inline_session(view.key, _change_label(view.label), self)
        result = session.run(_as_commands(view.write.edit(value, session.token)))
        if isinstance(result, Dropped):
            return
        if isinstance(result, Rejected):
            self._invalid = True
            self._set_caption(rejection_text(result), error=True)
            return
        self._invalid = False
        skipped = result[0] if isinstance(result, tuple) and result else None
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

    def begin_session(self, label: str) -> EditSession:
        return self._services.begin_session(label)

    @property
    def chrome(self):  # type: ignore[no-untyped-def]
        return self._services.chrome

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

    def _reset_clicked(self) -> None:
        view = self._view
        if not isinstance(view, OpenRow):
            return
        self._invalid = False
        if view.dynamic:
            from app.features.form_builder.qtside.inspector.editors.custom_props import remove_commands

            owners = self.owner_ids()
            self._services.execute_all(
                "Remove custom property %s" % view.qt_name,
                remove_commands(owners, view.qt_name),
            )
            self._announce("Removed custom property %s \u00b7 Undo" % view.qt_name)
            return
        produced = view.write.reset()
        words = _reset_words(view.label)
        if isinstance(produced, tuple):
            self._services.execute_all(words, produced)
        else:
            self._services.execute_all(words, (produced,))

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
        _guard_editor(self._editor.widget)
        self._slot_layout.addWidget(self._editor.widget)
        self._editor.widget.show()
        self._sync_stacked()

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

    def _elide_label(self) -> None:
        view = self._view
        if view is None:
            return
        if view.match is not None and view.match.where == "label":
            return
        width = self.width() - _BAR_SLOT if self._stacked else self._label.width()
        if width <= 0:
            return
        full = view.label
        if self._stacked:
            if self._label.text() != full:
                self._label.setText(full)
            self._label.setToolTip(_tip(view))
            return
        # Measure only when the label text or its width changed.
        key = (full, width, _tip(view))
        if self._elided_key == key:
            elided = self._elided_text
        else:
            mode = getattr(getattr(Qt, "TextElideMode", Qt), "ElideRight")
            elided = self._label.fontMetrics().elidedText(full, mode, width)
            self._elided_key = key
            self._elided_text = elided
        if self._label.text() != elided:
            self._label.setText(elided)
        tip = key[2]
        if elided != full:
            self._label.setToolTip(full if not tip or tip == full else "%s\n%s" % (full, tip))
        else:
            self._label.setToolTip(tip)

    def _place_caption(self) -> None:
        editor = self._editor
        widget = getattr(editor, "caption_widget", None) if editor is not None else None
        caption = widget if isinstance(widget, QWidget) else None
        if caption is self._extra_caption:
            return
        previous = self._extra_caption
        if previous is not None:
            self._outer.removeWidget(previous)
            previous.hide()
            previous.deleteLater()
        self._extra_caption = caption
        if caption is None:
            return
        caption.setParent(self)
        self._outer.addWidget(caption)
        caption.show()

    def _paint_qt(self, view: Row, match_color: str) -> None:
        match = view.match
        matched = match is not None and match.where == "qt_name"
        origin = getattr(view, "origin", "") or ""
        show_origin = bool(self._show_origin and origin)
        if not view.qt_name or not (self._qt_names or matched or show_origin):
            if self._qt is not None:
                self._qt.hide()
            return
        label = self._qt_label()
        text = view.qt_name
        write = getattr(view, "write", None)
        if getattr(write, "kind", "") == "attribute":
            text = "%s (attribute)" % text
        if show_origin:
            text = origin if not (self._qt_names or matched) else "%s \u00b7 %s" % (text, origin)
        if matched and not show_origin and getattr(write, "kind", "") != "attribute":
            label.setTextFormat(Qt.RichText)
            label.setText(_marked(view.qt_name, match, "qt_name", match_color))
        else:
            label.setTextFormat(Qt.PlainText)
            label.setText(text)
        label.show()

    def _sync_reset(self) -> None:
        view = self._view
        changed = isinstance(view, OpenRow) and view.changed
        dynamic = isinstance(view, OpenRow) and view.dynamic
        if not changed and not dynamic:
            if self._reset is not None:
                self._reset.hide()
            if self._custom_menu is not None:
                self._custom_menu.hide()
            return
        focus = QApplication.focusWidget()
        inside = self._hovered or (
            focus is not None and (focus is self or self.isAncestorOf(focus))
        )
        if changed:
            button = self._reset_button()
            if dynamic:
                button.setToolTip("Reset removes this custom property")
            else:
                button.setToolTip("Reset: remove this property from the file")
            button.setVisible(inside)
            self._move_reset()
        elif self._reset is not None:
            self._reset.hide()
        if dynamic:
            self._custom_button().setVisible(True)
        elif self._custom_menu is not None:
            self._custom_menu.hide()

    def _custom_button(self) -> QToolButton:
        button = self._custom_menu
        if button is not None:
            return button
        button = QToolButton(self)
        button.setObjectName("formBuilder.customMenu")
        button.setProperty("fbFlat", "true")
        button.setText("\u22ef")
        button.setFixedSize(16, 16)
        button.setAccessibleName("Custom property menu")
        button.setPopupMode(_popup_mode())
        button.setStyleSheet("QToolButton::menu-indicator { image: none; width: 0px; }")
        menu = QMenu(button)
        menu.addAction("Rename\u2026").triggered.connect(self._rename_custom)
        types = menu.addMenu("Change type")
        self._type_menu = types
        from app.features.form_builder.qtside.inspector.editors.custom_props import TYPES

        for label, kind in TYPES:
            types.addAction(label).triggered.connect(
                lambda _checked=False, chosen=kind, title=label: self._change_type(chosen, title)
            )
        menu.addAction("Remove").triggered.connect(self._reset_clicked)
        button.setMenu(menu)
        self._line.addWidget(button, 0)
        self._custom_menu = button
        return button

    def _rename_custom(self) -> None:
        from app.qt.QtWidgets import QInputDialog

        from app.features.form_builder.qtside.inspector.editors.custom_props import (
            explain_name,
            rename_commands,
        )

        view = self._view
        if not isinstance(view, OpenRow) or not isinstance(view.value, Written):
            return
        text, ok = QInputDialog.getText(self, "Rename", "Name", text=view.qt_name)
        if not ok:
            return
        name = str(text).strip()
        sentence = explain_name(self.document(), self.owner_ids(), name)
        if sentence is not None or name == view.qt_name:
            if sentence:
                self._set_caption(sentence, error=True)
            return
        owners = self.owner_ids()
        if not owners:
            return
        self._services.execute_all(
            "Rename custom property",
            rename_commands(owners[0], view.qt_name, name, view.value.value),
        )

    def _change_type(self, kind: str, title: str) -> None:
        from app.features.form_builder.engine.commands.catalog import SetProperty

        from app.features.form_builder.qtside.inspector.editors.custom_props import (
            confirm_clear,
            convert_value,
            empty_value,
        )

        view = self._view
        if not isinstance(view, OpenRow) or not isinstance(view.value, Written):
            return
        converted = convert_value(view.value.value, kind)
        if converted is None:
            if not confirm_clear(self, view.qt_name, title):
                return
            converted = empty_value(kind)
        owners = self.owner_ids()
        if not owners:
            return
        self._services.execute_all(
            "Change type of %s" % view.qt_name,
            (SetProperty(owners[0], view.qt_name, converted, stdset="0"),),
        )

    def _announce(self, text: str) -> None:
        parent = self.parentWidget()
        while parent is not None:
            toast = getattr(parent, "toast", None)
            if callable(toast):
                toast(text)
                return
            parent = parent.parentWidget()

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
        extra = self._extra_caption
        if extra is not None:
            self._outer.removeWidget(extra)
            extra.hide()
            extra.deleteLater()
            self._extra_caption = None
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

    def _show_canvas_refusal(self, view: Row) -> None:
        """UX-PED-009: the value stays in the file even when the canvas widget refuses it."""
        refused = any(self._services.refused(owner, view.qt_name) for owner in self.owner_ids())
        if refused:
            self._set_caption(CANVAS_REFUSED_TEXT, error=False, warning=True)
        elif self._caption is not None and self._caption.text() == CANVAS_REFUSED_TEXT:
            self._set_caption("", error=False)

    def _set_caption(self, text: str, *, error: bool, warning: bool = False) -> None:
        if not text:
            if self._caption is not None:
                self._caption.hide()
                self._caption.clear()
                self._caption.setStyleSheet("")
            return
        caption = self._caption_label()
        # UX-PED-009 names fb.warning for the canvas refusal; other notes keep the row-note rule.
        caption.setStyleSheet("color: %s;" % warning_color(self._services.chrome) if warning else "")
        name = "formBuilder.rowError" if error else "formBuilder.rowNote"
        if caption.objectName() != name:
            # A new object name does not restyle the label by itself.
            caption.setObjectName(name)
            style = caption.style()
            style.unpolish(caption)
            style.polish(caption)
        caption.setText(text)
        caption.show()

CANVAS_REFUSED_TEXT = "Saved in the file. The canvas can't show this value."


def _reset_words(label: str) -> str:
    """UX-PED-006. The row label stays as written: "Reset Tooltip"."""
    if not label:
        return "Reset"
    return "Reset %s" % label


def _change_label(label: str) -> str:
    """The undo name of a row's own edit: "Change maximum length"."""
    if not label:
        return "Change value"
    return "Change " + label[0].lower() + label[1:]


def _as_commands(produced: Union[Command, Tuple[Command, ...]]) -> Tuple[Command, ...]:
    if isinstance(produced, tuple):
        return produced
    return (produced,)


_EVENT = getattr(QEvent, "Type", QEvent)


def _focus_within(widget: QWidget) -> bool:
    focus = QApplication.focusWidget()
    return focus is not None and (focus is widget or widget.isAncestorOf(focus))


class _EditorGuard(QObject):
    """Installed on a spin box, a combo box or a slider.

    UX-PED-005: a wheel event over a field without keyboard focus is passed on
    (ignored, so the inspector scrolls) and does not change the value. Focus
    leaving a field is one ``QApplication.focusChanged`` hook on ``Services``,
    not a filter per widget.
    """

    def __init__(self, target: QWidget) -> None:
        super().__init__(target)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() != _EVENT.Wheel:
            return False
        if isinstance(watched, QWidget) and not _focus_within(watched):
            # Returning True stops the child from handling it; the ignored event
            # then travels on to the parents, so the inspector scrolls.
            event.ignore()
            return True
        return False


_WHEEL_KINDS = (QAbstractSpinBox, QComboBox, QAbstractSlider)


def _guard_editor(root: QWidget) -> None:
    """Install the wheel guard only on widgets that change value from the wheel.

    A filter runs in Python for every event its widget gets. Line edits,
    labels and containers get none.
    """
    for target in [root, *root.findChildren(QWidget)]:
        if isinstance(target, _WHEEL_KINDS):
            target.installEventFilter(_EditorGuard(target))


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
    def session(self) -> object:
        return self._services.session

    @property
    def owners(self) -> Tuple[NodeId, ...]:
        return self._owners

    @property
    def qt_names(self) -> bool:
        return self._qt_names

    def live(self, owner: NodeId) -> Optional[QWidget]:
        return self._services.live(owner)

    def layout(self, owner: NodeId) -> Optional[QLayout]:
        return self._services.layout(owner)

    def run(self, label: str, commands: Sequence[Command]) -> Optional[str]:
        result = self._services.execute_all(label, commands)
        if isinstance(result, Rejected):
            return rejection_text(result)
        return None

    def editor_for(self, row: Row, parent: QWidget) -> Editor:
        widget = _Row(self._services, parent)
        widget.paint(row, "", self._qt_names)
        return _BoundEditor(widget, row, self._qt_names)

class _BoundEditor:
    def __init__(self, row: _Row, view: Row, qt_names: bool) -> None:
        self._row = row
        self._view = view
        self._qt_names = qt_names

    @property
    def widget(self) -> QWidget:
        return self._row

    def show(self, value: RowValue) -> None:
        # A full paint, so the changed bar and Reset follow the value too.
        self._view = dataclasses.replace(self._view, value=value)
        self._row.paint(self._view, "", self._qt_names)

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

_VALUE_KINDS = (
    "QSpinBox",
    "QDoubleSpinBox",
    "QLineEdit",
    "QComboBox",
    "QFontComboBox",
    "QPlainTextEdit",
    "QKeySequenceEdit",
)
_BUTTON_KINDS = ("QCheckBox", "QPushButton", "QToolButton", "QRadioButton")


def _lead(label: str) -> str:
    if not label:
        return label
    return label[0].upper() + label[1:]


def _name_editors(root: QWidget, label: str) -> None:
    """Name the editor and the line edit Qt uses as its focus proxy.

    A summary button already carries "{label}: {summary}". Rebinding sets the
    row label and leaves the summary half alone.
    """
    if isinstance(root, SummaryButton):
        root.set_row_label(label)
    else:
        root.setAccessibleName(label)
        _name_line(root, label)
    lead = _lead(label)
    no_focus = getattr(getattr(Qt, "FocusPolicy", Qt), "NoFocus")
    for child in root.findChildren(QWidget):
        if isinstance(child, SummaryButton):
            child.set_row_label(label)
            continue
        if child.accessibleName():
            _name_line(child, child.accessibleName())
            continue
        meta = child.metaObject()
        kind = str(meta.className()) if meta is not None else ""
        if kind in _VALUE_KINDS:
            child.setAccessibleName(label)
            _name_line(child, label)
            continue
        if kind in _BUTTON_KINDS:
            reader = getattr(child, "text", None)
            text = str(reader()).strip() if callable(reader) else ""
            child.setAccessibleName("%s: %s" % (lead, text) if text else lead)
            continue
        if child.focusPolicy() != no_focus:
            child.setAccessibleName(lead)


def _tab_stop(widget: QWidget) -> bool:
    if not widget.isVisible() or not widget.isEnabled():
        return False
    no_focus = getattr(getattr(Qt, "FocusPolicy", Qt), "NoFocus")
    return widget.focusPolicy() != no_focus


def _stops_under(widget: QWidget) -> List[QWidget]:
    if not widget.isVisible():
        return []
    if isinstance(widget, QScrollArea):
        found: List[QWidget] = []
        if _tab_stop(widget):
            found.append(widget)
        content = widget.widget()
        if content is not None:
            found.extend(_stops_under(content))
        return found
    if _tab_stop(widget):
        return [widget]
    layout = widget.layout()
    if layout is not None:
        return _stops_in_layout(layout, widget)
    found = []
    for child in widget.children():
        if isinstance(child, QWidget):
            found.extend(_stops_under(child))
    return found


def _stops_in_layout(layout: QLayout, owner: QWidget) -> List[QWidget]:
    """Stops in layout order, without ``QLayout.itemAt``.

    PySide keeps every ``itemAt`` wrapper alive with its layout. Qt deletes the
    item when its widget goes, the wrapper stays registered, and a new object at
    that address comes back as a ``QWidgetItem``. So order the owner's child
    widgets and the nested layouts by ``indexOf`` instead.
    """
    entries: List[Tuple[int, int, object]] = []
    for child in owner.children():
        if isinstance(child, QWidget):
            index = layout.indexOf(child)
            if index >= 0:
                entries.append((index, len(entries), child))
    for child in layout.children():
        if isinstance(child, QLayout):
            index = layout.indexOf(child)
            if index >= 0:
                entries.append((index, len(entries), child))
    entries.sort(key=lambda entry: (entry[0], entry[1]))
    found: List[QWidget] = []
    for _index, _order, child in entries:
        if isinstance(child, QLayout):
            found.extend(_stops_in_layout(child, owner))
        elif isinstance(child, QWidget):
            found.extend(_stops_under(child))
    return found


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
