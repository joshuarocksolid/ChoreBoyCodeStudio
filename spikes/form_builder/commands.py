"""Edits. Every mutation of a Document goes through History."""

from __future__ import annotations

import copy
from typing import Callable, Optional

from spikes.form_builder.model import (
    ActionRef,
    Attribute,
    Connection,
    ConnectionList,
    Document,
    ItemEntry,
    Layout,
    LayoutItem,
    Property,
    TabStops,
    Widget,
    ZOrder,
    attributes_of,
    child_widgets,
    clone_widget,
    connections_of,
    default_object_name,
    ensure_connections,
    ensure_tabstops,
    find_node,
    get_property,
    insert_layout_item,
    item_content,
    layout_items,
    locate,
    make_item,
    make_layout,
    make_widget,
    set_attribute,
    set_property,
    tabstops_of,
    unique_name,
    widget_layout,
)


class History:
    def __init__(self, doc: Document):
        self.doc = doc
        self.undo_stack: list = []
        self.redo_stack: list = []
        self.listeners: list[Callable] = []
        self.dirty = False

    def execute(self, command) -> None:
        command.redo(self.doc)
        self.undo_stack.append(command)
        self.redo_stack.clear()
        self.dirty = True
        self._emit(command)

    def undo(self) -> bool:
        if not self.undo_stack:
            return False
        command = self.undo_stack.pop()
        command.undo(self.doc)
        self.redo_stack.append(command)
        self.dirty = True
        self._emit(command)
        return True

    def redo(self) -> bool:
        if not self.redo_stack:
            return False
        command = self.redo_stack.pop()
        command.redo(self.doc)
        self.undo_stack.append(command)
        self.dirty = True
        self._emit(command)
        return True

    def mark_clean(self) -> None:
        self.dirty = False

    def _emit(self, command) -> None:
        for listener in list(self.listeners):
            listener(command)


class Compound:
    def __init__(self, steps: list):
        self.steps = steps

    def redo(self, doc: Document) -> None:
        for step in self.steps:
            step.redo(doc)

    def undo(self, doc: Document) -> None:
        for step in reversed(self.steps):
            step.undo(doc)


class SetProperty:
    def __init__(self, node_id: str, name: str, new: Optional[Property]):
        self.node_id = node_id
        self.name = name
        self.new = copy.deepcopy(new) if new is not None else None
        self.old: Optional[Property] = None
        self.captured = False

    def redo(self, doc: Document) -> None:
        node = find_node(doc, self.node_id)
        if node is None:
            raise KeyError(self.node_id)
        if not self.captured:
            current = get_property(node, self.name)
            self.old = copy.deepcopy(current) if current is not None else None
            self.captured = True
        set_property(node, copy.deepcopy(self.new) if self.new is not None else None, self.name)

    def undo(self, doc: Document) -> None:
        node = find_node(doc, self.node_id)
        set_property(node, copy.deepcopy(self.old) if self.old is not None else None, self.name)


class SetProperties:
    """One undo step that writes the same property onto many nodes."""

    def __init__(self, node_ids: list[str], name: str, new: Optional[Property]):
        self.steps = [SetProperty(node_id, name, new) for node_id in node_ids]

    def redo(self, doc: Document) -> None:
        for step in self.steps:
            step.redo(doc)

    def undo(self, doc: Document) -> None:
        for step in reversed(self.steps):
            step.undo(doc)


class Rename:
    def __init__(self, node_id: str, new_name: str):
        self.node_id = node_id
        self.new_name = new_name
        self.old_name = ""
        self.captured = False

    def redo(self, doc: Document) -> None:
        node = find_node(doc, self.node_id)
        if node is None:
            raise KeyError(self.node_id)
        if not self.captured:
            self.old_name = _node_name(node)
            self.captured = True
        _set_node_name(node, self.new_name)
        _rewrite_refs(doc, self.old_name, self.new_name)

    def undo(self, doc: Document) -> None:
        node = find_node(doc, self.node_id)
        _set_node_name(node, self.old_name)
        _rewrite_refs(doc, self.new_name, self.old_name)


