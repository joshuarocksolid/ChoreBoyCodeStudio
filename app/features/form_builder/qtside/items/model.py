"""Item drafts. One draft is the whole item list a session writes back.

Texts of a multi-column tree item are stored the way the file keeps them:
earlier columns are preserved property elements, and the last column is the
typed ``text`` property. Every other property on the item stays on the spec.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import List, Optional, Sequence, Tuple

from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.engine.ui4.opaque import OpaqueElement
from app.features.form_builder.engine.ui4.spec import NodeSpec, PropertyEntry
from app.features.form_builder.engine.ui4.values import StringValue, Value

ITEM_CLASSES = frozenset({"QComboBox", "QListWidget", "QTreeWidget", "QTableWidget"})
MODEL_CLASSES = frozenset({"QListView", "QTreeView", "QTableView", "QColumnView", "QUndoView"})
MODEL_VIEW_SENTENCE = (
    "This view gets its rows from your code. To type rows here, change it to a list widget (Change to)."
)
TREE_COLUMN_SENTENCE = "A tree needs at least one column."

_KINDS = {
    "QComboBox": "combo",
    "QListWidget": "list",
    "QTreeWidget": "tree",
    "QTableWidget": "table",
}


@dataclass(frozen=True)
class Item:
    texts: Tuple[str, ...]
    children: Tuple["Item", ...] = ()
    base: Optional[NodeSpec] = None
    id: Optional[NodeId] = None
    fields: Tuple[Tuple[str, object], ...] = ()

    def text_at(self, column: int) -> str:
        if column < 0 or column >= len(self.texts):
            return ""
        return self.texts[column]


@dataclass(frozen=True)
class Draft:
    kind: str
    name: str
    widget: NodeId
    items: Tuple[Item, ...] = ()
    columns: Tuple[Item, ...] = ()
    rows: Tuple[Item, ...] = ()
    cells: Tuple[Item, ...] = ()
    columns_stored: bool = False
    rows_stored: bool = False


def kind_of(class_name: str) -> Optional[str]:
    return _KINDS.get(class_name)


def load_draft(document: UiDocument, widget: NodeId) -> Optional[Draft]:
    node = document.get(widget)
    if not isinstance(node, WidgetNode):
        return None
    kind = kind_of(node.class_name)
    if kind is None:
        return None
    columns = tuple(_item_from_node(header) for header in node.children("columns"))
    rows = tuple(_item_from_node(header) for header in node.children("rows"))
    stored_columns = bool(columns)
    if kind == "tree" and not columns:
        columns = (_header("column", "Name"),)
    items = tuple(_item_from_node(child) for child in node.children("items"))
    cells: Tuple[Item, ...] = ()
    if kind == "table":
        cells = items
        items = ()
    return Draft(
        kind,
        node.object_name or kind,
        widget,
        items,
        columns,
        rows,
        cells,
        stored_columns,
        bool(rows),
    )


def summary(draft: Draft) -> str:
    if draft.kind == "tree":
        count = _count(draft.items)
        columns = max(1, len(draft.columns))
        return "%d rows in %d columns" % (count, columns)
    if draft.kind == "table":
        filled = sum(1 for cell in draft.cells if any(text for text in cell.texts))
        return "%d \u00d7 %d, %d cells filled" % (len(draft.rows), len(draft.columns), filled)
    texts = tuple(item.text_at(0) for item in draft.items if item.text_at(0))
    if not texts:
        return "No items"
    noun = "item" if len(draft.items) == 1 else "items"
    shown = ", ".join(item.text_at(0) for item in draft.items[:3])
    if len(draft.items) > 3:
        shown += "\u2026"
    return "%d %s: %s" % (len(draft.items), noun, shown)


def outline_caption(node: WidgetNode) -> str:
    """The words inside the outline's quotes for an item widget."""
    kind = kind_of(node.class_name)
    if kind is None:
        return ""
    if kind == "table":
        texts = [_column_texts(item)[0] for item in node.children("items") if _column_texts(item)[:1] and _column_texts(item)[0]]
    elif kind == "tree":
        texts = [item.text_at(0) for item in _top_items(node) if item.text_at(0)]
    else:
        texts = [_column_texts(item)[0] for item in node.children("items") if _column_texts(item)[:1]]
    if not texts:
        return ""
    shown = ", ".join(texts[:3])
    if len(texts) > 3:
        shown += ", \u2026"
    return shown


