"""Property inspector. Common fields, sizing in plain words, and the long tail."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from spikes.form_builder.commands import (
    AddConnection,
    InsertChild,
    RemoveConnection,
    SetAttribute,
    SetComboItems,
    SetProperties,
    SetProperty,
)
from spikes.form_builder.model import (
    Connection,
    ItemEntry,
    Layout,
    Property,
    Widget,
    XmlNode,
    connections_of,
    find_node,
    get_attribute,
    get_property,
    iter_widgets,
    prop_bool,
    prop_double,
    prop_enum,
    prop_number,
    prop_string,
    properties_of,
    set_property,
    valid_identifier,
    widget_layout,
)

CURATED = {
    "QLabel": ["text", "alignment", "toolTip"],
    "QPushButton": ["text", "toolTip", "enabled"],
    "QToolButton": ["text", "toolTip", "enabled"],
    "QCheckBox": ["text", "checked", "enabled", "toolTip"],
    "QRadioButton": ["text", "checked", "enabled"],
    "QLineEdit": ["text", "placeholderText", "readOnly", "enabled", "toolTip"],
    "QPlainTextEdit": ["plainText", "placeholderText", "readOnly", "enabled", "toolTip"],
    "QTextEdit": ["html", "toolTip", "enabled"],
    "QSpinBox": ["value", "minimum", "maximum", "singleStep", "prefix", "suffix", "enabled"],
    "QDoubleSpinBox": ["value", "minimum", "maximum", "singleStep", "decimals", "prefix", "suffix", "enabled"],
    "QComboBox": ["editable", "enabled", "toolTip"],
    "QDateEdit": ["enabled", "toolTip"],
    "QDateTimeEdit": ["enabled", "toolTip"],
    "QTimeEdit": ["enabled", "toolTip"],
    "QSlider": ["minimum", "maximum", "value", "orientation", "enabled"],
    "QGroupBox": ["title", "checkable", "checked", "enabled"],
    "QTabWidget": ["currentIndex", "enabled"],
    "QDialogButtonBox": ["standardButtons", "enabled"],
}

SIZING = {
    "Fit content": ("Preferred", "Preferred"),
    "Fill": ("Expanding", "Expanding"),
    "Fixed": ("Fixed", "Fixed"),
}


class Inspector(QScrollArea):
    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        self.body = QWidget()
        self.body.setObjectName("panel")
        self.layout = QVBoxLayout(self.body)
        self.layout.setContentsMargins(12, 12, 12, 12)
        self.layout.setSpacing(8)
        self.setWidget(self.body)
        self.doc = None
        self.history = None
        self.canvas = None
        self.selection = []

    def set_session(self, doc, history, canvas):
        self.doc = doc
        self.history = history
        self.canvas = canvas

    def show_selection(self, ids):
        self.selection = list(ids)
        self._rebuild()

    def _rebuild(self):
        while self.layout.count():
            item = self.layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        if self.doc is None or not self.selection:
            empty = QLabel("Select a widget to edit it.")
            empty.setObjectName("muted")
            empty.setWordWrap(True)
            self.layout.addWidget(empty)
            self.layout.addStretch(1)
            return
        nodes = [find_node(self.doc, node_id) for node_id in self.selection]
        nodes = [node for node in nodes if node is not None]
        widgets = [node for node in nodes if isinstance(node, Widget)]
        if len(widgets) > 1:
            self._multi(widgets)
            self.layout.addStretch(1)
            return
        node = nodes[0]
        if isinstance(node, Widget):
            self._widget(node)
        elif isinstance(node, Layout):
            self._layout(node)
        self.layout.addStretch(1)

    def _widget(self, node: Widget):
        title = QLabel(node.class_name)
        title.setObjectName("section")
        self.layout.addWidget(title)
        name = QLineEdit(node.object_name)
        name.editingFinished.connect(lambda: self._rename(node.id, name.text()))
        self.layout.addWidget(name)
        if not valid_identifier(node.object_name):
            warn = QLabel("Name must be a Python identifier and unique in the form.")
            warn.setWordWrap(True)
            self.layout.addWidget(warn)
        form = QFormLayout()
        self.layout.addLayout(form)
        for prop_name in CURATED.get(node.class_name, ["toolTip", "enabled"]):
            self._editor(form, node, prop_name)
        if node.class_name == "QLabel":
            self._buddy(form, node)
        if node.class_name == "QComboBox":
            self._items(node)
        if node.class_name == "QTabWidget":
            self._pages(node)
        if node.class_name == "QMainWindow":
            self._actions(node)
        self._sizing(node)
        layout = widget_layout(node)
        if layout is not None:
            self._layout(layout, nested=True)
        self._why(node)
        self._all_properties(node)

    def _multi(self, widgets):
        label = QLabel(f"{len(widgets)} widgets selected")
        label.setObjectName("section")
        self.layout.addWidget(label)
        form = QFormLayout()
        self.layout.addLayout(form)
        shared = set(CURATED.get(widgets[0].class_name, []))
        for widget in widgets[1:]:
            shared &= set(CURATED.get(widget.class_name, []))
        for prop_name in sorted(shared):
            edit = QLineEdit()
            edit.setPlaceholderText("Set on all")
            edit.editingFinished.connect(lambda name=prop_name, box=edit: self._set_many(widgets, name, box.text()))
            form.addRow(prop_name, edit)

    def _editor(self, form, node, prop_name):
        current = get_property(node, prop_name)
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        editor = self._control(node, prop_name, current)
        row_layout.addWidget(editor, 1)
        if current is not None:
            reset = QPushButton("Reset")
            reset.clicked.connect(lambda _checked=False, name=prop_name: self.history.execute(SetProperty(node.id, name, None)))
            row_layout.addWidget(reset)
        form.addRow(prop_name, row)

    def _control(self, node, prop_name, current):
        kind = current.body.tag if current is not None else _guess_kind(prop_name)
        text = current.body.text if current is not None and not current.body.children else ""
        if kind == "bool":
            box = QCheckBox()
            box.setChecked(text == "true")
            box.toggled.connect(lambda checked, name=prop_name: self.history.execute(SetProperty(node.id, name, prop_bool(name, checked))))
            return box
        if kind == "number":
            spin = QSpinBox()
            spin.setRange(-999999, 999999)
            spin.setValue(int(float(text or "0")))
            spin.editingFinished.connect(lambda name=prop_name, box=spin: self.history.execute(SetProperty(node.id, name, prop_number(name, box.value()))))
            return spin
        if kind == "double":
            spin = QDoubleSpinBox()
            spin.setRange(-1e9, 1e9)
            spin.setValue(float(text or "0"))
            spin.editingFinished.connect(lambda name=prop_name, box=spin: self.history.execute(SetProperty(node.id, name, prop_double(name, box.value()))))
            return spin
        if kind in {"enum", "set"}:
            edit = QLineEdit(text)
            edit.editingFinished.connect(lambda name=prop_name, box=edit, kind=kind: self._commit_text(node.id, name, kind, box.text()))
            return edit
        edit = QLineEdit(text)
        edit.editingFinished.connect(lambda name=prop_name, box=edit: self.history.execute(SetProperty(node.id, name, prop_string(name, box.text()))))
        return edit

    def _commit_text(self, node_id, name, kind, text):
        body_prop = prop_enum(name, text) if kind == "enum" else prop_string(name, text)
        if kind == "set":
            from spikes.form_builder.model import prop_set

            body_prop = prop_set(name, text)
        self.history.execute(SetProperty(node_id, name, body_prop))

    def _buddy(self, form, node: Widget):
        combo = QComboBox()
        combo.addItem("")
        for widget in iter_widgets(self.doc):
            if widget.id != node.id and widget.object_name:
                combo.addItem(widget.object_name)
        buddy = get_property(node, "buddy")
        if buddy is not None:
            index = combo.findText(buddy.body.text)
            if index >= 0:
                combo.setCurrentIndex(index)
        combo.currentTextChanged.connect(
            lambda text: self.history.execute(SetProperty(node.id, "buddy", prop_string("buddy", text) if False else __buddy(text)))
        )
        form.addRow("buddy", combo)

    def _items(self, node: Widget):
        group = QGroupBox("Items")
        layout = QVBoxLayout(group)
        lines = []
        for part in node.body:
            if isinstance(part, ItemEntry):
                text = ""
                for child in part.body:
                    if isinstance(child, Property) and child.name == "text":
                        text = child.body.text
                lines.append(text)
        edit = QLineEdit(", ".join(lines))
        edit.setPlaceholderText("One, two, three")
        edit.editingFinished.connect(lambda: self._set_items(node, edit.text()))
        layout.addWidget(edit)
        self.layout.addWidget(group)

    def _set_items(self, node: Widget, text: str):
        pieces = [part.strip() for part in text.split(",") if part.strip()]
        self.history.execute(SetComboItems(node.id, pieces))

    def _pages(self, node: Widget):
        group = QGroupBox("Pages")
        layout = QVBoxLayout(group)
        for child in [part for part in node.body if isinstance(part, Widget)]:
            attr = get_attribute(child, "title")
            edit = QLineEdit(attr.body.text if attr else child.object_name)
            edit.editingFinished.connect(lambda child_id=child.id, box=edit: self.history.execute(SetAttribute(child_id, "title", box.text())))
            layout.addWidget(edit)
        add = QPushButton("Add page")
        add.clicked.connect(lambda: self._add_page(node))
        layout.addWidget(add)
        self.layout.addWidget(group)

    def _add_page(self, node: Widget):
        from spikes.form_builder.model import make_layout, make_widget, set_attribute, unique_name

        page = make_widget(self.doc, "QWidget", unique_name(self.doc, "page"))
        set_attribute(page, "title", page.object_name)
        page.body.append(make_layout(self.doc, "QVBoxLayout"))
        self.history.execute(InsertChild(node.id, 999, page))

    def _actions(self, node: Widget):
        from spikes.form_builder.model import Action

        group = QGroupBox("Actions")
        layout = QVBoxLayout(group)
        for part in node.body:
            if isinstance(part, Action):
                text = ""
                prop = get_property(part, "text")
                if prop is not None:
                    text = prop.body.text
                edit = QLineEdit(f"{part.name}: {text}")
                edit.setReadOnly(True)
                layout.addWidget(edit)
        self.layout.addWidget(group)

    def _sizing(self, node: Widget):
        group = QGroupBox("Sizing")
        form = QFormLayout(group)
        current = get_property(node, "sizePolicy")
        mode = QComboBox()
        mode.addItems(list(SIZING))
        if current is not None and current.body.tag == "sizepolicy":
            horiz = current.body.attrib.get("hsizetype", "Preferred")
            for label, pair in SIZING.items():
                if pair[0] == horiz:
                    mode.setCurrentText(label)
        stretch = QSpinBox()
        stretch.setRange(0, 20)
        if current is not None:
            for child in current.body.children:
                if child.tag == "horstretch":
                    stretch.setValue(int(child.text or "0"))
        mode.currentTextChanged.connect(lambda label, node_id=node.id, box=stretch: self._set_sizing(node_id, label, box.value()))
        stretch.editingFinished.connect(lambda node_id=node.id, picker=mode, box=stretch: self._set_sizing(node_id, picker.currentText(), box.value()))
        form.addRow("Behavior", mode)
        form.addRow("Stretch", stretch)
        self.layout.addWidget(group)

    def _set_sizing(self, node_id, label, stretch_value):
        horiz, vert = SIZING[label]
        body = XmlNode(
            "sizepolicy",
            {"hsizetype": horiz, "vsizetype": vert},
            "",
            [XmlNode("horstretch", {}, str(stretch_value)), XmlNode("verstretch", {}, str(stretch_value))],
        )
        self.history.execute(SetProperty(node_id, "sizePolicy", Property({"name": "sizePolicy"}, body)))

    def _why(self, node: Widget):
        label = QLabel(_why_sentence(self.canvas, node.id))
        label.setWordWrap(True)
        label.setObjectName("muted")
        self.layout.addWidget(label)

    def _layout(self, layout: Layout, nested: bool = False):
        group = QGroupBox("Layout" if not nested else layout.class_name)
        form = QFormLayout(group)
        for prop_name in ("spacing", "leftMargin", "topMargin", "rightMargin", "bottomMargin"):
            self._editor(form, layout, prop_name)
        if layout.class_name == "QFormLayout":
            self._editor(form, layout, "fieldGrowthPolicy")
        self.layout.addWidget(group)

    def _all_properties(self, node: Widget):
        button = QPushButton("All properties")
        button.setCheckable(True)
        holder = QWidget()
        holder_layout = QFormLayout(holder)
        holder.hide()

        def toggle(checked):
            if checked and holder_layout.rowCount() == 0:
                self._fill_meta(holder_layout, node)
            holder.setVisible(checked)

        button.toggled.connect(toggle)
        self.layout.addWidget(button)
        self.layout.addWidget(holder)

    def _fill_meta(self, form, node: Widget):
        widget = self.canvas.primary.realization.widgets.get(node.id) if self.canvas else None
        if widget is None:
            return
        meta = widget.metaObject()
        for index in range(meta.propertyCount()):
            prop = meta.property(index)
            if not prop.isWritable() or not prop.isReadable():
                continue
            name = prop.name()
            editor = self._meta_editor(node, widget, prop)
            if editor is not None:
                form.addRow(name, editor)

    def _meta_editor(self, node, widget, prop):
        name = prop.name()
        value = widget.property(name)
        if prop.isEnumType() and prop.enumerator() is not None:
            enum = prop.enumerator()
            combo = QComboBox()
            for key_index in range(enum.keyCount()):
                combo.addItem(enum.key(key_index))
            current = enum.valueToKey(int(value) if not hasattr(value, "value") else int(value.value)) if False else None
            try:
                key = enum.valueToKey(int(getattr(value, "value", value)))
            except (TypeError, ValueError):
                key = None
            if key:
                combo.setCurrentText(key)
            combo.currentTextChanged.connect(
                lambda text, prop_name=name, scope=enum.scope() or widget.metaObject().className(): self.history.execute(
                    SetProperty(node.id, prop_name, prop_enum(prop_name, f"{scope}::{text}"))
                )
            )
            return combo
        if isinstance(value, bool):
            box = QCheckBox()
            box.setChecked(value)
            box.toggled.connect(lambda checked, prop_name=name: self.history.execute(SetProperty(node.id, prop_name, prop_bool(prop_name, checked))))
            return box
        if isinstance(value, int) and not isinstance(value, bool):
            spin = QSpinBox()
            spin.setRange(-1000000, 1000000)
            spin.setValue(int(value))
            spin.editingFinished.connect(lambda prop_name=name, box=spin: self.history.execute(SetProperty(node.id, prop_name, prop_number(prop_name, box.value()))))
            return spin
        if isinstance(value, float):
            spin = QDoubleSpinBox()
            spin.setRange(-1e9, 1e9)
            spin.setValue(float(value))
            spin.editingFinished.connect(lambda prop_name=name, box=spin: self.history.execute(SetProperty(node.id, prop_name, prop_double(prop_name, box.value()))))
            return spin
        if isinstance(value, str):
            edit = QLineEdit(value)
            edit.editingFinished.connect(lambda prop_name=name, box=edit: self.history.execute(SetProperty(node.id, prop_name, prop_string(prop_name, box.text()))))
            return edit
        return None

    def _rename(self, node_id, text):
        from spikes.form_builder.commands import Rename

        node = find_node(self.doc, node_id)
        if node is None or not isinstance(node, Widget) or text == node.object_name:
            return
        if not valid_identifier(text):
            return
        if any(widget.object_name == text for widget in iter_widgets(self.doc) if widget.id != node_id):
            return
        self.history.execute(Rename(node_id, text))

    def _set_many(self, widgets, prop_name, text):
        if text == "":
            return
        self.history.execute(SetProperties([widget.id for widget in widgets], prop_name, prop_string(prop_name, text)))


class SignalsPanel(QWidget):
    def __init__(self):
        super().__init__()
        self.doc = None
        self.history = None
        layout = QVBoxLayout(self)
        self.list_host = QVBoxLayout()
        layout.addLayout(self.list_host)
        self.sender = QLineEdit()
        self.sender.setPlaceholderText("sender objectName")
        self.signal = QLineEdit("toggled(bool)")
        self.receiver = QLineEdit()
        self.receiver.setPlaceholderText("receiver objectName")
        self.slot = QLineEdit("setEnabled(bool)")
        add = QPushButton("Add connection")
        add.setObjectName("primary")
        add.clicked.connect(self._add)
        for widget in (self.sender, self.signal, self.receiver, self.slot, add):
            layout.addWidget(widget)
        layout.addStretch(1)

    def set_session(self, doc, history):
        self.doc = doc
        self.history = history
        self.refresh()

    def refresh(self):
        while self.list_host.count():
            item = self.list_host.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        if self.doc is None:
            return
        links = connections_of(self.doc)
        if links is None:
            return
        for index, link in enumerate(links.items):
            row = QLabel(f"{link.sender}.{link.signal} → {link.receiver}.{link.slot}")
            row.setWordWrap(True)
            remove = QPushButton(f"Remove {index + 1}")
            remove.clicked.connect(lambda _checked=False, row_index=index: self.history.execute(RemoveConnection(row_index)))
            self.list_host.addWidget(row)
            self.list_host.addWidget(remove)

    def _add(self):
        if self.history is None:
            return
        self.history.execute(
            AddConnection(Connection(self.sender.text(), self.signal.text(), self.receiver.text(), self.slot.text()))
        )


def _guess_kind(name: str) -> str:
    if name in {"enabled", "checked", "readOnly", "editable", "checkable", "flat"}:
        return "bool"
    if name in {"minimum", "maximum", "value", "singleStep", "currentIndex", "decimals", "spacing"}:
        return "number"
    if name in {"orientation", "alignment", "standardButtons", "fieldGrowthPolicy"}:
        return "enum"
    return "string"


def _why_sentence(canvas, node_id: str) -> str:
    widget = None
    if canvas is not None:
        widget = canvas.primary.realization.widgets.get(node_id)
    if widget is None:
        return "The size sentence appears after the canvas builds this widget."
    hint = widget.sizeHint()
    policy = widget.sizePolicy()
    horizontal = getattr(policy.horizontalPolicy(), "name", str(policy.horizontalPolicy()))
    vertical = getattr(policy.verticalPolicy(), "name", str(policy.verticalPolicy()))
    return (
        f"This is {widget.width()} by {widget.height()} pixels. "
        f"It asks for {hint.width()} by {hint.height()}. "
        f"Horizontal policy is {horizontal} with stretch {policy.horizontalStretch()}. "
        f"Vertical policy is {vertical} with stretch {policy.verticalStretch()}. "
        f"Minimum is {widget.minimumWidth()} by {widget.minimumHeight()}. "
        f"Maximum is {widget.maximumWidth()} by {widget.maximumHeight()}."
    )


def __buddy(text: str):
    from spikes.form_builder.model import prop_cstring

    if not text:
        return None
    return prop_cstring("buddy", text)