class EnsureLayout:
    def __init__(
        self,
        widget_id: str,
        layout_class: str = "QVBoxLayout",
        layout_id: str = "",
        layout_name: str = "",
    ):
        self.widget_id = widget_id
        self.layout_class = layout_class
        self.layout_id = layout_id
        self.layout_name = layout_name
        self.moved: list[tuple[int, Widget]] = []
        self.captured = False
        self.skipped = False

    def redo(self, doc: Document) -> None:
        widget = find_node(doc, self.widget_id)
        if not isinstance(widget, Widget):
            raise KeyError(self.widget_id)
        if widget_layout(widget) is not None:
            self.skipped = True
            return
        if not self.captured:
            if not self.layout_id:
                self.layout_id = doc.alloc()
            if not self.layout_name:
                self.layout_name = unique_name(doc, default_object_name(self.layout_class))
            children = child_widgets(widget)
            self.moved = []
            for child in children:
                parent, index = locate(doc, child.id)
                self.moved.append((index, child))
            self.captured = True
        for _index, child in sorted(self.moved, key=lambda pair: pair[0], reverse=True):
            parent, index = locate(doc, child.id)
            parent.body.pop(index)
        layout = Layout(
            id=self.layout_id,
            class_name=self.layout_class,
            object_name=self.layout_name,
        )
        for _index, child in self.moved:
            layout.body.append(make_item(doc, child))
        insert_at = 0
        for index, part in enumerate(widget.body):
            if isinstance(part, Property):
                insert_at = index + 1
        widget.body.insert(insert_at, layout)

    def undo(self, doc: Document) -> None:
        if self.skipped:
            return
        widget = find_node(doc, self.widget_id)
        layout = widget_layout(widget)
        if layout is None:
            return
        children = []
        for item in layout_items(layout):
            content = item_content(item)
            if isinstance(content, Widget):
                children.append(content)
        parent, index = locate(doc, layout.id)
        parent.body.pop(index)
        for child in children:
            widget.body.append(child)


class InsertItem:
    def __init__(self, layout_id: str, index: int, item: LayoutItem):
        self.layout_id = layout_id
        self.index = index
        self.item = item
        self.captured = False

    def redo(self, doc: Document) -> None:
        layout = find_node(doc, self.layout_id)
        if not isinstance(layout, Layout):
            raise KeyError(self.layout_id)
        insert_layout_item(layout, self.index, self.item)
        self.captured = True

    def undo(self, doc: Document) -> None:
        located = locate(doc, self.item.id)
        if located is None:
            return
        parent, index = located
        parent.body.pop(index)


class InsertChild:
    """Insert a widget into another widget's body. Used for pages and splitter children."""

    def __init__(self, parent_id: str, index: int, widget: Widget):
        self.parent_id = parent_id
        self.index = index
        self.widget = widget

    def redo(self, doc: Document) -> None:
        parent = find_node(doc, self.parent_id)
        if not isinstance(parent, Widget):
            raise KeyError(self.parent_id)
        widgets = child_widgets(parent)
        if self.index >= len(widgets) or not widgets:
            parent.body.append(self.widget)
            return
        target = widgets[min(max(self.index, 0), len(widgets) - 1)]
        parent.body.insert(parent.body.index(target), self.widget)

    def undo(self, doc: Document) -> None:
        located = locate(doc, self.widget.id)
        if located is None:
            return
        parent, index = located
        parent.body.pop(index)


class Delete:
    def __init__(self, node_ids: list[str]):
        self.node_ids = list(node_ids)
        self.removed: list[tuple[str, int, object]] = []
        self.captured = False

    def redo(self, doc: Document) -> None:
        if not self.captured:
            packed = []
            for node_id in self.node_ids:
                located = locate(doc, node_id)
                if located is None:
                    continue
                parent, index = located
                packed.append((parent.id, index, copy.deepcopy(parent.body[index])))
            packed.sort(key=lambda row: (row[0], -row[1]))
            # Removing high indexes first only works inside one capture pass.
            # Store original indexes and delete from the live tree high to low per parent.
            self.removed = packed
            self.captured = True
        grouped: dict[str, list[tuple[int, object]]] = {}
        for parent_id, index, node in self.removed:
            grouped.setdefault(parent_id, []).append((index, node))
        for parent_id, rows in grouped.items():
            parent = find_node(doc, parent_id)
            for index, _node in sorted(rows, key=lambda row: -row[0]):
                parent.body.pop(index)

    def undo(self, doc: Document) -> None:
        for parent_id, index, node in sorted(self.removed, key=lambda row: (row[0], row[1])):
            parent = find_node(doc, parent_id)
            parent.body.insert(index, copy.deepcopy(node))