def _top_items(node: WidgetNode) -> Tuple[Item, ...]:
    return tuple(_item_from_node(child) for child in node.children("items"))


def commit_slots(draft: Draft) -> Tuple[Optional[Tuple[NodeSpec, ...]], Optional[Tuple[NodeSpec, ...]], Optional[Tuple[NodeSpec, ...]]]:
    """``(items, rows, columns)``. None leaves that slot alone."""
    if draft.kind == "table":
        return (
            tuple(_spec_from_item(cell) for cell in draft.cells),
            tuple(_spec_from_item(row) for row in draft.rows) if draft.rows_stored or draft.rows else (),
            tuple(_spec_from_item(column) for column in draft.columns) if draft.columns_stored or draft.columns else (),
        )
    columns: Optional[Tuple[NodeSpec, ...]] = None
    if draft.kind == "tree" and (draft.columns_stored or any(item.id is not None or item.text_at(0) != "Name" for item in draft.columns)):
        columns = tuple(_spec_from_item(column) for column in draft.columns)
    return tuple(_spec_from_item(item) for item in draft.items), None, columns


def column_count(draft: Draft) -> int:
    if draft.kind == "tree":
        return max(1, len(draft.columns))
    if draft.kind == "table":
        return len(draft.columns)
    return 1


def set_text(draft: Draft, path: Tuple[int, ...], column: int, text: str) -> Draft:
    return replace(draft, items=_map_items(draft.items, path, lambda item: _set_column(item, column, text)))


def set_cell_text(draft: Draft, row: int, column: int, text: str) -> Draft:
    """An emptied cell with nothing else on it leaves the file, as in Designer."""
    cells = list(draft.cells)
    found = _cell_index(cells, row, column)
    if found is None:
        if not text:
            return draft
        cells.append(Item(texts=(text,), fields=(("row", row), ("column", column))))
    elif not text and _bare(cells[found]):
        del cells[found]
    else:
        cells[found] = _set_column(cells[found], 0, text)
    return replace(draft, cells=tuple(cells))


def _bare(cell: Item) -> bool:
    base = cell.base
    if base is None:
        return True
    others = [entry for entry in base.properties if entry.name != "text"]
    return not others and not base.attributes and not base.children("opaque")


def clear_cell(draft: Draft, row: int, column: int) -> Draft:
    return set_cell_text(draft, row, column, "")


def paste_cells(draft: Draft, row: int, column: int, grid: Sequence[Sequence[str]]) -> Draft:
    current = draft
    for r, line in enumerate(grid):
        for c, text in enumerate(line):
            current = set_cell_text(current, row + r, column + c, text)
            current = _grow_table(current, row + r + 1, column + c + 1)
    return current


def add_sibling(draft: Draft, path: Tuple[int, ...]) -> Tuple[Draft, Tuple[int, ...]]:
    parent, index = _parent_list(draft.items, path)
    inserted = list(parent)
    at = index + 1
    inserted.insert(at, Item(texts=("",) * max(1, column_count(draft))))
    items = _put_list(draft.items, path[:-1], tuple(inserted))
    return replace(draft, items=items), path[:-1] + (at,)


def add_root(draft: Draft) -> Tuple[Draft, Tuple[int, ...]]:
    items = draft.items + (Item(texts=("",) * max(1, column_count(draft))),)
    return replace(draft, items=items), (len(items) - 1,)


def delete_at(draft: Draft, path: Tuple[int, ...]) -> Draft:
    parent, index = _parent_list(draft.items, path)
    if index < 0 or index >= len(parent):
        return draft
    kept = parent[:index] + parent[index + 1 :]
    return replace(draft, items=_put_list(draft.items, path[:-1], kept))


