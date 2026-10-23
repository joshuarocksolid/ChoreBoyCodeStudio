"""The Properties tab. Rows reconcile by key, so a focused editor survives its own commit."""

from __future__ import annotations

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
    GroupId,
    LockedRow,
    Match,
    Mixed,
    OpenRow,
    Row,
    RowValue,
    Unset,
)
from app.features.form_builder.qtside.inspector.model import (
    BodyView,
    FormBody,
    GroupView,
    value_text,
)
from app.qt.QtCore import Qt
from app.qt.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

_DRAG = "Drag the page's right or bottom edge to try other sizes."
_LABEL_WIDTH = 104


class PropertiesPage(QWidget):
    """Object name formBuilder.inspectorBody. Search sits above the scrolled groups."""

    def __init__(self, services: Services, on_search: Callable[[], None], parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.inspectorBody")
        self._services = services
        self._on_search = on_search
        self._match_color = ""
        self._expanded: Dict[GroupId, bool] = {group: group is not GroupId.ALL for group in GroupId}
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
        self._scroll = QScrollArea(self)
        self._scroll.setObjectName("formBuilder.inspectorScroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(_no_frame())
        self._content = QWidget(self._scroll)
        self._content.setObjectName("formBuilder.inspectorContent")
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(8, 4, 8, 8)
        self._content_layout.setSpacing(4)
        self._form = _FormSection(services, self._content)
        self._content_layout.addWidget(self._form)
        self._groups: Dict[GroupId, _Group] = {}
        for group in GroupId:
            widget = _Group(services, group, self, self._content)
            self._groups[group] = widget
            self._content_layout.addWidget(widget)
            widget.hide()
        self._content_layout.addStretch(1)
        self._scroll.setWidget(self._content)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._search)
        layout.addWidget(self._pill)
        layout.addWidget(self._scroll, 1)
        self.setFocusProxy(self._search)

    @property
    def search(self) -> str:
        return self._search.text()

    def set_match_color(self, color: str) -> None:
        self._match_color = color

    def apply_colors(self, panel: str, text: str, faint: str) -> None:
        """The scroll viewport does not inherit the inspector stylesheet."""
        self.setStyleSheet(
            "QWidget#formBuilder\\.inspectorBody { background: %s; color: %s; }"
            "QLabel { color: %s; background: transparent; }"
            % (panel, text, text)
        )
        self._scroll.setStyleSheet(
            "QScrollArea#formBuilder\\.inspectorScroll { background: %s; border: none; }" % panel
        )
        viewport = self._scroll.viewport()
        viewport.setAutoFillBackground(False)
        viewport.setStyleSheet("background: %s;" % panel)
        self._content.setStyleSheet(
            "QWidget#formBuilder\\.inspectorContent { background: %s; color: %s; }"
            "QLabel { color: %s; background: transparent; }"
            "QLabel#formBuilder\\.rowQtName, QLabel#formBuilder\\.rowDefault,"
            " QLabel#formBuilder\\.rowMixed { color: %s; }"
            "QToolButton { color: %s; background: transparent; border: none; }"
            % (panel, text, text, faint, text)
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
        for group_id in GroupId:
            group = self._groups[group_id]
            view = present.get(group_id)
            if view is None:
                group.hide()
                continue
            group.show()
            expanded = True if searching else self._expanded[group_id]
            group.paint(view, expanded, searching, self._match_color, body.owners)

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

    def revert_focused_row(self) -> None:
        focus = QApplication.focusWidget()
        if focus is None:
            return
        row = self._row_holding(focus)
        if row is not None:
            row.revert()

    def _search_changed(self, text: str) -> None:
        if text.strip():
            self._pill.setText("Filtered: %s \u00b7 <a href=\"clear\">Clear</a>" % _escape(text.strip()))
            self._pill.show()
        else:
            self._pill.hide()
        self._on_search()

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
        self._window: Optional[_Row] = None
        self._size = QLabel(self)
        self._drag = QLabel(_DRAG, self)
        self._drag.setWordWrap(True)
        self._layout_name = QLabel(self)
        self._order = QLabel(self)
        self._order.setWordWrap(True)
        self._problems = QLabel(self)
        self._files = QLabel(self)
        self._files.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self._layout = layout
        layout.addWidget(self._size)
        layout.addWidget(self._drag)
        layout.addWidget(self._layout_name)
        layout.addWidget(self._order)
        layout.addWidget(self._problems)
        layout.addWidget(self._files)

    def paint(self, body: FormBody, match_color: str) -> None:
        window = body.window
        if window is None:
            if self._window is not None:
                self._window.hide()
        else:
            if self._window is None:
                self._window = _Row(self._services, self)
                self._layout.insertWidget(0, self._window)
            self._window.show()
            self._window.paint(window, match_color)
        self._size.setText(body.design_size)
        self._layout_name.setText(body.root_layout)
        self._order.setText("\n".join(body.tab_order))
        self._problems.setText(body.problems)
        self._files.setText(body.files)

    def row_holding(self, focus: QWidget) -> Optional["_Row"]:
        row = self._window
        if row is not None and (focus is row or row.isAncestorOf(focus)):
            return row
        return None


class _Group(QWidget):
    """A collapsible group. A collapsed group builds no rows."""

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
        self._titles: List[QLabel] = []
        self._custom: Optional[GroupBody] = None
        self._host: Optional[_GroupHost] = None
        self._toggle = QToolButton(self)
        self._toggle.setText(group.title)
        self._toggle.setCheckable(True)
        self._toggle.setChecked(page._expanded[group])
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
    ) -> None:
        self._view = view
        self._owners = owners
        self._searching = searching
        self._match_color = match_color
        self._toggle.setText(view.group.title)
        self._toggle.setChecked(expanded)
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

    def row_holding(self, focus: QWidget) -> Optional["_Row"]:
        for row in self._rows.values():
            if focus is row or row.isAncestorOf(focus):
                return row
        return None

    def _toggled(self, checked: bool) -> None:
        if self._searching:
            self._toggle.setChecked(True)
            return
        self._page._set_expanded(self._group, bool(checked))
        view = self._view
        if view is not None:
            self.paint(view, bool(checked), False, self._match_color, self._owners)

    def _paint_custom(self, view: GroupView, factory: GroupBodyFactory) -> None:
        if self._custom is None:
            self._host = _GroupHost(self._services, self._owners)
            self._custom = factory(self._host, self._body)
            self._body_layout.addWidget(self._custom.widget)
        self._custom.show(view.rows())

    def _hide_custom(self) -> None:
        custom = self._custom
        if custom is not None:
            custom.widget.hide()

    def _paint_rows(self, view: GroupView, match_color: str) -> None:
        wanted = [row.key for block in view.blocks for row in block.rows]
        for key in [key for key in self._rows if key not in wanted]:
            widget = self._rows.pop(key)
            self._release(widget)
            self._body_layout.removeWidget(widget)
            widget.hide()
            widget.deleteLater()
        for title in self._titles:
            self._body_layout.removeWidget(title)
            title.hide()
            title.deleteLater()
        self._titles = []
        for block in view.blocks:
            if block.title:
                label = QLabel(block.title, self._body)
                label.setObjectName("formBuilder.blockTitle")
                label.show()
                self._titles.append(label)
                self._body_layout.addWidget(label)
            for row in block.rows:
                widget = self._rows.get(row.key)
                if widget is None:
                    widget = _Row(self._services, self._body)
                    self._rows[row.key] = widget
                widget.show()
                widget.paint(row, match_color)
                self._body_layout.addWidget(widget)

    def _drop_rows(self) -> None:
        for key in list(self._rows):
            widget = self._rows.pop(key)
            self._release(widget)
            self._body_layout.removeWidget(widget)
            widget.hide()
            widget.deleteLater()
        for title in self._titles:
            self._body_layout.removeWidget(title)
            title.hide()
            title.deleteLater()
        self._titles = []

    def _release(self, widget: QWidget) -> None:
        focus = QApplication.focusWidget()
        if focus is not None and (focus is widget or widget.isAncestorOf(focus)):
            self._page.setFocus()

class _Row(QWidget):
    """Label, editor, changed bar, reset, and caption. The editor's EditorHost."""

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
        self._bar = QFrame(self)
        self._bar.setObjectName("formBuilder.rowChanged")
        self._bar.setFixedWidth(2)
        self._bar.setMinimumHeight(18)
        self._bar.hide()
        self._label = QLabel(self)
        self._label.setFixedWidth(_LABEL_WIDTH)
        self._label.setWordWrap(True)
        self._qt = QLabel(self)
        self._qt.setObjectName("formBuilder.rowQtName")
        self._qt.hide()
        self._slot = QWidget(self)
        self._slot_layout = QVBoxLayout(self._slot)
        self._slot_layout.setContentsMargins(0, 0, 0, 0)
        self._reset = QToolButton(self)
        self._reset.setObjectName("formBuilder.rowReset")
        self._reset.setText("Reset")
        self._reset.clicked.connect(self._reset_clicked)
        self._reset.hide()
        self._caption = QLabel(self)
        self._caption.setWordWrap(True)
        self._caption.hide()
        line = QHBoxLayout()
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(6)
        line.addWidget(self._bar, 0)
        line.addWidget(self._label, 0)
        line.addWidget(self._qt, 0)
        line.addWidget(self._slot, 1)
        line.addWidget(self._reset, 0)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(2)
        layout.addLayout(line)
        layout.addWidget(self._caption)

    def is_invalid(self) -> bool:
        return self._invalid

    def paint(self, view: Row, match_color: str) -> None:
        self.setObjectName("formBuilder.row.%s" % view.key)
        previous = self._view
        self._view = view
        self._label.setToolTip(view.help)
        self._paint_label(view, match_color)
        self._paint_qt(view, match_color)
        changed = view.changed
        self._bar.setVisible(changed)
        open_row = isinstance(view, OpenRow)
        self._reset.setVisible(open_row and changed)
        if isinstance(view, LockedRow):
            self._show_locked(view, match_color)
            return
        if self._needs_new_editor(previous, view):
            self._invalid = False
            self._build_editor(view)
        self._paint_value_match(view, match_color)
        if self._invalid:
            return
        if self._editor is not None:
            self._editor.show(view.value)

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
        self._slot_layout.addWidget(self._editor.widget)
        self._editor.widget.show()

    def _show_locked(self, view: LockedRow, match_color: str) -> None:
        self._clear_slot()
        self._editor = None
        text = value_text(view.value) or NOT_SET_TEXT
        label = QLabel(self._slot)
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
        if view.match is not None and view.match.where == "label":
            self._label.setTextFormat(Qt.RichText)
            self._label.setText(_marked(view.label, view.match, "label", match_color))
            return
        self._label.setTextFormat(Qt.PlainText)
        self._label.setText(view.label)

    def _paint_qt(self, view: Row, match_color: str) -> None:
        match = view.match
        if match is None or match.where != "qt_name":
            self._qt.hide()
            return
        self._qt.setTextFormat(Qt.RichText)
        self._qt.setText(_marked(view.qt_name, match, "qt_name", match_color))
        self._qt.show()

    def _paint_value_match(self, view: OpenRow, match_color: str) -> None:
        widget = None if self._editor is None else self._editor.widget
        if widget is None:
            return
        match = view.match
        if match is not None and match.where == "value" and match_color:
            widget.setStyleSheet("background-color: %s;" % match_color)
            return
        widget.setStyleSheet("")

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
            self._caption.hide()
            self._caption.clear()
            return
        self._caption.setObjectName(
            "formBuilder.rowError" if error else "formBuilder.rowNote"
        )
        self._caption.setText(text)
        self._caption.show()


class _GroupHost:
    """GroupHost for a registered group body."""

    def __init__(self, services: Services, owners: Tuple[NodeId, ...]) -> None:
        self._services = services
        self._owners = owners

    @property
    def document(self) -> UiDocument:
        return self._services.session.document

    @property
    def owners(self) -> Tuple[NodeId, ...]:
        return self._owners

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


def _no_frame() -> QFrame.Shape:
    return getattr(getattr(QFrame, "Shape", QFrame), "NoFrame")