class MoveItem:
    def __init__(self, item_id: str, dest_layout_id: str, dest_index: int, new_attrib: Optional[dict] = None):
        self.item_id = item_id
        self.dest_layout_id = dest_layout_id
        self.dest_index = dest_index
        self.new_attrib = None if new_attrib is None else dict(new_attrib)
        self.src_layout_id = ""
        self.src_index = 0
        self.old_attrib: dict = {}
        self.adjusted_index = dest_index
        self.captured = False

    def redo(self, doc: Document) -> None:
        located = locate(doc, self.item_id)
        if located is None:
            raise KeyError(self.item_id)
        source, src_index = located
        if not self.captured:
            self.src_layout_id = source.id
            self.src_index = src_index
            item = source.body[src_index]
            self.old_attrib = dict(item.attrib)
            self.captured = True
        item = source.body.pop(src_index)
        if self.new_attrib is not None:
            item.attrib = dict(self.new_attrib)
        dest = find_node(doc, self.dest_layout_id)
        index = self.dest_index
        if source.id == dest.id and src_index < index:
            index -= 1
        self.adjusted_index = index
        insert_layout_item(dest, index, item)

    def undo(self, doc: Document) -> None:
        located = locate(doc, self.item_id)
        if located is None:
            return
        parent, index = located
        item = parent.body.pop(index)
        item.attrib = dict(self.old_attrib)
        source = find_node(doc, self.src_layout_id)
        source.body.insert(self.src_index, item)


class Wrap:
    def __init__(self, item_ids: list[str], container_class: str, layout_class: str):
        self.item_ids = list(item_ids)
        self.container_class = container_class
        self.layout_class = layout_class
        self.parent_id = ""
        self.indexes: list[int] = []
        self.container: Optional[Widget] = None
        self.container_item: Optional[LayoutItem] = None
        self.captured = False

    def redo(self, doc: Document) -> None:
        if not self.item_ids:
            return
        if not self.captured:
            located = [locate(doc, item_id) for item_id in self.item_ids]
            if any(row is None for row in located):
                raise KeyError("wrap target missing")
            parents = {row[0].id for row in located}
            if len(parents) != 1:
                raise ValueError("wrap needs siblings")
            self.parent_id = located[0][0].id
            order = sorted(zip(self.item_ids, located), key=lambda pair: pair[1][1])
            self.item_ids = [pair[0] for pair in order]
            self.indexes = [pair[1][1] for pair in order]
            container = make_widget(doc, self.container_class)
            if self.container_class == "QGroupBox":
                set_property(container, _string_prop("title", "Group"), "title")
            layout = make_layout(doc, self.layout_class)
            container.body.append(layout)
            self.container = container
            self.container_item = LayoutItem(id=doc.alloc(), body=[container])
            self.captured = True
        parent = find_node(doc, self.parent_id)
        first = parent.body[self.indexes[0]]
        slot = layout_items(parent).index(first)
        picked = []
        for index in sorted(self.indexes, reverse=True):
            picked.append(parent.body.pop(index))
        picked.reverse()
        layout = widget_layout(self.container)
        layout.body = [part for part in layout.body if not isinstance(part, LayoutItem)]
        layout.body.extend(picked)
        insert_layout_item(parent, slot, self.container_item)

    def undo(self, doc: Document) -> None:
        if self.container_item is None:
            return
        parent = find_node(doc, self.parent_id)
        located = locate(doc, self.container_item.id)
        if located is not None:
            parent.body.pop(located[1])
        layout = widget_layout(self.container)
        items = [part for part in layout.body if isinstance(part, LayoutItem)]
        layout.body = [part for part in layout.body if not isinstance(part, LayoutItem)]
        for offset, item in enumerate(items):
            parent.body.insert(self.indexes[0] + offset, item)


class Unwrap:
    def __init__(self, container_id: str):
        self.container_id = container_id
        self.parent_id = ""
        self.index = 0
        self.item: Optional[LayoutItem] = None
        self.inner_ids: list[str] = []
        self.captured = False

    def redo(self, doc: Document) -> None:
        container = find_node(doc, self.container_id)
        if not isinstance(container, Widget):
            raise KeyError(self.container_id)
        located = locate(doc, self.container_id)
        if located is None or not isinstance(located[0], LayoutItem):
            raise ValueError("unwrap needs a laid-out container")
        holder = located[0]
        if not self.captured:
            parent_of_holder, index = locate(doc, holder.id)
            self.parent_id = parent_of_holder.id
            self.index = index
            self.item = holder
            layout = widget_layout(container)
            self.inner_ids = [item.id for item in layout_items(layout)] if layout else []
            self.captured = True
        parent = find_node(doc, self.parent_id)
        parent.body.pop(parent.body.index(holder))
        layout = widget_layout(container)
        inners = [part for part in layout.body if isinstance(part, LayoutItem)] if layout else []
        if layout is not None:
            layout.body = [part for part in layout.body if not isinstance(part, LayoutItem)]
        for offset, inner in enumerate(inners):
            parent.body.insert(self.index + offset, inner)

    def undo(self, doc: Document) -> None:
        parent = find_node(doc, self.parent_id)
        inners = []
        for inner_id in self.inner_ids:
            located = locate(doc, inner_id)
            if located is None:
                continue
            inners.append(parent.body.pop(located[1]))
        layout = widget_layout(self.item.body[0])
        layout.body.extend(inners)
        parent.body.insert(self.index, self.item)