def move_sibling(draft: Draft, path: Tuple[int, ...], delta: int) -> Tuple[Draft, Tuple[int, ...]]:
    parent, index = _parent_list(draft.items, path)
    target = index + delta
    if target < 0 or target >= len(parent):
        return draft, path
    items = list(parent)
    items[index], items[target] = items[target], items[index]
    return replace(draft, items=_put_list(draft.items, path[:-1], tuple(items))), path[:-1] + (target,)


def nest(draft: Draft, path: Tuple[int, ...]) -> Tuple[Draft, Tuple[int, ...]]:
    """Move the item under the previous sibling, children included."""
    parent, index = _parent_list(draft.items, path)
    if index <= 0:
        return draft, path
    items = list(parent)
    moved = items.pop(index)
    previous = items[index - 1]
    items[index - 1] = replace(previous, children=previous.children + (moved,))
    new_path = path[:-1] + (index - 1, len(previous.children))
    return replace(draft, items=_put_list(draft.items, path[:-1], tuple(items))), new_path


def unnest(draft: Draft, path: Tuple[int, ...]) -> Tuple[Draft, Tuple[int, ...]]:
    if len(path) < 2:
        return draft, path
    parent_path = path[:-1]
    parent_items, parent_index = _parent_list(draft.items, parent_path)
    parent = parent_items[parent_index]
    index = path[-1]
    if index < 0 or index >= len(parent.children):
        return draft, path
    moved = parent.children[index]
    parent_items_list = list(parent_items)
    parent_items_list[parent_index] = replace(parent, children=parent.children[:index] + parent.children[index + 1 :])
    grand_path = parent_path[:-1]
    inserted = list(parent_items_list)
    at = parent_index + 1
    inserted.insert(at, moved)
    items = _put_list(draft.items, grand_path, tuple(inserted))
    return replace(draft, items=items), grand_path + (at,)


def set_item_value(draft: Draft, path: Tuple[int, ...], name: str, value: Optional[Value]) -> Draft:
    return replace(draft, items=_map_items(draft.items, path, lambda item: _with_value(item, name, value)))


def set_header_text(draft: Draft, axis: str, index: int, text: str) -> Draft:
    slot = draft.columns if axis == "column" else draft.rows
    items = list(slot)
    while len(items) <= index:
        items.append(_header(axis))
    items[index] = _set_column(items[index], 0, text)
    if axis == "column":
        return replace(draft, columns=tuple(items), columns_stored=True)
    return replace(draft, rows=tuple(items), rows_stored=True)


def delete_header(draft: Draft, axis: str, index: int) -> Draft:
    slot = list(draft.columns if axis == "column" else draft.rows)
    if index < 0 or index >= len(slot):
        return draft
    if axis == "column" and draft.kind == "tree" and len(slot) <= 1:
        return draft
    del slot[index]
    if axis == "column":
        cells = tuple(cell for cell in draft.cells if _field_int(cell, "column") != index)
        cells = tuple(_shift_field(cell, "column", index) for cell in cells)
        return replace(draft, columns=tuple(slot), columns_stored=True, cells=cells)
    cells = tuple(cell for cell in draft.cells if _field_int(cell, "row") != index)
    cells = tuple(_shift_field(cell, "row", index) for cell in cells)
    return replace(draft, rows=tuple(slot), rows_stored=True, cells=cells)


def move_header(draft: Draft, axis: str, index: int, delta: int) -> Draft:
    slot = list(draft.columns if axis == "column" else draft.rows)
    target = index + delta
    if target < 0 or target >= len(slot):
        return draft
    slot[index], slot[target] = slot[target], slot[index]
    if axis == "column":
        return replace(draft, columns=tuple(slot), columns_stored=True)
    return replace(draft, rows=tuple(slot), rows_stored=True)


def add_header(draft: Draft, axis: str, index: int) -> Draft:
    slot = list(draft.columns if axis == "column" else draft.rows)
    at = index + 1
    slot.insert(at, _header(axis))
    if axis == "column":
        return replace(draft, columns=tuple(slot), columns_stored=True)
    return replace(draft, rows=tuple(slot), rows_stored=True)


