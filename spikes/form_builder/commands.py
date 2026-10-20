"""Edits. Every mutation of a Document goes through History."""

from __future__ import annotations

import copy
from typing import Callable, Optional

from spikes.form_builder.model import (
    INPUT_CLASSES,
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
    reading_order,
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


class SetLayoutAttrib:
    """Set or remove a ui4 layout attribute such as stretch or columnstretch."""

    def __init__(self, layout_id: str, key: str, value: Optional[str]):
        self.layout_id = layout_id
        self.key = key
        self.value = value
        self.old: Optional[str] = None
        self.captured = False

    def redo(self, doc: Document) -> None:
        layout = find_node(doc, self.layout_id)
        if not isinstance(layout, Layout):
            raise KeyError(self.layout_id)
        if not self.captured:
            self.old = layout.attrib.get(self.key)
            self.captured = True
        _put(layout.attrib, self.key, self.value)

    def undo(self, doc: Document) -> None:
        layout = find_node(doc, self.layout_id)
        _put(layout.attrib, self.key, self.old)


class SetItemAttrib:
    """Change a layout item's row, column, or span without moving it."""

    def __init__(self, item_id: str, attrib: dict):
        self.item_id = item_id
        self.attrib = dict(attrib)
        self.old: Optional[dict] = None

    def redo(self, doc: Document) -> None:
        item = find_node(doc, self.item_id)
        if not isinstance(item, LayoutItem):
            raise KeyError(self.item_id)
        if self.old is None:
            self.old = dict(item.attrib)
        item.attrib = dict(self.attrib)

    def undo(self, doc: Document) -> None:
        item = find_node(doc, self.item_id)
        item.attrib = dict(self.old or {})


class InsertPart:
    """Insert any body part (an action, an action reference, a menu) at an index."""

    def __init__(self, parent_id: str, index: int, part):
        self.parent_id = parent_id
        self.index = index
        self.part = part
        self.at = -1

    def redo(self, doc: Document) -> None:
        parent = find_node(doc, self.parent_id)
        if parent is None:
            raise KeyError(self.parent_id)
        index = len(parent.body) if self.index < 0 or self.index > len(parent.body) else self.index
        parent.body.insert(index, self.part)
        self.at = index

    def undo(self, doc: Document) -> None:
        parent = find_node(doc, self.parent_id)
        for index, part in enumerate(parent.body):
            if part is self.part:
                parent.body.pop(index)
                return


class RemovePart:
    def __init__(self, parent_id: str, index: int):
        self.parent_id = parent_id
        self.index = index
        self.part = None

    def redo(self, doc: Document) -> None:
        parent = find_node(doc, self.parent_id)
        self.part = parent.body.pop(self.index)

    def undo(self, doc: Document) -> None:
        parent = find_node(doc, self.parent_id)
        parent.body.insert(self.index, self.part)


class SpliceTabStops:
    """After an insert, put the new inputs into the saved tab order by reading order.

    Runs inside the same Compound as the insert, so it sees the new widgets.
    Does nothing when the form has no explicit tab order.
    """

    def __init__(self, names: list[str]):
        self.names = list(names)
        self.old: Optional[list[str]] = None

    def redo(self, doc: Document) -> None:
        stops = tabstops_of(doc)
        if stops is None or not stops.names:
            self.old = None
            return
        self.old = list(stops.names)
        stops.names = splice_names(stops.names, reading_order(doc.root), self.names)

    def undo(self, doc: Document) -> None:
        stops = tabstops_of(doc)
        if stops is not None and self.old is not None:
            stops.names = list(self.old)


def _put(attrib: dict, key: str, value: Optional[str]) -> None:
    if value is None or value == "":
        attrib.pop(key, None)
    else:
        attrib[key] = value


def splice_names(order: list[str], reading: list[str], new_names: list[str]) -> list[str]:
    """Insert new_names into order, each after the nearest earlier name in reading order."""
    result = [name for name in order]
    for name in new_names:
        if name in result or name not in reading:
            continue
        position = reading.index(name)
        anchor = None
        for earlier in reversed(reading[:position]):
            if earlier in result:
                anchor = earlier
                break
        if anchor is None:
            following = next((later for later in reading[position + 1:] if later in result), None)
            index = result.index(following) if following is not None else len(result)
        else:
            index = result.index(anchor) + 1
        result.insert(index, name)
    return result


def input_names(node) -> list[str]:
    """Object names of focusable inputs inside a widget subtree, in reading order."""
    if not isinstance(node, Widget):
        return []
    return reading_order(node)


def with_tab_splice(doc: Document, command, content):
    """Wrap an insert so new inputs join the saved tab order in reading position."""
    names = input_names(content)
    if not names or tabstops_of(doc) is None or not tabstops_of(doc).names:
        return command
    return Compound([command, SpliceTabStops(names)])


def pair_buddies(doc: Document) -> list:
    """Buddy every unpaired label in a form layout to the field in its row."""
    from spikes.form_builder.model import iter_nodes, prop_cstring

    steps = []
    for node in iter_nodes(doc):
        if not isinstance(node, Layout) or node.class_name not in ("QFormLayout", "QGridLayout"):
            continue
        cells = {}
        for item in layout_items(node):
            content = item_content(item)
            if isinstance(content, Widget):
                cells[(item.attrib.get("row", "0"), item.attrib.get("column", "0"))] = content
        for (row, column), content in cells.items():
            if content.class_name != "QLabel" or get_property(content, "buddy") is not None:
                continue
            field = cells.get((row, str(int(column) + 1)))
            if field is None or field.class_name not in INPUT_CLASSES or field.class_name in BUTTONISH:
                continue
            steps.append(SetProperty(content.id, "buddy", prop_cstring("buddy", field.object_name)))
    return steps


BUTTONISH = {"QPushButton", "QToolButton", "QCommandLinkButton", "QCheckBox", "QRadioButton"}


def next_cell(layout: Layout, content=None) -> dict:
    """Where the next control goes when no cell was pointed at.

    Form layout: a field fills the empty field column of the last row; anything
    else starts a new row. Grid: the first empty cell in reading order inside the
    current bounds, else a new row. Box layouts have no cells.
    """
    items = layout_items(layout)
    if layout.class_name == "QFormLayout":
        rows: dict[int, set] = {}
        for item in items:
            row = int(item.attrib.get("row", "0") or 0)
            rows.setdefault(row, set()).add(item.attrib.get("column", "0"))
        last = max(rows) if rows else -1
        is_label = isinstance(content, Widget) and content.class_name == "QLabel"
        if last >= 0 and not is_label and rows[last] == {"0"}:
            return {"row": str(last), "column": "1"}
        return {"row": str(last + 1), "column": "0" if is_label else "1"}
    if layout.class_name == "QGridLayout":
        taken = set()
        rows = cols = 0
        for item in items:
            row = int(item.attrib.get("row", "0") or 0)
            col = int(item.attrib.get("column", "0") or 0)
            rowspan = int(item.attrib.get("rowspan", "1") or 1)
            colspan = int(item.attrib.get("colspan", "1") or 1)
            for r in range(row, row + rowspan):
                for c in range(col, col + colspan):
                    taken.add((r, c))
            rows = max(rows, row + rowspan)
            cols = max(cols, col + colspan)
        for r in range(rows):
            for c in range(max(cols, 1)):
                if (r, c) not in taken:
                    return {"row": str(r), "column": str(c)}
        return {"row": str(rows), "column": "0"}
    return {}


def insert_form_row(doc: Document, layout: Layout, row: int, item: LayoutItem):
    """Insert a new row in a form or grid layout: rows at and below move down by one."""
    steps = []
    for existing in layout_items(layout):
        current = int(existing.attrib.get("row", "0") or 0)
        if current >= row:
            attrib = dict(existing.attrib)
            attrib["row"] = str(current + 1)
            steps.append(SetItemAttrib(existing.id, attrib))
    steps.append(InsertItem(layout.id, len(layout_items(layout)), item))
    return Compound(steps)


def add_menu_command(doc: Document, bar_id: str, title: str):
    """A new menu on a menu bar: the QMenu child plus the bar's addaction reference."""
    from spikes.form_builder.model import prop_string

    bar = find_node(doc, bar_id)
    base = "menu" + "".join(part.capitalize() for part in _words(title)) or "menu"
    menu = make_widget(doc, "QMenu", unique_name(doc, base))
    menu.body.append(prop_string("title", title))
    widgets = [part for part in bar.body if isinstance(part, Widget)]
    index = bar.body.index(widgets[-1]) + 1 if widgets else len(bar.body)
    steps = [InsertPart(bar.id, index, menu), InsertPart(bar.id, -1, ActionRef(menu.object_name))]
    return Compound(steps), menu.id


def add_action_command(doc: Document, menu_id: str, text: str):
    """Type-here on a menu: '-' adds a separator, anything else a new QAction on the form."""
    from spikes.form_builder.model import Action, prop_string

    menu = find_node(doc, menu_id)
    if text.strip() == "-":
        return InsertPart(menu.id, -1, ActionRef("separator")), ""
    base = "action" + "".join(part.capitalize() for part in _words(text)) or "action"
    action = Action(id=doc.alloc(), name=unique_name(doc, base))
    action.body.append(prop_string("text", text))
    actions = [i for i, part in enumerate(doc.root.body) if isinstance(part, Action)]
    if actions:
        at = actions[-1] + 1
    else:
        at = next((i for i, part in enumerate(doc.root.body) if isinstance(part, (Widget, Layout))), len(doc.root.body))
    steps = [InsertPart(doc.root.id, at, action), InsertPart(menu.id, -1, ActionRef(action.name))]
    return Compound(steps), action.id


def remove_action_ref_command(doc: Document, menu_id: str, action_name: str):
    menu = find_node(doc, menu_id)
    for index, part in enumerate(menu.body):
        if isinstance(part, ActionRef) and part.name == action_name:
            return RemovePart(menu.id, index)
    return None


def _words(text: str) -> list[str]:
    cleaned = "".join(char if char.isalnum() else " " for char in text.replace("&", ""))
    return [word for word in cleaned.split() if word]


def insert_near(doc: Document, ids: list[str], content):
    """Where quick insert, palette double-click, and paste put a new control.

    A selected container (or layout) receives it at its next free slot. A selected
    leaf gets it right after itself in its own layout: the next index in a box, the
    empty field beside a label or a new row below in a form, the next free cell in a
    grid. With nothing selected it goes to the end of the form, creating the first
    layout if the form has none.
    """
    target = find_node(doc, ids[0]) if ids else None
    if isinstance(target, Widget) and target.class_name == "QSplitter":
        if isinstance(content, Widget):
            return InsertChild(target.id, 10**6, content)
        return None
    if isinstance(target, Layout):
        return with_tab_splice(doc, _append(doc, target, content), content)
    if isinstance(target, Widget) and widget_layout(target) is not None and (target is doc.root or _is_box(target)):
        return with_tab_splice(doc, _append(doc, widget_layout(target), content), content)
    item = resolve_layout_item(doc, target.id) if target is not None and getattr(target, "id", None) else None
    if item is not None:
        located = locate(doc, item.id)
        layout = located[0] if located is not None else None
        if isinstance(layout, Layout):
            return with_tab_splice(doc, _after(doc, layout, item, content), content)
    if isinstance(target, Widget) and target.class_name in ("QTabWidget", "QStackedWidget"):
        pages = child_widgets(target)
        if pages:
            page = pages[0]
            if widget_layout(page) is None:
                layout_id = doc.alloc()
                steps = [EnsureLayout(page.id, "QVBoxLayout", layout_id, unique_name(doc, "verticalLayout")),
                         InsertItem(layout_id, 0, make_item(doc, content))]
                return with_tab_splice(doc, Compound(steps), content)
            return with_tab_splice(doc, _append(doc, widget_layout(page), content), content)
    root = doc.root
    if root.class_name == "QMainWindow":
        central = next((child for child in child_widgets(root) if child.class_name not in ("QMenuBar", "QToolBar", "QStatusBar", "QDockWidget")), None)
        if central is not None:
            root = central
    layout = widget_layout(root)
    if layout is None:
        layout_id = doc.alloc()
        steps = [EnsureLayout(root.id, "QVBoxLayout", layout_id, unique_name(doc, "verticalLayout")),
                 InsertItem(layout_id, 0, make_item(doc, content))]
        return with_tab_splice(doc, Compound(steps), content)
    return with_tab_splice(doc, _append(doc, layout, content), content)


def _is_box(widget: Widget) -> bool:
    return widget.class_name in ("QWidget", "QFrame", "QGroupBox", "QScrollArea", "QDialog", "QWizardPage") or not widget.class_name.startswith("Q")


def _append(doc: Document, layout: Layout, content):
    return InsertItem(layout.id, 10**6, make_item(doc, content, **next_cell(layout, content)))


def _after(doc: Document, layout: Layout, item: LayoutItem, content):
    if layout.class_name in ("QVBoxLayout", "QHBoxLayout"):
        index = layout_items(layout).index(item) + 1
        return InsertItem(layout.id, index, make_item(doc, content))
    if layout.class_name == "QFormLayout":
        row = int(item.attrib.get("row", "0") or 0)
        column = item.attrib.get("column", "0")
        is_label = isinstance(content, Widget) and content.class_name == "QLabel"
        taken = {(it.attrib.get("row"), it.attrib.get("column", "0")) for it in layout_items(layout)}
        if column == "0" and not is_label and (str(row), "1") not in taken and int(item.attrib.get("colspan", "1") or 1) < 2:
            return InsertItem(layout.id, 10**6, make_item(doc, content, row=str(row), column="1"))
        return insert_form_row(doc, layout, row + 1, make_item(doc, content, row=str(row + 1), column="0" if is_label else "1"))
    attrib = next_cell(layout, content)
    return InsertItem(layout.id, 10**6, make_item(doc, content, **attrib))


class MorphLayout:
    """Change a layout's kind in place. Children keep their reading order.

    To a box: cells are dropped. To a grid: a vertical box becomes one column, a
    horizontal box one row, a form keeps its rows. To a form: each label starts a
    row and the next control fills that row's field.
    """

    def __init__(self, layout_id: str, new_class: str):
        self.layout_id = layout_id
        self.new_class = new_class
        self.old_class = ""
        self.old_attrib: dict = {}
        self.old_body: list = []
        self.old_items: dict = {}

    def redo(self, doc: Document) -> None:
        layout = find_node(doc, self.layout_id)
        if not isinstance(layout, Layout):
            raise KeyError(self.layout_id)
        self.old_class = layout.class_name
        self.old_attrib = dict(layout.attrib)
        self.old_body = list(layout.body)
        items = layout_items(layout)
        self.old_items = {item.id: dict(item.attrib) for item in items}
        if layout.class_name in ("QGridLayout", "QFormLayout"):
            ordered = sorted(items, key=lambda item: (int(item.attrib.get("row", "0") or 0), int(item.attrib.get("column", "0") or 0)))
        else:
            ordered = list(items)
        new_attribs = _morph_attribs(layout.class_name, self.new_class, ordered)
        others = [part for part in layout.body if not isinstance(part, LayoutItem)]
        for item, attrib in zip(ordered, new_attribs):
            item.attrib = attrib
        layout.body = others + ordered
        layout.class_name = self.new_class
        for key in ("stretch", "rowstretch", "columnstretch", "rowminimumheight", "columnminimumwidth"):
            layout.attrib.pop(key, None)

    def undo(self, doc: Document) -> None:
        layout = find_node(doc, self.layout_id)
        layout.class_name = self.old_class
        layout.attrib = dict(self.old_attrib)
        layout.body = list(self.old_body)
        for item in layout_items(layout):
            if item.id in self.old_items:
                item.attrib = dict(self.old_items[item.id])


def _morph_attribs(old: str, new: str, ordered: list) -> list[dict]:
    if new in ("QVBoxLayout", "QHBoxLayout"):
        return [{} for _item in ordered]
    if new == "QGridLayout":
        if old == "QHBoxLayout":
            return [{"row": "0", "column": str(i)} for i, _item in enumerate(ordered)]
        if old == "QFormLayout":
            result = []
            for item in ordered:
                spans = item.attrib.get("column") == "2" or int(item.attrib.get("colspan", "1") or 1) > 1
                attrib = {"row": item.attrib.get("row", "0"), "column": "0" if spans else item.attrib.get("column", "0")}
                if spans:
                    attrib["colspan"] = "2"
                result.append(attrib)
            return result
        return [{"row": str(i), "column": "0"} for i, _item in enumerate(ordered)]
    if new == "QFormLayout":
        result = []
        row = -1
        label_open = False
        for item in ordered:
            content = item_content(item)
            is_label = isinstance(content, Widget) and content.class_name == "QLabel"
            if is_label:
                row += 1
                result.append({"row": str(row), "column": "0"})
                label_open = True
            elif label_open:
                result.append({"row": str(row), "column": "1"})
                label_open = False
            else:
                row += 1
                spans = isinstance(content, Widget) and content.class_name in ("QDialogButtonBox", "QGroupBox", "QTabWidget")
                result.append({"row": str(row), "column": "0", "colspan": "2"} if spans else {"row": str(row), "column": "1"})
        return result
    return [dict(item.attrib) for item in ordered]


def morph_layout(doc: Document, layout_id: str, new_class: str):
    layout = find_node(doc, layout_id)
    if not isinstance(layout, Layout) or layout.class_name == new_class:
        return None
    return MorphLayout(layout_id, new_class)


class RemoveLayout:
    """Remove a widget's layout; its widgets stay as plain children. One undo step."""

    def __init__(self, owner_id: str):
        self.owner_id = owner_id
        self.saved: Optional[Layout] = None
        self.index = 0

    def redo(self, doc: Document) -> None:
        owner = find_node(doc, self.owner_id)
        layout = widget_layout(owner)
        if layout is None:
            return
        self.index = owner.body.index(layout)
        self.saved = layout
        owner.body.pop(self.index)
        for item in layout_items(layout):
            content = item_content(item)
            if isinstance(content, Widget):
                owner.body.append(content)

    def undo(self, doc: Document) -> None:
        if self.saved is None:
            return
        owner = find_node(doc, self.owner_id)
        moved = {id(item_content(item)) for item in layout_items(self.saved)}
        owner.body = [part for part in owner.body if id(part) not in moved]
        owner.body.insert(self.index, self.saved)
