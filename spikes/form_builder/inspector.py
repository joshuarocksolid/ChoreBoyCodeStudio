"""Inspector: a tab host. Properties today; Behavior and Data are ready for the logic phase.

Never empty: with nothing selected it shows the form itself. Sizing is in words
(Hug / Fill / Fixed, Share) with a "why is this size?" sentence. Every Reset
removes the property line. Editors keep focus across the rebuild that follows a
commit, so typing a value and pressing Enter never throws the keyboard away.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QSizePolicy,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTabBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from spikes.form_builder import sizing
from spikes.form_builder.commands import (
    AddConnection,
    Compound,
    InsertChild,
    RemoveConnection,
    Rename,
    SetAttribute,
    SetComboItems,
    SetLayoutAttrib,
    SetProperties,
    SetProperty,
    SetTabStops,
    pair_buddies,
    resolve_layout_item,
)
from spikes.form_builder.icons import glyph_for_class, pixmap
from spikes.form_builder.kit import EmptyState, IconButton, NumberField, ScrubLabel, Section, SegmentedControl, hairline, label
from spikes.form_builder.model import (
    INPUT_CLASSES,
    Action,
    ActionRef,
    Connection,
    ItemEntry,
    Layout,
    Property,
    Spacer,
    Widget,
    all_names,
    child_widgets,
    connections_of,
    effective_tab_order,
    find_node,
    get_attribute,
    get_property,
    iter_nodes,
    iter_widgets,
    layout_items,
    locate,
    problems,
    prop_bool,
    prop_cstring,
    prop_double,
    prop_enum,
    prop_number,
    prop_set,
    prop_string,
    reading_order,
    tabstops_of,
    valid_identifier,
    widget_layout,
    widget_path,
)
from spikes.form_builder.theme import current

CURATED = {
    "QLabel": ["text", "alignment", "wordWrap"],
    "QPushButton": ["text", "default", "checkable", "flat"],
    "QToolButton": ["text", "checkable", "autoRaise"],
    "QCheckBox": ["text", "checked", "tristate"],
    "QRadioButton": ["text", "checked"],
    "QLineEdit": ["placeholderText", "text", "echoMode", "maxLength", "readOnly", "clearButtonEnabled"],
    "QPlainTextEdit": ["placeholderText", "plainText", "readOnly"],
    "QTextEdit": ["placeholderText", "readOnly"],
    "QSpinBox": ["value", "minimum", "maximum", "singleStep", "prefix", "suffix"],
    "QDoubleSpinBox": ["value", "minimum", "maximum", "singleStep", "decimals", "prefix", "suffix"],
    "QComboBox": ["editable", "currentIndex"],
    "QDateEdit": ["displayFormat", "calendarPopup"],
    "QDateTimeEdit": ["displayFormat", "calendarPopup"],
    "QTimeEdit": ["displayFormat"],
    "QSlider": ["orientation", "minimum", "maximum", "value"],
    "QProgressBar": ["value", "minimum", "maximum", "textVisible"],
    "QGroupBox": ["title", "checkable", "checked", "flat"],
    "QFrame": ["frameShape", "frameShadow"],
    "QTabWidget": ["tabPosition", "currentIndex"],
    "QStackedWidget": ["currentIndex"],
    "QDialogButtonBox": ["standardButtons", "orientation", "centerButtons"],
    "QListWidget": ["alternatingRowColors", "selectionMode"],
    "QTableWidget": ["alternatingRowColors", "selectionMode"],
    "QTreeWidget": ["alternatingRowColors", "selectionMode"],
    "QSplitter": ["orientation", "childrenCollapsible", "handleWidth"],
    "QScrollArea": ["widgetResizable"],
    "QMenu": ["title"],
    "QMainWindow": ["windowTitle"],
    "QDialog": ["windowTitle", "modal"],
    "QWidget": [],
}
COMMON = ["enabled", "toolTip"]
WORD_LABELS = {
    "text": "Text",
    "placeholderText": "Placeholder",
    "plainText": "Text",
    "alignment": "Alignment",
    "wordWrap": "Wrap words",
    "echoMode": "Echo",
    "maxLength": "Max length",
    "readOnly": "Read-only",
    "clearButtonEnabled": "Clear button",
    "enabled": "Enabled",
    "toolTip": "Tooltip",
    "checked": "Checked",
    "checkable": "Checkable",
    "title": "Title",
    "windowTitle": "Title",
    "standardButtons": "Buttons",
    "orientation": "Direction",
    "currentIndex": "Current",
    "displayFormat": "Format",
    "calendarPopup": "Calendar",
    "singleStep": "Step",
    "selectionMode": "Selection",
    "alternatingRowColors": "Striped rows",
    "frameShape": "Shape",
    "frameShadow": "Shadow",
    "tabPosition": "Tabs at",
    "default": "Default",
    "flat": "Flat",
    "autoRaise": "Auto raise",
    "tristate": "Three states",
    "textVisible": "Show text",
    "centerButtons": "Centred",
    "childrenCollapsible": "Collapsible",
    "handleWidth": "Handle",
    "widgetResizable": "Resizable",
    "modal": "Modal",
    "decimals": "Decimals",
    "prefix": "Prefix",
    "suffix": "Suffix",
    "value": "Value",
    "minimum": "Minimum",
    "maximum": "Maximum",
}
LAYOUT_KINDS = [("QVBoxLayout", "", "QVBoxLayout", "Vertical"), ("QHBoxLayout", "", "QHBoxLayout", "Horizontal"),
                ("QGridLayout", "", "QGridLayout", "Grid"), ("QFormLayout", "", "QFormLayout", "Form")]


class Inspector(QWidget):
    select_request = Signal(list)
    status = Signal(str)
    remove_layout = Signal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("Panel")
        self.doc = None
        self.history = None
        self.canvas = None
        self.path = None
        self.selection: list[str] = []
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.header = QWidget()
        self.header_layout = QVBoxLayout(self.header)
        self.header_layout.setContentsMargins(14, 12, 12, 4)
        self.header_layout.setSpacing(2)
        outer.addWidget(self.header)
        self.tabs = QTabBar()
        self.tabs.setExpanding(False)
        self.tabs.setDrawBase(False)
        for text in ("Properties", "Behavior", "Data"):
            self.tabs.addTab(text)
        tab_row = QHBoxLayout()
        tab_row.setContentsMargins(8, 0, 8, 0)
        tab_row.addWidget(self.tabs)
        tab_row.addStretch(1)
        outer.addLayout(tab_row)
        outer.addWidget(hairline())
        self.pages = QStackedWidget()
        self.scrolls = []
        for _index in range(3):
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.NoFrame)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.scrolls.append(scroll)
            self.pages.addWidget(scroll)
        outer.addWidget(self.pages, 1)
        self.tabs.currentChanged.connect(self._tab_changed)
        self._focus_key = None
        self._stale = set()

    # ------------------------------------------------------------------ public
    def set_session(self, doc, history, canvas, path=None):
        self.doc = doc
        self.history = history
        self.canvas = canvas
        self.path = path

    def show_selection(self, ids):
        self.selection = [node_id for node_id in ids if self.doc is not None and find_node(self.doc, node_id) is not None]
        self._remember_focus()
        self._rebuild()
        QTimer.singleShot(0, self._restore_focus)

    def show_tab(self, name: str):
        self.tabs.setCurrentIndex({"properties": 0, "behavior": 1, "data": 2}.get(name, 0))

    def focus_name(self):
        field = self.header.findChild(QLineEdit, "NameField")
        if field is not None:
            field.setFocus()
            field.selectAll()

    # ------------------------------------------------------------------ focus
    def _remember_focus(self):
        focus = self.focusWidget()
        self._focus_key = None
        if focus is not None and self.isAncestorOf(focus) and focus.hasFocus():
            self._focus_key = focus.property("inspectorKey")
        self._scroll = [scroll.verticalScrollBar().value() for scroll in self.scrolls]

    def _restore_focus(self):
        for scroll, value in zip(self.scrolls, getattr(self, "_scroll", [0, 0, 0])):
            scroll.verticalScrollBar().setValue(value)
        if not self._focus_key:
            return
        for widget in self.findChildren(QWidget):
            if widget.property("inspectorKey") == self._focus_key and widget.isVisible():
                widget.setFocus()
                if isinstance(widget, QLineEdit):
                    widget.deselect()
                    widget.end(False)
                return

    # ------------------------------------------------------------------ build
    def _clear(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()
            elif item.layout() is not None:
                self._clear(item.layout())

    def _page(self, index) -> QVBoxLayout:
        body = QWidget()
        body.setObjectName("InspectorBody")
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 16)
        layout.setSpacing(0)
        old = self.scrolls[index].takeWidget()
        if old is not None:
            old.deleteLater()
        self.scrolls[index].setWidget(body)
        return layout

    def _rebuild(self):
        """Header and the visible tab now; the other tabs when they are opened."""
        self._clear(self.header_layout)
        self._stale = {0, 1, 2}
        if self.doc is None:
            props = self._page(0)
            props.addWidget(EmptyState("design", "No form open", "Pick a template on the start screen."))
            props.addStretch(1)
            return
        nodes = self._nodes()
        if len(nodes) > 1:
            self._header_multi(nodes)
        elif not nodes or nodes[0] is self.doc.root:
            self._header(self.doc.root, form=True)
        else:
            self._header(nodes[0])
        target = nodes[0] if len(nodes) == 1 and isinstance(nodes[0], Widget) else self.doc.root
        count = _connection_count(self.doc, target)
        self.tabs.setTabText(1, f"Behavior  {count}" if count else "Behavior")
        self._build_page(self.tabs.currentIndex())

    def _nodes(self):
        nodes = [find_node(self.doc, node_id) for node_id in self.selection]
        return [node for node in nodes if node is not None]

    def _tab_changed(self, index):
        self.pages.setCurrentIndex(index)
        if index in getattr(self, "_stale", set()) and self.doc is not None:
            self._build_page(index)

    def _build_page(self, index):
        self._stale.discard(index)
        layout = self._page(index)
        nodes = self._nodes()
        if index == 0:
            if len(nodes) > 1:
                self._multi(layout, [node for node in nodes if isinstance(node, Widget)])
            elif not nodes or nodes[0] is self.doc.root:
                self._form(layout, self.doc.root)
            else:
                node = nodes[0]
                if isinstance(node, Widget):
                    self._widget(layout, node)
                elif isinstance(node, Layout):
                    self._layout_section(layout, node, owner=None)
                elif isinstance(node, Spacer):
                    self._spacer(layout, node)
                elif isinstance(node, Action):
                    self._action(layout, node)
        elif index == 1:
            target = nodes[0] if len(nodes) == 1 and isinstance(nodes[0], Widget) else self.doc.root
            self._behavior(layout, target)
        else:
            self._data(layout)
        layout.addStretch(1)
        self._narrow(self.scrolls[index].widget())

    def _narrow(self, body):
        """Nothing in the inspector may force it wider than the pane."""
        for combo in body.findChildren(QComboBox):
            combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(6)
        for button in body.findChildren(QToolButton):
            if button.popupMode() == QToolButton.InstantPopup:
                button.setMinimumWidth(60)
                button.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        for edit in body.findChildren(QLineEdit):
            if edit.minimumWidth() == 0:
                edit.setMinimumWidth(40)

    # ------------------------------------------------------------------ header
    def _header(self, node, form: bool = False):
        tokens = current()
        row = QHBoxLayout()
        row.setSpacing(6)
        glyph = QLabel()
        class_name = getattr(node, "class_name", "") or ("Action" if isinstance(node, Action) else "Spacer")
        if isinstance(node, Action):
            glyph.setPixmap(pixmap("Action", tokens.warn, 18))
        else:
            color = tokens.layout if isinstance(node, Layout) else (tokens.gap if isinstance(node, Spacer) else tokens.accent)
            glyph.setPixmap(pixmap(glyph_for_class(class_name), color, 18))
        row.addWidget(glyph)
        name = QLineEdit(_node_name(node))
        name.setObjectName("NameField")
        name.setProperty("inspectorKey", "name")
        name.setToolTip("Object name. Your code uses it as self.ui.<name>. F2 or click to rename.")
        row.addWidget(name, 1)
        self.header_layout.addLayout(row)
        sub = QHBoxLayout()
        sub.setSpacing(4)
        kind = "Form · " + class_name if form else class_name
        if isinstance(node, Action):
            kind = "Action"
        elif isinstance(node, Spacer):
            kind = "Spacer"
        sub.addWidget(label(kind, "Faint"))
        sub.addStretch(1)
        self.header_layout.addLayout(sub)
        warn = label("", "Danger", wrap=True)
        warn.hide()
        self.header_layout.addWidget(warn)

        def commit():
            text = name.text().strip()
            if text == _node_name(node):
                warn.hide()
                return
            if not valid_identifier(text):
                warn.setText(f"“{text}” is not a Python name. Use letters, digits and _, not starting with a digit.")
                warn.show()
                return
            if text in all_names(self.doc):
                warn.setText(f"“{text}” is already used on this form.")
                warn.show()
                return
            warn.hide()
            self.history.execute(Rename(node.id, text))

        name.editingFinished.connect(commit)
        if not form and not isinstance(node, Action):
            path = widget_path(self.doc, node.id)
            if len(path) > 1:
                crumbs = QHBoxLayout()
                crumbs.setSpacing(2)
                ancestors = self._ancestor_ids(node.id)
                for position, (text, node_id) in enumerate(zip(path[:-1], ancestors)):
                    link = QPushButton(text)
                    link.setObjectName("Link")
                    link.setCursor(Qt.PointingHandCursor)
                    link.setStyleSheet("font-size: 11px;")
                    link.clicked.connect(lambda _checked=False, target=node_id: self.select_request.emit([target]))
                    crumbs.addWidget(link)
                    crumbs.addWidget(label("›", "Faint"))
                crumbs.addWidget(label(path[-1], "Faint"))
                crumbs.addStretch(1)
                self.header_layout.addLayout(crumbs)

    def _ancestor_ids(self, node_id):
        found = []
        current_id = node_id
        while True:
            located = locate(self.doc, current_id)
            if located is None:
                break
            parent = located[0]
            if parent.__class__.__name__ == "LayoutItem":
                located = locate(self.doc, parent.id)
                if located is None:
                    break
                parent = located[0]
            if not hasattr(parent, "id"):
                break
            found.append(parent.id)
            current_id = parent.id
            if parent is self.doc.root:
                break
        found.reverse()
        return found

    def _header_multi(self, nodes):
        row = QHBoxLayout()
        title = label(f"{len(nodes)} selected", "Title")
        row.addWidget(title)
        row.addStretch(1)
        self.header_layout.addLayout(row)
        names = ", ".join(_node_name(node) for node in nodes[:4]) + ("…" if len(nodes) > 4 else "")
        self.header_layout.addWidget(label(names, "Faint", wrap=True))

    # ------------------------------------------------------------------ rows
    def _grid(self, section: Section) -> QGridLayout:
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)
        grid.setColumnMinimumWidth(0, 84)
        grid.setColumnStretch(1, 1)
        section.add_layout(grid)
        return grid

    def _row(self, grid: QGridLayout, text: str, editor: QWidget, is_set: bool = False, reset=None, scrub=None):
        row = grid.rowCount()
        caption = scrub or label(text, "Small")
        if is_set:
            caption.setStyleSheet(f"color: {current().text}; font-weight: 600;")
            caption.setToolTip("Set in this file. Reset removes the line.")
        grid.addWidget(caption, row, 0, Qt.AlignVCenter)
        grid.addWidget(editor, row, 1)
        if reset is not None and is_set:
            button = IconButton("close", "Reset: remove this property from the file")
            button.setFixedSize(22, 22)
            button.setIconSize(QSize(12, 12))
            button.clicked.connect(reset)
            grid.addWidget(button, row, 2)
        else:
            spacer = QWidget()
            spacer.setFixedSize(22, 22)
            grid.addWidget(spacer, row, 2)

    def _realized(self, node_id):
        if self.canvas is None:
            return None
        return self.canvas.primary.realization.widgets.get(node_id)

    def _execute(self, command):
        if command is not None:
            self.history.execute(command)

    # ------------------------------------------------------------------ widget
    def _widget(self, page, node: Widget):
        content = Section("Content", "content")
        grid = self._grid(content)
        names = list(CURATED.get(node.class_name, CURATED.get(_base_class(self.doc, node.class_name), [])))
        for prop_name in names + [name for name in COMMON if name not in names]:
            self._property_row(grid, node, prop_name)
        if node.class_name == "QLabel":
            self._buddy_row(grid, node)
        page.addWidget(content)
        if node.class_name == "QComboBox":
            page.addWidget(self._items_section(node))
        if node.class_name in ("QTabWidget", "QStackedWidget", "QToolBox"):
            page.addWidget(self._pages_section(node))
        if self._in_layout(node):
            page.addWidget(self._size_section(node))
        layout = widget_layout(node)
        if layout is not None:
            self._layout_section(page, layout, owner=node)
        page.addWidget(self._all_section(node))

    def _in_layout(self, node) -> bool:
        return resolve_layout_item(self.doc, node.id) is not None

    def _meta(self, node, prop_name):
        widget = self._realized(node.id)
        if widget is None:
            return None, None
        meta = widget.metaObject()
        index = meta.indexOfProperty(prop_name)
        if index < 0:
            return widget, None
        return widget, meta.property(index)

    def _property_row(self, grid, node, prop_name):
        widget, meta = self._meta(node, prop_name)
        current_prop = get_property(node, prop_name)
        if meta is None and current_prop is None:
            return
        editor = self._editor(node, prop_name, widget, meta, current_prop)
        if editor is None:
            return
        editor.setProperty("inspectorKey", f"prop:{prop_name}")
        reset = lambda _checked=False, name=prop_name: self._execute(SetProperty(node.id, name, None))  # noqa: E731
        self._row(grid, WORD_LABELS.get(prop_name, prop_name), editor, current_prop is not None, reset)

    def _editor(self, node, prop_name, widget, meta, current_prop):
        editor = self._make_editor(node, prop_name, widget, meta, current_prop)
        if editor is not None:
            _tame(editor)
        return editor

    def _make_editor(self, node, prop_name, widget, meta, current_prop):
        value = widget.property(prop_name) if widget is not None else None
        if meta is not None and (meta.isEnumType() or meta.isFlagType()):
            enum = meta.enumerator()
            if meta.isFlagType() or enum.isFlag():
                return self._flags_editor(node, prop_name, enum, value)
            combo = QComboBox()
            keys = [enum.key(i) for i in range(enum.keyCount())]
            combo.addItems(keys)
            key = getattr(value, "name", None)
            if key is None:
                try:
                    key = enum.valueToKey(int(value))
                except (TypeError, ValueError):
                    key = None
            if key in keys:
                combo.setCurrentText(key)
            scope = enum.scope() or widget.metaObject().className()
            combo.currentTextChanged.connect(
                lambda text, name=prop_name, scope=scope: self._execute(SetProperty(node.id, name, prop_enum(name, f"{scope}::{text}")))
            )
            return combo
        kind = current_prop.body.tag if current_prop is not None else None
        type_name = meta.typeName() if meta is not None else ""
        if kind == "bool" or type_name == "bool" or isinstance(value, bool):
            box = QCheckBox()
            box.setChecked(bool(value) if current_prop is None else current_prop.body.text == "true")
            box.toggled.connect(lambda checked, name=prop_name: self._execute(SetProperty(node.id, name, prop_bool(name, checked))))
            return box
        if kind == "number" or type_name == "int":
            number = NumberField(None if current_prop is None else int(float(current_prop.body.text or 0)), placeholder=str(value if value is not None else 0))
            number.committed.connect(lambda result, name=prop_name: self._execute(SetProperty(node.id, name, None if result is None else prop_number(name, result))))
            return number
        if kind == "double" or type_name == "double":
            edit = QLineEdit("" if current_prop is None else current_prop.body.text)
            edit.setPlaceholderText(str(value if value is not None else 0))
            edit.editingFinished.connect(lambda name=prop_name, box=edit: self._commit_double(node, name, box.text()))
            return edit
        if kind in (None, "string", "cstring") and (type_name in ("QString", "") or isinstance(value, str)):
            text = current_prop.body.text if current_prop is not None else ""
            edit = QLineEdit(text)
            if current_prop is None and value:
                edit.setPlaceholderText(str(value))
            edit.editingFinished.connect(lambda name=prop_name, box=edit: self._commit_string(node, name, box.text()))
            return edit
        if current_prop is not None and not current_prop.body.children:
            edit = QLineEdit(current_prop.body.text)
            edit.setReadOnly(True)
            edit.setToolTip("Kept exactly as it is in the file.")
            return edit
        return None

    def _commit_string(self, node, name, text):
        current_prop = get_property(node, name)
        if current_prop is None and text == "":
            return
        if current_prop is not None and current_prop.body.text == text:
            return
        self._execute(SetProperty(node.id, name, prop_string(name, text)))

    def _commit_double(self, node, name, text):
        if text.strip() == "":
            self._execute(SetProperty(node.id, name, None) if get_property(node, name) is not None else None)
            return
        try:
            self._execute(SetProperty(node.id, name, prop_double(name, float(text))))
        except ValueError:
            self.status.emit(f"“{text}” is not a number.")

    def _flags_editor(self, node, prop_name, enum, value):
        button = QToolButton()
        button.setPopupMode(QToolButton.InstantPopup)
        button.setObjectName("TextTool")
        button.setStyleSheet("QToolButton { border: 1px solid %s; border-radius: 6px; padding: 3px 8px; text-align: left; }" % current().border_strong)
        try:
            number = int(getattr(value, "value", value) or 0)
        except (TypeError, ValueError):
            number = 0
        scope = enum.scope()
        keys = [enum.key(i) for i in range(enum.keyCount())]
        values = {key: enum.value(i) for i, key in enumerate(keys)}
        chosen = [key for key in keys if values[key] and (number & values[key]) == values[key] and bin(values[key]).count("1") == 1]
        button.setText(", ".join(_short(key) for key in chosen) or "None")
        menu = QMenu(button)
        for key in keys:
            if bin(values[key]).count("1") != 1:
                continue
            action = menu.addAction(_short(key))
            action.setCheckable(True)
            action.setChecked(key in chosen)
            action.toggled.connect(lambda checked, k=key: self._toggle_flag(node, prop_name, scope, chosen, k, checked))
        button.setMenu(menu)
        return button

    def _toggle_flag(self, node, prop_name, scope, chosen, key, checked):
        keys = [k for k in chosen if k != key] + ([key] if checked else [])
        if not keys:
            self._execute(SetProperty(node.id, prop_name, None))
            return
        self._execute(SetProperty(node.id, prop_name, prop_set(prop_name, "|".join(f"{scope}::{k}" for k in keys))))

    def _buddy_row(self, grid, node):
        combo = QComboBox()
        combo.setProperty("inspectorKey", "buddy")
        combo.addItem("None", "")
        for widget in iter_widgets(self.doc):
            if widget.id != node.id and widget.class_name in INPUT_CLASSES and widget.class_name not in ("QPushButton", "QToolButton"):
                combo.addItem(widget.object_name, widget.object_name)
        buddy = get_property(node, "buddy")
        if buddy is not None:
            index = combo.findData(buddy.body.text)
            if index >= 0:
                combo.setCurrentIndex(index)
        combo.currentIndexChanged.connect(
            lambda _index: self._execute(
                SetProperty(node.id, "buddy", prop_cstring("buddy", combo.currentData()) if combo.currentData() else None)
            )
        )
        reset = lambda _checked=False: self._execute(SetProperty(node.id, "buddy", None))  # noqa: E731
        self._row(grid, "Buddy", combo, buddy is not None, reset)

    def _items_section(self, node):
        section = Section("Items", "items")
        lines = []
        for part in node.body:
            if isinstance(part, ItemEntry):
                text = ""
                for child in part.body:
                    if isinstance(child, Property) and child.name == "text":
                        text = child.body.text
                lines.append(text)
        edit = QLineEdit(", ".join(lines))
        edit.setProperty("inspectorKey", "items")
        edit.setPlaceholderText("One, two, three")
        edit.editingFinished.connect(lambda: self._execute(SetComboItems(node.id, [p.strip() for p in edit.text().split(",") if p.strip()])))
        section.add(edit)
        section.add(label("Separate items with commas.", "Faint"))
        return section

    def _pages_section(self, node):
        from spikes.form_builder.model import make_layout, make_widget, set_attribute, unique_name

        section = Section("Pages", "pages")
        for number, child in enumerate(child_widgets(node)):
            attr = get_attribute(child, "title")
            edit = QLineEdit(attr.body.text if attr else child.object_name)
            edit.setProperty("inspectorKey", f"page:{number}")
            edit.editingFinished.connect(lambda child_id=child.id, box=edit: self._execute(SetAttribute(child_id, "title", box.text())))
            section.add(edit)

        def add_page():
            page = make_widget(self.doc, "QWidget", unique_name(self.doc, "tab" if node.class_name == "QTabWidget" else "page"))
            set_attribute(page, "title", f"Tab {len(child_widgets(node)) + 1}")
            page.body.append(make_layout(self.doc, "QVBoxLayout"))
            self._execute(InsertChild(node.id, 10**6, page))

        add = QPushButton("Add page")
        add.clicked.connect(add_page)
        section.add(add)
        return section

    # ------------------------------------------------------------------ size
    def _size_section(self, node: Widget):
        section = Section("Size", "size")
        default = _class_default(self.doc, node.class_name)
        parent_layout = self._parent_layout(node)
        grid = self._grid(section)
        for axis, word in (("h", "Width"), ("v", "Height")):
            mode, fixed, _explicit = sizing.axis_mode(node, axis, default)
            options = [("hug", "Hug", "", "Hug: stay at the size the content asks for"),
                       ("fill", "Fill", "", "Fill: take the spare room"),
                       ("fixed", "Fixed", "", "Fixed: always this many pixels")]
            control = SegmentedControl(options, mode if mode != "auto" else None, compact=True)
            control.setProperty("inspectorKey", f"size:{axis}")
            control.changed.connect(lambda key, axis=axis: self._set_axis(node, axis, key))
            holder = QWidget()
            holder_layout = QHBoxLayout(holder)
            holder_layout.setContentsMargins(0, 0, 0, 0)
            holder_layout.setSpacing(6)
            holder_layout.addWidget(control)
            if mode == "fixed":
                field = NumberField(fixed, minimum=1, maximum=9999)
                field.setFixedWidth(64)
                field.setProperty("inspectorKey", f"fixed:{axis}")
                field.committed.connect(lambda value, axis=axis: self._set_axis(node, axis, "fixed", value))
                holder_layout.addWidget(field)
            holder_layout.addStretch(1)
            is_set = mode != "auto" and _explicit or mode == "fixed"
            reset = lambda _checked=False, axis=axis: self._execute(sizing.set_axis(node, axis, "auto", default))  # noqa: E731
            self._row(grid, word, holder, is_set, reset)
            if mode == "fill":
                share = NumberField(sizing.share_of(node, axis) or None, placeholder="0", minimum=0, maximum=255)
                share.setFixedWidth(56)
                share.setToolTip("Share of the spare room, compared with siblings that also fill. Up/Down to step, Shift for 10.")
                share.setProperty("inspectorKey", f"share:{axis}")
                share.committed.connect(lambda value, axis=axis: self._execute(sizing.set_share(node, axis, value, default)))
                share_row = QWidget()
                share_layout = QHBoxLayout(share_row)
                share_layout.setContentsMargins(0, 0, 0, 0)
                share_layout.addWidget(share)
                share_layout.addWidget(label("of the spare " + ("width" if axis == "h" else "height"), "Faint"))
                share_layout.addStretch(1)
                scrub = ScrubLabel("  Share", share)
                self._row(grid, "", share_row, False, None, scrub=scrub)
        if all(sizing.axis_mode(node, axis, default)[0] == "auto" for axis in ("h", "v")):
            section.add(label("Neither set: the class default applies. Most controls grow only when nothing else wants the room.", "Faint", wrap=True))
        for name, word in (("minimumSize", "Minimum"), ("maximumSize", "Maximum")):
            size = sizing.read_size(node, name)
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(4)
            limit = 9999 if name == "minimumSize" else sizing.QT_MAX
            show_w = None if size is None or size[0] in (0, sizing.QT_MAX) else size[0]
            show_h = None if size is None or size[1] in (0, sizing.QT_MAX) else size[1]
            width_field = NumberField(show_w, placeholder="any" if name == "maximumSize" else "0", minimum=0, maximum=limit)
            height_field = NumberField(show_h, placeholder="any" if name == "maximumSize" else "0", minimum=0, maximum=limit)
            for field, key in ((width_field, "w"), (height_field, "h")):
                field.setFixedWidth(60)
                field.setProperty("inspectorKey", f"{name}:{key}")
            row_layout.addWidget(width_field)
            row_layout.addWidget(label("×", "Faint"))
            row_layout.addWidget(height_field)
            row_layout.addStretch(1)

            def commit(_value=None, name=name, wf=width_field, hf=height_field):
                default_value = 0 if name == "minimumSize" else sizing.QT_MAX
                w = wf.value() if wf.value() is not None else default_value
                h = hf.value() if hf.value() is not None else default_value
                if (w, h) == (default_value, default_value):
                    self._execute(sizing.reset_size_property(node, name))
                else:
                    self._execute(SetProperty(node.id, name, sizing.size_property(name, w, h)))

            width_field.committed.connect(commit)
            height_field.committed.connect(commit)
            reset = lambda _checked=False, name=name: self._execute(sizing.reset_size_property(node, name))  # noqa: E731
            self._row(grid, word, row_widget, size is not None, reset)
        why = label(self._why(node, default, parent_layout), "Why", wrap=True)
        why.setTextInteractionFlags(Qt.TextSelectableByMouse)
        caption = label("WHY IS IT THIS SIZE?", "Overline")
        section.add(caption)
        section.add(why)
        return section

    def _set_axis(self, node, axis, mode, value=None):
        default = _class_default(self.doc, node.class_name)
        if mode == "fixed" and value is None:
            widget = self._realized(node.id)
            value = (widget.width() if axis == "h" else widget.height()) if widget is not None else 100
        self._execute(sizing.set_axis(node, axis, mode, default, value))

    def _parent_layout(self, node):
        item = resolve_layout_item(self.doc, node.id)
        if item is None:
            return None
        located = locate(self.doc, item.id)
        return located[0] if located is not None and isinstance(located[0], Layout) else None

    def _why(self, node, default, parent_layout) -> str:
        widget = self._realized(node.id)
        if widget is None:
            return "The sentence appears once the canvas has built this widget."
        hint = widget.sizeHint()
        policy = widget.sizePolicy()
        h_mode, fixed_w, _ = sizing.axis_mode(node, "h", default)
        v_mode, fixed_h, _ = sizing.axis_mode(node, "v", default)
        parent = ""
        if parent_layout is not None:
            words = {"QVBoxLayout": "vertical layout", "QHBoxLayout": "horizontal layout", "QGridLayout": "grid", "QFormLayout": "form layout"}
            parent = f"the {words.get(parent_layout.class_name, 'layout')} {parent_layout.object_name}"
        facts = {
            "class_label": node.class_name.split("::")[-1].lstrip("Q").lower().replace("lineedit", "line edit").replace("pushbutton", "button"),
            "width": widget.width(),
            "height": widget.height(),
            "hint_w": hint.width(),
            "hint_h": hint.height(),
            "h_mode": h_mode,
            "v_mode": v_mode,
            "h_policy": policy.horizontalPolicy().name,
            "v_policy": policy.verticalPolicy().name,
            "min_w": widget.minimumWidth(),
            "min_h": widget.minimumHeight(),
            "max_w": widget.maximumWidth(),
            "max_h": widget.maximumHeight(),
            "parent": parent,
            "share_h": policy.horizontalStretch(),
            "share_v": policy.verticalStretch(),
            "fixed_w": fixed_w,
            "fixed_h": fixed_h,
        }
        if v_mode == "auto" and policy.verticalPolicy().name in sizing.HUG:
            facts["v_mode"] = "hug"
        if h_mode == "auto" and policy.horizontalPolicy().name in sizing.HUG:
            facts["h_mode"] = "hug"
        if h_mode == "auto" and policy.horizontalPolicy().name in sizing.FILL:
            facts["h_mode"] = "fill"
        if v_mode == "auto" and policy.verticalPolicy().name in sizing.FILL:
            facts["v_mode"] = "fill"
        return sizing.why_sentence(facts)

    # ------------------------------------------------------------------ layout
    def _layout_section(self, page, layout: Layout, owner):
        from spikes.form_builder.commands import morph_layout

        section = Section("Layout", "layout")
        kinds = SegmentedControl([(key, "", glyph, tip) for key, _t, glyph, tip in LAYOUT_KINDS], layout.class_name, compact=True)
        kinds.setToolTip("Change the layout kind. Children keep their order.")
        kinds.changed.connect(lambda key: self._execute(morph_layout(self.doc, layout.id, key)))
        grid = self._grid(section)
        self._row(grid, "Kind", kinds)
        qlayout = self.canvas.primary.realization.layouts.get(layout.id) if self.canvas else None
        spacing_props = ("spacing",) if layout.class_name in ("QVBoxLayout", "QHBoxLayout") else ("horizontalSpacing", "verticalSpacing")
        for prop_name in spacing_props:
            prop = get_property(layout, prop_name)
            live = None
            if qlayout is not None:
                getter = getattr(qlayout, prop_name, None)
                live = getter() if callable(getter) else None
            field = NumberField(None if prop is None else int(float(prop.body.text or 0)), placeholder=f"{live if live is not None and live >= 0 else 6}", minimum=0, maximum=200)
            field.setFixedWidth(64)
            field.setProperty("inspectorKey", f"layout:{prop_name}")
            field.committed.connect(lambda value, name=prop_name: self._execute(SetProperty(layout.id, name, None if value is None else prop_number(name, value))))
            caption = {"spacing": "Gap", "horizontalSpacing": "Column gap", "verticalSpacing": "Row gap"}[prop_name]
            scrub = ScrubLabel(caption, field)
            reset = lambda _checked=False, name=prop_name: self._execute(SetProperty(layout.id, name, None))  # noqa: E731
            holder = QWidget()
            holder_layout = QHBoxLayout(holder)
            holder_layout.setContentsMargins(0, 0, 0, 0)
            holder_layout.addWidget(field)
            holder_layout.addStretch(1)
            holder.setToolTip("Drag the label sideways, use Up/Down, or drag the pink bar on the canvas.")
            self._row(grid, caption, holder, prop is not None, reset, scrub=scrub)
        margins = QWidget()
        margins_layout = QHBoxLayout(margins)
        margins_layout.setContentsMargins(0, 0, 0, 0)
        margins_layout.setSpacing(4)
        live_margins = qlayout.contentsMargins() if qlayout is not None else None
        any_set = False
        for name, short, live in (("leftMargin", "L", live_margins.left() if live_margins else 9), ("topMargin", "T", live_margins.top() if live_margins else 9),
                                  ("rightMargin", "R", live_margins.right() if live_margins else 9), ("bottomMargin", "B", live_margins.bottom() if live_margins else 9)):
            prop = get_property(layout, name)
            any_set = any_set or prop is not None
            field = NumberField(None if prop is None else int(float(prop.body.text or 0)), placeholder=str(live), minimum=0, maximum=200)
            field.setFixedWidth(40)
            field.setToolTip({"L": "Left", "T": "Top", "R": "Right", "B": "Bottom"}[short] + " margin")
            field.setProperty("inspectorKey", f"layout:{name}")
            field.committed.connect(lambda value, name=name: self._execute(SetProperty(layout.id, name, None if value is None else prop_number(name, value))))
            margins_layout.addWidget(field)
        margins_layout.addStretch(1)

        def reset_margins(_checked=False):
            steps = [SetProperty(layout.id, name, None) for name in ("leftMargin", "topMargin", "rightMargin", "bottomMargin") if get_property(layout, name) is not None]
            self._execute(Compound(steps) if steps else None)

        self._row(grid, "Margins", margins, any_set, reset_margins)
        if layout.class_name == "QGridLayout":
            section.add(self._grid_tracks(layout, qlayout))
        if layout.class_name == "QFormLayout":
            self._property_row_layout(grid, layout, "fieldGrowthPolicy", qlayout)
            self._property_row_layout(grid, layout, "labelAlignment", qlayout)
        if owner is not None:
            remove = QPushButton("Remove layout…")
            remove.setObjectName("Ghost")
            remove.setToolTip("Children stay, but stop following the window. Asks first.")
            remove.clicked.connect(lambda: self.remove_layout.emit(owner.id))
            section.add(remove)
        page.addWidget(section)

    def _property_row_layout(self, grid, layout, prop_name, qlayout):
        if qlayout is None:
            return
        meta = qlayout.metaObject()
        index = meta.indexOfProperty(prop_name)
        if index < 0:
            return
        prop = meta.property(index)
        enum = prop.enumerator()
        current_prop = get_property(layout, prop_name)
        if prop.isFlagType():
            editor = self._flags_editor(layout, prop_name, enum, qlayout.property(prop_name))
        else:
            editor = QComboBox()
            keys = [enum.key(i) for i in range(enum.keyCount())]
            editor.addItems(keys)
            value = qlayout.property(prop_name)
            key = getattr(value, "name", None)
            if key in keys:
                editor.setCurrentText(key)
            scope = enum.scope()
            editor.currentTextChanged.connect(lambda text: self._execute(SetProperty(layout.id, prop_name, prop_enum(prop_name, f"{scope}::{text}"))))
        reset = lambda _checked=False: self._execute(SetProperty(layout.id, prop_name, None))  # noqa: E731
        words = {"fieldGrowthPolicy": "Fields grow", "labelAlignment": "Labels"}
        self._row(grid, words[prop_name], editor, current_prop is not None, reset)

    def _grid_tracks(self, layout, qlayout):
        """Column and row sizes as numbers, the way people asked for them."""
        box = QWidget()
        grid = QGridLayout(box)
        grid.setContentsMargins(0, 6, 0, 0)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(4)
        columns = qlayout.columnCount() if qlayout is not None else 0
        rows = qlayout.rowCount() if qlayout is not None else 0
        grid.addWidget(label("", "Faint"), 0, 0)
        grid.addWidget(label("share", "Faint"), 0, 1)
        grid.addWidget(label("min px", "Faint"), 0, 2)
        line = 1
        for axis, count, stretch_key, min_key in (("Column", columns, "columnstretch", "columnminimumwidth"), ("Row", rows, "rowstretch", "rowminimumheight")):
            stretches = _csv(layout.attrib.get(stretch_key, ""))
            minimums = _csv(layout.attrib.get(min_key, ""))
            for position in range(count):
                grid.addWidget(label(f"{axis} {position + 1}", "Small"), line, 0)
                for column, key, values in ((1, stretch_key, stretches), (2, min_key, minimums)):
                    value = values[position] if position < len(values) and values[position] else None
                    field = NumberField(value, placeholder="0", minimum=0, maximum=9999)
                    field.setFixedWidth(56)
                    field.setProperty("inspectorKey", f"track:{key}:{position}")
                    field.committed.connect(lambda result, key=key, position=position, count=count: self._set_track(layout, key, position, result, count))
                    grid.addWidget(field, line, column)
                line += 1
        grid.setColumnStretch(3, 1)
        return box

    def _set_track(self, layout, key, position, value, count):
        values = _csv(layout.attrib.get(key, ""))
        while len(values) < count:
            values.append(0)
        values[position] = value or 0
        text = ",".join(str(v) for v in values) if any(values) else None
        self._execute(SetLayoutAttrib(layout.id, key, text))

    # ------------------------------------------------------------------ others
    def _spacer(self, page, node: Spacer):
        section = Section("Spacer", "spacer")
        grid = self._grid(section)
        orientation = get_property(node, "orientation")
        vertical = orientation is not None and "Vertical" in orientation.body.text
        control = SegmentedControl([("Qt::Horizontal", "Horizontal", "", ""), ("Qt::Vertical", "Vertical", "", "")], "Qt::Vertical" if vertical else "Qt::Horizontal", compact=True)
        control.changed.connect(lambda key: self._execute(SetProperty(node.id, "orientation", prop_enum("orientation", key))))
        self._row(grid, "Direction", control)
        hint = sizing.read_size(node, "sizeHint") or (40, 20)
        size_type = get_property(node, "sizeType")
        kind = SegmentedControl([("QSizePolicy::Expanding", "Grows", "", ""), ("QSizePolicy::Fixed", "Fixed", "", "")],
                                "QSizePolicy::Fixed" if size_type is not None and "Fixed" in size_type.body.text else "QSizePolicy::Expanding", compact=True)
        kind.changed.connect(lambda key: self._execute(SetProperty(node.id, "sizeType", prop_enum("sizeType", key)) if key != "QSizePolicy::Expanding" else SetProperty(node.id, "sizeType", None)))
        self._row(grid, "Behaves", kind)
        length = NumberField(hint[1] if vertical else hint[0], minimum=0, maximum=9999)
        length.setFixedWidth(64)

        def commit(value):
            prop = sizing.size_property("sizeHint", hint[0] if vertical else (value or 0), (value or 0) if vertical else hint[1])
            prop.attrib["stdset"] = "0"
            self._execute(SetProperty(node.id, "sizeHint", prop))

        length.committed.connect(commit)
        self._row(grid, "Length", length)
        section.add(label("A gap you can see is easier: select the layout and drag its pink bars.", "Faint", wrap=True))
        page.addWidget(section)

    def _action(self, page, node: Action):
        section = Section("Action", "action")
        grid = self._grid(section)
        for prop_name, word in (("text", "Text"), ("shortcut", "Shortcut"), ("toolTip", "Tooltip"), ("statusTip", "Status tip")):
            prop = get_property(node, prop_name)
            edit = QLineEdit(prop.body.text if prop is not None else "")
            edit.setProperty("inspectorKey", f"action:{prop_name}")
            if prop_name == "shortcut":
                edit.setPlaceholderText("Ctrl+O")
            edit.editingFinished.connect(lambda name=prop_name, box=edit: self._commit_string(node, name, box.text()))
            reset = lambda _checked=False, name=prop_name: self._execute(SetProperty(node.id, name, None))  # noqa: E731
            self._row(grid, word, edit, prop is not None, reset)
        used = [widget.object_name for widget in iter_widgets(self.doc) if any(isinstance(part, ActionRef) and part.name == node.name for part in widget.body)]
        section.add(label("Used in " + ", ".join(used) if used else "Not in any menu or toolbar yet.", "Faint", wrap=True))
        page.addWidget(section)

    def _multi(self, page, widgets):
        section = Section("Shared", "shared")
        grid = self._grid(section)
        if not widgets:
            section.add(label("Select widgets to edit them together.", "Faint"))
            page.addWidget(section)
            return
        shared = set(CURATED.get(widgets[0].class_name, [])) | set(COMMON)
        for widget in widgets[1:]:
            shared &= set(CURATED.get(widget.class_name, [])) | set(COMMON)
        for prop_name in sorted(shared):
            values = {get_property(widget, prop_name).body.text if get_property(widget, prop_name) else "" for widget in widgets}
            edit = QLineEdit(values.pop() if len(values) == 1 else "")
            edit.setPlaceholderText("Mixed" if len(values) > 0 else "")
            edit.setProperty("inspectorKey", f"multi:{prop_name}")
            edit.editingFinished.connect(lambda name=prop_name, box=edit: self._set_many(widgets, name, box.text()))
            self._row(grid, WORD_LABELS.get(prop_name, prop_name), edit)
        page.addWidget(section)
        size = Section("Size", "multi-size")
        size_grid = self._grid(size)
        for axis, word in (("h", "Width"), ("v", "Height")):
            control = SegmentedControl([("hug", "Hug", "", ""), ("fill", "Fill", "", "")], None, compact=True)
            control.changed.connect(lambda key, axis=axis: self._multi_axis(widgets, axis, key))
            self._row(size_grid, word, control)
        page.addWidget(size)

    def _multi_axis(self, widgets, axis, mode):
        steps = []
        for widget in widgets:
            command = sizing.set_axis(widget, axis, mode, _class_default(self.doc, widget.class_name))
            if command is not None:
                steps.append(command)
        self._execute(Compound(steps) if steps else None)

    def _set_many(self, widgets, prop_name, text):
        if text == "":
            return
        kind = "bool" if prop_name in ("enabled", "checked", "readOnly", "checkable") else "string"
        prop = prop_bool(prop_name, text.lower() in ("1", "true", "yes", "on")) if kind == "bool" else prop_string(prop_name, text)
        self._execute(SetProperties([widget.id for widget in widgets], prop_name, prop))

    # ------------------------------------------------------------------ form
    def _form(self, page, root: Widget):
        window = Section("Window", "window")
        grid = self._grid(window)
        self._property_row(grid, root, "windowTitle")
        geometry = get_property(root, "geometry")
        width, height = 640, 480
        if geometry is not None and geometry.body.tag == "rect":
            values = {child.tag: child.text for child in geometry.body.children}
            width, height = int(values.get("width", 640)), int(values.get("height", 480))
        size_widget = QWidget()
        size_layout = QHBoxLayout(size_widget)
        size_layout.setContentsMargins(0, 0, 0, 0)
        width_field = NumberField(width, minimum=60, maximum=4000)
        height_field = NumberField(height, minimum=40, maximum=4000)
        for field, key in ((width_field, "w"), (height_field, "h")):
            field.setFixedWidth(64)
            field.setProperty("inspectorKey", f"form:{key}")
        size_layout.addWidget(width_field)
        size_layout.addWidget(label("×", "Faint"))
        size_layout.addWidget(height_field)
        size_layout.addStretch(1)

        def commit(_value=None):
            from spikes.form_builder.model import prop_rect

            self._execute(SetProperty(root.id, "geometry", prop_rect("geometry", 0, 0, width_field.value() or width, height_field.value() or height)))

        width_field.committed.connect(commit)
        height_field.committed.connect(commit)
        self._row(grid, "Size", size_widget)
        window.add(label("Drag the page's right or bottom edge to try other sizes. Everything in a layout follows.", "Faint", wrap=True))
        page.addWidget(window)
        layout = widget_layout(root)
        if layout is not None:
            self._layout_section(page, layout, owner=root)
        page.addWidget(self._tab_order_section())
        page.addWidget(self._problems_section())
        page.addWidget(self._files_section())

    def _tab_order_section(self):
        stops = tabstops_of(self.doc)
        custom = bool(stops and stops.names)
        order = effective_tab_order(self.doc)
        reset = QPushButton("Use reading order")
        reset.setObjectName("Ghost")
        reset.setEnabled(custom)
        reset.clicked.connect(lambda: self._execute(SetTabStops(None)))
        section = Section("Tab order", "tab-order", trailing=reset)
        listing = QListWidget()
        listing.setDragDropMode(QAbstractItemView.InternalMove)
        listing.setFixedHeight(min(26 * max(len(order), 1) + 8, 220))
        listing.setUniformItemSizes(True)
        for number, name in enumerate(order, start=1):
            item = QListWidgetItem(f"{number}   {name}")
            item.setData(Qt.UserRole, name)
            listing.addItem(item)

        def reordered(*_args):
            names = [listing.item(i).data(Qt.UserRole) for i in range(listing.count())]
            if names != order:
                self._execute(SetTabStops(names))

        listing.model().rowsMoved.connect(reordered)
        if order:
            section.add(listing)
        else:
            listing.deleteLater()
            section.add(label("No fields yet. Inputs join the order as you add them.", "Small", wrap=True))
        words = "Custom order. New fields join it where they sit on the form." if custom else "Follows reading order: top to bottom, left to right."
        section.add(label(words + " Drag to reorder, or use Tab order in the top bar.", "Faint", wrap=True))
        pair = QPushButton("Pair labels with their fields")
        pair.setObjectName("Ghost")
        pair.setToolTip("Sets each label's buddy to the field in its row, so Alt+letter jumps to the field.")
        pair.clicked.connect(self._pair)
        section.add(pair)
        return section

    def _pair(self):
        steps = pair_buddies(self.doc)
        if steps:
            self._execute(Compound(steps))
            self.status.emit(f"Paired {len(steps)} labels with their fields.")
        else:
            self.status.emit("Every label in a row already has its field.")

    def _problems_section(self):
        found = problems(self.doc)
        section = Section(f"Problems  {len(found)}" if found else "Problems", "problems")
        if not found:
            ok = QHBoxLayout()
            mark = QLabel()
            mark.setPixmap(pixmap("check-mark", current().ok, 14))
            ok.addWidget(mark)
            ok.addWidget(label("No problems. Save writes a clean .ui and ui_ module.", "Small"))
            ok.addStretch(1)
            section.add_layout(ok)
        for text in found:
            row = QHBoxLayout()
            mark = QLabel()
            mark.setPixmap(pixmap("warning", current().warn, 14))
            row.addWidget(mark, 0, Qt.AlignTop)
            row.addWidget(label(text, "Small", wrap=True), 1)
            section.add_layout(row)
        return section

    def _files_section(self):
        section = Section("Files", "files")
        if not self.path:
            section.add(label("Not saved yet. Save writes name.ui and ui_name.py side by side.", "Faint", wrap=True))
            return section
        path = Path(self.path)
        rows = [
            ("file", path.name, "the form; open it again any time"),
            ("file", f"ui_{path.stem}.py", "generated on every save; do not edit"),
            ("file", f"{path.stem}_window.py", "your code; created once, never overwritten"),
        ]
        for glyph, name, detail in rows:
            line = QHBoxLayout()
            mark = QLabel()
            mark.setPixmap(pixmap(glyph, current().muted, 14))
            line.addWidget(mark)
            line.addWidget(label(name, "Small"))
            line.addWidget(label(detail, "Faint"), 1)
            section.add_layout(line)
        return section

    # ------------------------------------------------------------------ all properties
    def _all_section(self, node: Widget):
        section = Section("All properties", "all")
        widget = self._realized(node.id)
        if widget is None:
            section.add(label("Available once the canvas has built this widget.", "Faint"))
            return section
        search = QLineEdit()
        search.setObjectName("Search")
        search.setPlaceholderText("Find a property")
        search.setProperty("inspectorKey", "all:search")
        section.add(search)
        holder = QWidget()
        grid = QGridLayout(holder)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(4)
        grid.setColumnStretch(1, 1)
        section.add(holder)
        rows = []
        meta = widget.metaObject()
        skip = {"objectName", "geometry", "pos", "size", "x", "y", "width", "height", "rect", "sizePolicy", "minimumSize", "maximumSize",
                "minimumWidth", "minimumHeight", "maximumWidth", "maximumHeight", "frameGeometry", "normalGeometry", "childrenRect",
                "childrenRegion", "frameSize", "visible", "focus", "isActiveWindow", "fullScreen", "maximized", "minimized", "modal",
                "underMouse", "updatesEnabled", "windowModified", "windowFilePath", "windowIconText", "windowOpacity", "inputMethodHints",
                "sizeIncrement", "baseSize", "minimized", "acceptDrops"}
        built = {"done": False}

        def build():
            if built["done"]:
                return
            built["done"] = True
            set_names = {prop.name for prop in node.body if isinstance(prop, Property)}
            for position in range(meta.propertyCount()):
                prop = meta.property(position)
                name = prop.name()
                if not prop.isWritable() or not prop.isDesignable() or name in skip:
                    continue
                editor = self._editor(node, name, widget, prop, get_property(node, name))
                if editor is None:
                    continue
                editor.setProperty("inspectorKey", f"all:{name}")
                caption = label(name, "Small")
                if name in set_names:
                    caption.setStyleSheet(f"color: {current().text}; font-weight: 600;")
                line = grid.rowCount()
                grid.addWidget(caption, line, 0)
                grid.addWidget(editor, line, 1)
                rows.append((name.lower(), caption, editor))

        def filter_rows(text):
            build()
            for name, caption, editor in rows:
                visible = text.lower() in name
                caption.setVisible(visible)
                editor.setVisible(visible)

        search.textChanged.connect(filter_rows)
        if not Section._collapsed.get("all", False):
            QTimer.singleShot(0, build)
        section.header_clicked = build
        return section

    # ------------------------------------------------------------------ behavior
    def _behavior(self, page, node: Widget) -> int:
        links = connections_of(self.doc)
        rows = []
        if links is not None:
            for position, link in enumerate(links.items):
                if node is self.doc.root or link.sender == node.object_name or link.receiver == node.object_name:
                    rows.append((position, link))
        section = Section("Connections", "connections")
        intro = "When this widget emits a signal, call a slot on another widget or the form." if node is not self.doc.root else "Every signal-to-slot connection on this form."
        section.add(label(intro, "Faint", wrap=True))
        for position, link in rows:
            line = QHBoxLayout()
            line.setSpacing(6)
            text = label(f"{link.sender}.{link.signal.split('(')[0]}  →  {link.receiver}.{link.slot.split('(')[0]}", "Small", wrap=True)
            text.setToolTip(f"{link.sender}.{link.signal} → {link.receiver}.{link.slot}")
            line.addWidget(text, 1)
            remove = IconButton("close", "Remove this connection")
            remove.setFixedSize(22, 22)
            remove.clicked.connect(lambda _checked=False, index=position: self._execute(RemoveConnection(index)))
            line.addWidget(remove)
            section.add_layout(line)
        if node is not self.doc.root:
            section.add(self._connection_builder(node))
        page.addWidget(section)
        later = Section("Rules and events", "logic")
        later.add(
            EmptyState(
                "Action",
                "Coming in the logic phase",
                "State (enabled when…), Checks (required, between…) and Events (when clicked → steps) will live here, "
                "next to the connections above.",
            )
        )
        page.addWidget(later)
        return len(rows)

    def _connection_builder(self, node: Widget):
        box = QWidget()
        grid = QGridLayout(box)
        grid.setContentsMargins(0, 6, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)
        grid.setColumnStretch(1, 1)
        widget = self._realized(node.id)
        signal = QComboBox()
        signal.setProperty("inspectorKey", "conn:signal")
        common = ["clicked()", "toggled(bool)", "textChanged(QString)", "editingFinished()", "valueChanged(int)", "currentIndexChanged(int)", "accepted()", "rejected()"]
        names = _signals(widget)
        ordered = [name for name in common if name in names] + [name for name in names if name not in common]
        signal.addItems(ordered)
        receiver = QComboBox()
        receiver.setProperty("inspectorKey", "conn:receiver")
        receiver.addItem(self.doc.root.object_name)
        for other in iter_widgets(self.doc):
            if other is not self.doc.root:
                receiver.addItem(other.object_name)
        slot = QComboBox()
        slot.setProperty("inspectorKey", "conn:slot")

        def refill_slots():
            slot.clear()
            target_name = receiver.currentText()
            target_node = next((w for w in iter_widgets(self.doc) if w.object_name == target_name), None)
            target = self._realized(target_node.id) if target_node is not None else None
            wanted = signal.currentText()
            slot.addItems(_slots(target, wanted))

        receiver.currentTextChanged.connect(lambda _text: refill_slots())
        signal.currentTextChanged.connect(lambda _text: refill_slots())
        refill_slots()
        add = QPushButton("Add connection")
        add.setObjectName("Primary")

        def commit():
            if not signal.currentText() or not slot.currentText():
                self.status.emit("Pick a signal and a slot first.")
                return
            self._execute(AddConnection(Connection(node.object_name, signal.currentText(), receiver.currentText(), slot.currentText())))
            self.status.emit("Connection added.")

        add.clicked.connect(commit)
        grid.addWidget(label("When", "Small"), 0, 0)
        grid.addWidget(signal, 0, 1)
        grid.addWidget(label("Call", "Small"), 1, 0)
        grid.addWidget(receiver, 1, 1)
        grid.addWidget(label("Slot", "Small"), 2, 0)
        grid.addWidget(slot, 2, 1)
        grid.addWidget(add, 3, 1, Qt.AlignLeft)
        return box

    # ------------------------------------------------------------------ data
    def _data(self, page):
        button = QPushButton("Connect this form to a table…")
        button.setEnabled(False)
        page.addWidget(
            EmptyState(
                "database",
                "No data source yet",
                "In the logic phase this tab binds fields to columns, fills lookups and adds record navigation. "
                "Today, “Build from a table” on the start screen lays out a form from a table's columns.",
                button,
            )
        )


def _tame(widget):
    """Editors never set the inspector's minimum width."""
    if isinstance(widget, QComboBox):
        widget.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        widget.setMinimumContentsLength(6)
    elif isinstance(widget, QToolButton):
        widget.setMinimumWidth(60)
        widget.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
    elif isinstance(widget, QLineEdit) and widget.minimumWidth() == 0:
        widget.setMinimumWidth(40)