def flat_paths(items: Sequence[Item], prefix: Tuple[int, ...] = ()) -> Tuple[Tuple[Tuple[int, ...], Item], ...]:
    found: List[Tuple[Tuple[int, ...], Item]] = []
    for index, item in enumerate(items):
        path = prefix + (index,)
        found.append((path, item))
        found.extend(flat_paths(item.children, path))
    return tuple(found)


def item_at(items: Sequence[Item], path: Tuple[int, ...]) -> Item:
    node = items[path[0]]
    for index in path[1:]:
        node = node.children[index]
    return node


def _count(items: Sequence[Item]) -> int:
    return sum(1 + _count(item.children) for item in items)


def _item_from_node(node: object) -> Item:
    spec = node.to_spec()  # type: ignore[attr-defined]
    children = ()
    if getattr(node, "kind", "") == "item":
        children = tuple(_item_from_node(child) for child in node.children("subitems"))  # type: ignore[attr-defined]
    return Item(_column_texts(node), children, spec, node.id, spec.fields)  # type: ignore[attr-defined]


def _column_texts(node: object) -> Tuple[str, ...]:
    spec = node.to_spec() if hasattr(node, "to_spec") else node
    return _texts_of_spec(spec)  # type: ignore[arg-type]


def _texts_of_spec(spec: NodeSpec) -> Tuple[str, ...]:
    typed = [entry.value.text for entry in spec.properties if entry.name == "text" and isinstance(entry.value, StringValue)]
    if len(typed) > 1:
        return tuple(typed)
    earlier: List[str] = []
    for child in spec.children("opaque"):
        element = child.field("element")
        if not isinstance(element, OpaqueElement):
            continue
        if element.tag != "property" or dict(element.attrs).get("name") != "text":
            continue
        text = _opaque_text(element)
        if text is not None:
            earlier.append(text)
    if typed:
        return tuple(earlier + typed)
    if earlier:
        return tuple(earlier)
    return ("",)


def _opaque_text(element: OpaqueElement) -> Optional[str]:
    for child in element.children:
        if isinstance(child, OpaqueElement) and child.tag == "string":
            return "".join(part for part in child.children if isinstance(part, str))
    return None


def _properties_with_texts(base: NodeSpec, texts: Tuple[str, ...]) -> Tuple[PropertyEntry, ...]:
    others = tuple(entry for entry in base.properties if entry.name != "text")
    values = texts or ("",)
    old = next((entry for entry in base.properties if entry.name == "text" and isinstance(entry.value, StringValue)), None)
    built: List[PropertyEntry] = []
    # Earlier columns travel as opaque elements, added by the caller via slots.
    # The typed property is the last column so codegen and the writer agree.
    last = values[-1]
    if old is not None and len(values) == 1:
        value = StringValue(last, old.value.notr, old.value.comment, old.value.extracomment, old.value.id)
        built.append(PropertyEntry("property", "text", value, old.stdset, old.extra_attrs))
    else:
        built.append(PropertyEntry("property", "text", StringValue(last)))
    return tuple(built) + others


def _spec_from_item(item: Item) -> NodeSpec:
    return _spec_with_earlier_texts(item)


def _spec_with_earlier_texts(item: Item) -> NodeSpec:
    base = item.base or NodeSpec("item")
    kind = base.kind if base.kind in ("item", "header") else "item"
    if item.fields and base.kind == "header":
        kind = "header"
    if base.kind == "header":
        kind = "header"
    texts = item.texts or ("",)
    properties = _properties_with_texts(base, texts)
    opaque = _opaque_with_texts(base.children("opaque"), texts[:-1])
    slots_rest = tuple((name, kids) for name, kids in base.slots if name not in ("subitems", "opaque"))
    slots: List[Tuple[str, Tuple[NodeSpec, ...]]] = list(slots_rest)
    if opaque:
        slots.append(("opaque", opaque))
    children = tuple(_spec_with_earlier_texts(child) for child in item.children)
    if children:
        slots.append(("subitems", children))
    fields = item.fields if item.fields else base.fields
    return NodeSpec(kind, item.id, fields, properties, base.attributes, tuple(slots), base.extra_attrs)