class SetAttribute:
    def __init__(self, widget_id: str, name: str, text: str):
        self.widget_id = widget_id
        self.name = name
        self.text = text
        self.old: Optional[Attribute] = None
        self.captured = False

    def redo(self, doc: Document) -> None:
        widget = find_node(doc, self.widget_id)
        if not isinstance(widget, Widget):
            raise KeyError(self.widget_id)
        if not self.captured:
            current = None
            for attr in attributes_of(widget):
                if attr.name == self.name:
                    current = copy.deepcopy(attr)
            self.old = current
            self.captured = True
        set_attribute(widget, self.name, self.text)

    def undo(self, doc: Document) -> None:
        widget = find_node(doc, self.widget_id)
        widget.body = [
            part
            for part in widget.body
            if not (isinstance(part, Attribute) and part.name == self.name)
        ]
        if self.old is not None:
            widget.body.append(copy.deepcopy(self.old))


class AddConnection:
    def __init__(self, link: Connection):
        self.link = link

    def redo(self, doc: Document) -> None:
        ensure_connections(doc).items.append(self.link)

    def undo(self, doc: Document) -> None:
        block = connections_of(doc)
        if block and self.link in block.items:
            block.items.remove(self.link)


class RemoveConnection:
    def __init__(self, index: int):
        self.index = index
        self.link: Optional[Connection] = None

    def redo(self, doc: Document) -> None:
        block = connections_of(doc)
        if block is None or self.index >= len(block.items):
            return
        if self.link is None:
            self.link = block.items[self.index]
        block.items.pop(self.index)

    def undo(self, doc: Document) -> None:
        if self.link is None:
            return
        ensure_connections(doc).items.insert(self.index, self.link)


class SetTabStops:
    def __init__(self, names: Optional[list[str]]):
        self.names = None if names is None else list(names)
        self.old: Optional[list[str]] = None
        self.had = False
        self.captured = False

    def redo(self, doc: Document) -> None:
        current = tabstops_of(doc)
        if not self.captured:
            self.had = current is not None
            self.old = list(current.names) if current is not None else None
            self.captured = True
        if self.names is None:
            doc.footer = [part for part in doc.footer if not isinstance(part, TabStops)]
            return
        block = ensure_tabstops(doc)
        block.names = list(self.names)

    def undo(self, doc: Document) -> None:
        if not self.had:
            doc.footer = [part for part in doc.footer if not isinstance(part, TabStops)]
            return
        block = ensure_tabstops(doc)
        block.names = list(self.old or [])


class SetComboItems:
    def __init__(self, widget_id: str, texts: list[str]):
        self.widget_id = widget_id
        self.texts = list(texts)
        self.old: Optional[list] = None

    def redo(self, doc: Document) -> None:
        node = find_node(doc, self.widget_id)
        if not isinstance(node, Widget):
            return
        if self.old is None:
            self.old = [part for part in node.body if isinstance(part, ItemEntry)]
        node.body = [part for part in node.body if not isinstance(part, ItemEntry)]
        for text in self.texts:
            node.body.append(ItemEntry(body=[_string_prop("text", text)]))

    def undo(self, doc: Document) -> None:
        node = find_node(doc, self.widget_id)
        if not isinstance(node, Widget) or self.old is None:
            return
        node.body = [part for part in node.body if not isinstance(part, ItemEntry)]
        node.body.extend(copy.deepcopy(self.old))


def _string_prop(name: str, text: str) -> Property:
    from spikes.form_builder.model import prop_string

    return prop_string(name, text)


def _node_name(node) -> str:
    if isinstance(node, Widget):
        return node.object_name
    if isinstance(node, Layout):
        return node.object_name
    return getattr(node, "name", "")