def _connection_count(doc, node) -> int:
    links = connections_of(doc)
    if links is None:
        return 0
    if node is doc.root:
        return len(links.items)
    return sum(1 for link in links.items if node.object_name in (link.sender, link.receiver))


def _node_name(node) -> str:
    if isinstance(node, (Widget, Layout)):
        return node.object_name
    return getattr(node, "name", "")


def _short(key: str) -> str:
    for prefix in ("Align", "Qt"):
        if key.startswith(prefix) and len(key) > len(prefix):
            return key[len(prefix):]
    return key


def _csv(text: str) -> list[int]:
    values = []
    for piece in (text or "").split(","):
        piece = piece.strip()
        if piece:
            try:
                values.append(int(piece))
            except ValueError:
                values.append(0)
    return values


def _class_default(doc, class_name):
    from spikes.form_builder.canvas import class_default

    return class_default(doc, class_name)


def _base_class(doc, class_name):
    from spikes.form_builder.realize import custom_base

    if "::" in class_name or not class_name.startswith("Q"):
        return custom_base(doc, class_name)
    return class_name


def _signals(widget) -> list[str]:
    if widget is None:
        return []
    meta = widget.metaObject()
    found = []
    for index in range(meta.methodCount()):
        method = meta.method(index)
        if method.methodType() == method.MethodType.Signal:
            text = bytes(method.methodSignature()).decode()
            if not text.startswith(("destroyed", "objectNameChanged", "windowIcon", "windowTitle", "customContextMenu", "_q_")):
                found.append(text)
    return sorted(set(found), key=lambda name: (name.count(","), name))


def _slots(widget, signal: str) -> list[str]:
    if widget is None:
        return []
    args = signal[signal.find("(") + 1 : signal.rfind(")")] if "(" in signal else ""
    signal_args = [arg.strip() for arg in args.split(",") if arg.strip()]
    meta = widget.metaObject()
    found = []
    for index in range(meta.methodCount()):
        method = meta.method(index)
        if method.methodType() not in (method.MethodType.Slot,):
            continue
        text = bytes(method.methodSignature()).decode()
        if text.startswith("_q_") or text.startswith("deleteLater"):
            continue
        slot_args = [arg.strip() for arg in text[text.find("(") + 1 : text.rfind(")")].split(",") if arg.strip()]
        if signal_args[: len(slot_args)] == slot_args:
            found.append(text)
    preferred = ["close()", "accept()", "reject()", "setEnabled(bool)", "setVisible(bool)", "clear()", "setFocus()", "show()", "hide()"]
    return [name for name in preferred if name in found] + sorted(name for name in set(found) if name not in preferred)