def _opaque_with_texts(kept: Sequence[NodeSpec], earlier: Sequence[str]) -> Tuple[NodeSpec, ...]:
    """Put the earlier column texts back where the file had them.

    Each column's own properties (a column tooltip, say) follow that column's
    text in the file, so the k-th stored text is rewritten in place and the
    elements after it stay with it. New columns go at the end.
    """
    out: List[NodeSpec] = []
    used = 0
    for child in kept:
        if not _is_text_opaque(child):
            out.append(child)
            continue
        if used < len(earlier):
            out.append(_retext_opaque(child, earlier[used]))
            used += 1
    out.extend(_text_opaque(text) for text in earlier[used:])
    return tuple(out)


def _retext_opaque(spec: NodeSpec, text: str) -> NodeSpec:
    element = spec.field("element")
    if not isinstance(element, OpaqueElement) or _opaque_text(element) == text:
        return spec
    children = tuple(
        replace(child, children=(text,)) if isinstance(child, OpaqueElement) and child.tag == "string" else child
        for child in element.children
    )
    fields = tuple((key, replace(element, children=children) if key == "element" else value) for key, value in spec.fields)
    return replace(spec, fields=fields)


def _text_opaque(text: str) -> NodeSpec:
    element = OpaqueElement("property", (("name", "text"),), (OpaqueElement("string", (), (text,)),))
    return NodeSpec("opaque", None, (("element", element), ("anchor", ("properties", 0))))


def _is_text_opaque(spec: NodeSpec) -> bool:
    element = spec.field("element")
    return isinstance(element, OpaqueElement) and element.tag == "property" and dict(element.attrs).get("name") == "text"


def _header(axis: str, text: str = "") -> Item:
    fields = (("axis", axis),)
    return Item(texts=(text,), base=NodeSpec("header", None, fields), fields=fields)


def _set_column(item: Item, column: int, text: str) -> Item:
    texts = list(item.texts or ("",))
    while len(texts) <= column:
        texts.append("")
    texts[column] = text
    return replace(item, texts=tuple(texts))


def _with_value(item: Item, name: str, value: Optional[Value]) -> Item:
    base = item.base or NodeSpec("item")
    props = tuple(entry for entry in base.properties if entry.name != name)
    if value is not None:
        props = props + (PropertyEntry("property", name, value),)
    return replace(item, base=replace(base, properties=props))


def _map_items(items: Tuple[Item, ...], path: Tuple[int, ...], edit: object) -> Tuple[Item, ...]:
    if not path:
        return items
    found = list(items)
    index = path[0]
    if index < 0 or index >= len(found):
        return items
    if len(path) == 1:
        found[index] = edit(found[index])  # type: ignore[operator]
        return tuple(found)
    found[index] = replace(found[index], children=_map_items(found[index].children, path[1:], edit))
    return tuple(found)


def _parent_list(items: Tuple[Item, ...], path: Tuple[int, ...]) -> Tuple[Tuple[Item, ...], int]:
    if len(path) <= 1:
        return items, path[0] if path else 0
    parent = item_at(items, path[:-1])
    return parent.children, path[-1]


def _put_list(items: Tuple[Item, ...], path: Tuple[int, ...], kids: Tuple[Item, ...]) -> Tuple[Item, ...]:
    if not path:
        return kids
    return _map_items(items, path, lambda item: replace(item, children=kids))


def _cell_index(cells: Sequence[Item], row: int, column: int) -> Optional[int]:
    for index, cell in enumerate(cells):
        if _field_int(cell, "row") == row and _field_int(cell, "column") == column:
            return index
    return None


def _field_int(item: Item, name: str) -> int:
    for key, value in item.fields:
        if key == name and isinstance(value, int) and not isinstance(value, bool):
            return value
    return -1


def _shift_field(cell: Item, name: str, removed: int) -> Item:
    fields = []
    for key, value in cell.fields:
        if key == name and isinstance(value, int) and value > removed:
            fields.append((key, value - 1))
        else:
            fields.append((key, value))
    return replace(cell, fields=tuple(fields))