def _set_node_name(node, name: str) -> None:
    if isinstance(node, (Widget, Layout)):
        node.object_name = name
    else:
        node.name = name


def _rewrite_refs(doc: Document, old: str, new: str) -> None:
    if not old or old == new:
        return

    def walk(node) -> None:
        body = getattr(node, "body", None)
        if not isinstance(body, list):
            return
        for part in body:
            if isinstance(part, Property) and part.body.tag == "cstring" and part.body.text == old:
                part.body.text = new
            elif isinstance(part, ActionRef) and part.name == old:
                part.name = new
            elif isinstance(part, ZOrder) and part.name == old:
                part.name = new
            else:
                walk(part)

    walk(doc.root)
    stops = tabstops_of(doc)
    if stops:
        stops.names = [new if name == old else name for name in stops.names]
    links = connections_of(doc)
    if links:
        for link in links.items:
            if link.sender == old:
                link.sender = new
            if link.receiver == old:
                link.receiver = new


def resolve_layout_item(doc: Document, node_id: str) -> Optional[LayoutItem]:
    node = find_node(doc, node_id)
    if isinstance(node, LayoutItem):
        return node
    located = locate(doc, node_id)
    if located is not None and isinstance(located[0], LayoutItem):
        content = item_content(located[0])
        if content is node or getattr(content, "id", None) == node_id:
            return located[0]
    return None


def delete_targets(doc: Document, node_ids: list[str]) -> list[str]:
    targets = []
    for node_id in node_ids:
        item = resolve_layout_item(doc, node_id)
        if item is not None:
            targets.append(item.id)
            continue
        if locate(doc, node_id) is not None:
            targets.append(node_id)
    return targets


def nest_command(doc: Document, node_id: str):
    """Move a layout item into the previous sibling container."""

    item = resolve_layout_item(doc, node_id)
    if item is None:
        return None
    located = locate(doc, item.id)
    if located is None or not isinstance(located[0], Layout):
        return None
    parent, _index = located
    items = layout_items(parent)
    slot = items.index(item)
    if slot == 0:
        return None
    previous = item_content(items[slot - 1])
    if not isinstance(previous, Widget):
        return None
    if previous.class_name in {
        "QLineEdit",
        "QLabel",
        "QPushButton",
        "QCheckBox",
        "QSpinBox",
        "QComboBox",
        "QPlainTextEdit",
    }:
        return None
    dest = widget_layout(previous)
    steps = []
    if dest is None:
        layout_id = doc.alloc()
        layout_name = unique_name(doc, default_object_name("QVBoxLayout"))
        steps.append(EnsureLayout(previous.id, "QVBoxLayout", layout_id, layout_name))
        dest_id = layout_id
        dest_count = 0
    else:
        dest_id = dest.id
        dest_count = len(layout_items(dest))
    steps.append(MoveItem(item.id, dest_id, dest_count))
    return steps[0] if len(steps) == 1 else Compound(steps)


def unnest_command(doc: Document, node_id: str):
    item = resolve_layout_item(doc, node_id)
    if item is None:
        return None
    located = locate(doc, item.id)
    if located is None or not isinstance(located[0], Layout):
        return None
    layout = located[0]
    owner = None
    for node in _widgets_owning_layout(doc, layout.id):
        owner = node
        break
    if owner is None:
        return None
    holder = resolve_layout_item(doc, owner.id)
    if holder is None:
        return None
    holder_loc = locate(doc, holder.id)
    if holder_loc is None or not isinstance(holder_loc[0], Layout):
        return None
    dest = holder_loc[0]
    dest_slot = layout_items(dest).index(holder) + 1
    return MoveItem(item.id, dest.id, dest_slot)


def _widgets_owning_layout(doc: Document, layout_id: str):
    from spikes.form_builder.model import iter_widgets

    for widget in iter_widgets(doc):
        layout = widget_layout(widget)
        if layout is not None and layout.id == layout_id:
            yield widget


def duplicate_item(doc: Document, item_id: str) -> Optional[InsertItem]:
    located = locate(doc, item_id)
    if located is None:
        return None
    parent, index = located
    if not isinstance(parent, Layout):
        return None
    original = parent.body[index]
    content = item_content(original)
    if not isinstance(content, Widget):
        return None
    cloned = clone_widget(doc, content)
    item = LayoutItem(id=doc.alloc(), attrib=dict(original.attrib), body=[cloned])
    return InsertItem(parent.id, index + 1, item)