def _grow_table(draft: Draft, rows: int, columns: int) -> Draft:
    current = draft
    while len(current.rows) < rows:
        current = add_header(current, "row", len(current.rows) - 1 if current.rows else -1)
    while len(current.columns) < columns:
        current = add_header(current, "column", len(current.columns) - 1 if current.columns else -1)
    return current


Origin = Tuple[Optional[int], ...]


def rows_from_list(draft: Draft, texts: Sequence[str], origin: Origin) -> Draft:
    """Combo or list items after a list-editor change. Each item keeps its details."""
    old = draft.items
    items = []
    for text, source in zip(texts, origin):
        if source is not None and 0 <= source < len(old):
            items.append(_set_column(old[source], 0, text))
        else:
            items.append(Item(texts=(text,)))
    return replace(draft, items=tuple(items))


def headers_from_list(draft: Draft, axis: str, texts: Sequence[str], origin: Origin) -> Draft:
    """Rows or columns after a list-editor change. Cells and column texts follow their header."""
    old = draft.columns if axis == "column" else draft.rows
    headers = []
    for text, source in zip(texts, origin):
        if source is not None and 0 <= source < len(old):
            headers.append(_set_column(old[source], 0, text))
        else:
            headers.append(_set_column(_header(axis), 0, text))
    new_at = {source: index for index, source in enumerate(origin) if source is not None}
    shift = len(texts) - len(old)
    if axis == "column":
        draft = replace(draft, columns=tuple(headers), columns_stored=True)
    else:
        draft = replace(draft, rows=tuple(headers), rows_stored=True)
    if tuple(origin) == tuple(range(len(old))):
        return draft
    if draft.kind == "tree" and axis == "column":
        return replace(draft, items=_permute_columns(draft.items, origin))
    cells = []
    for cell in draft.cells:
        at = _field_int(cell, axis)
        if at < 0:
            cells.append(cell)
            continue
        if at >= len(old):
            cells.append(_with_field(cell, axis, at + shift))
            continue
        if at not in new_at:
            continue
        cells.append(_with_field(cell, axis, new_at[at]))
    return replace(draft, cells=tuple(cells))


def _permute_columns(items: Tuple[Item, ...], origin: Origin) -> Tuple[Item, ...]:
    moved = []
    for item in items:
        texts = [item.text_at(source) if source is not None else "" for source in origin]
        while len(texts) > max(1, len(item.texts)) and texts[-1] == "":
            texts.pop()
        moved.append(replace(item, texts=tuple(texts) or ("",), children=_permute_columns(item.children, origin)))
    return tuple(moved)


def _with_field(cell: Item, name: str, value: int) -> Item:
    fields = tuple((key, value if key == name else old) for key, old in cell.fields)
    return replace(cell, fields=fields)


def delete_row(draft: Draft, path: Tuple[int, ...]) -> Tuple[Draft, Tuple[int, ...]]:
    """Delete a tree row with its children. Focus goes to the row above, or the next one."""
    parent, index = _parent_list(draft.items, path)
    if index < 0 or index >= len(parent):
        return draft, path
    gone = delete_at(draft, path)
    if index > 0:
        return gone, path[:-1] + (index - 1,)
    if len(parent) > 1:
        return gone, path
    return gone, path[:-1]


def is_blank(item: Item) -> bool:
    """No text, no children and nothing else on it: a row the user added and left empty."""
    if any(text for text in item.texts) or item.children:
        return False
    base = item.base
    if base is None:
        return True
    others = [entry for entry in base.properties if entry.name != "text"]
    return not others and not base.attributes and not base.children("opaque")


def trim_blank_tail(items: Tuple[Item, ...]) -> Tuple[Item, ...]:
    """Drop empty rows at the end of each level, as Done does for a list."""
    kept = [replace(item, children=trim_blank_tail(item.children)) for item in items]
    while kept and is_blank(kept[-1]):
        kept.pop()
    return tuple(kept)
