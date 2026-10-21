"""Immutable node descriptions (CONTRACTS.md sections 2.2 and 3.3).

``NodeSpec`` is the frozen, hashable, JSON-able description of a node subtree.
It is used wherever a subtree crosses a boundary:

* InsertNodeOp carries the subtree it inserts; RemoveNodeOp's inverse carries
  a snapshot of the subtree it removed. Undo and redo rebuild live nodes from
  specs, so no live node object is ever shared between the document and the
  undo history.
* Clipboard, duplicate, palette templates and paste use specs with
  ``id=None``; the planner assigns ids.
* ``ReplaceRootOp`` carries a whole ``ui`` spec.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.ui4.values import Value


@dataclass(frozen=True)
class PropertyEntry:
    """One ``<property>`` or ``<attribute>`` element.

    ``stdset``: the raw ``stdset`` attribute text or None when absent. A dynamic
    property is ``stdset="0"``; Designer writes exactly that.
    ``extra_attrs``: unknown attributes in input order.
    Identity on a node is ``(kind, name)``. The last copy is the typed entry
    (Qt last-wins). Earlier copies become opaque at that same position (FB007).
    """

    kind: str  # "property" | "attribute"
    name: str
    value: Value
    stdset: Optional[str] = None
    extra_attrs: Tuple[Tuple[str, str], ...] = ()

    @property
    def is_dynamic(self) -> bool:
        """True when ``stdset == "0"``."""
        return self.stdset == "0"


@dataclass(frozen=True)
class NodeSpec:
    """A node and its subtree.

    ``fields``: ``(field_name, value)`` pairs in the schema's field order, only
    fields that are not None.
    ``properties`` and ``attributes``: in document order.
    ``slots``: ``(slot_name, children)`` pairs in the schema's slot order, only
    non-empty slots.
    ``id``: None in templates and fragments; always set inside a document and in
    op payloads.
    """

    kind: str
    id: Optional[NodeId] = None
    fields: Tuple[Tuple[str, object], ...] = ()
    properties: Tuple[PropertyEntry, ...] = ()
    attributes: Tuple[PropertyEntry, ...] = ()
    slots: Tuple[Tuple[str, Tuple["NodeSpec", ...]], ...] = ()
    extra_attrs: Tuple[Tuple[str, str], ...] = ()

    def field(self, name: str) -> object:
        """Field value or None."""
        for key, value in self.fields:
            if key == name:
                return value
        return None

    def children(self, slot: str) -> Tuple["NodeSpec", ...]:
        """Children in ``slot`` (empty tuple when absent)."""
        for key, kids in self.slots:
            if key == slot:
                return kids
        return ()

    def iter_subtree(self) -> Tuple["NodeSpec", ...]:
        """This spec and every descendant spec, pre-order, slot order."""
        found = [self]
        for _name, kids in self.slots:
            for kid in kids:
                found.extend(kid.iter_subtree())
        return tuple(found)

    def ids(self) -> Tuple[NodeId, ...]:
        """Every non-None id in the subtree, pre-order."""
        return tuple(spec.id for spec in self.iter_subtree() if spec.id is not None)


@dataclass(frozen=True)
class Fragment:
    """A pasteable ``.ui`` fragment: the clipboard and palette format.

    ``nodes``: top-level specs with ``id=None`` throughout.
    ``connections``: connections whose sender and receiver are both inside
    ``nodes`` (kept on copy; others are dropped, as Designer does).
    ``customwidgets``/``resources``: declarations the nodes need; paste merges
    them by class name / location.
    ``xml``: the fragment serialised as a ``<ui>`` document with a ``QWidget``
    root holding ``nodes`` (the cross-process clipboard text, MIME
    ``application/x-cbcs-form-fragment`` plus ``text/plain``).
    """

    nodes: Tuple[NodeSpec, ...]
    connections: Tuple[NodeSpec, ...] = ()
    customwidgets: Tuple[NodeSpec, ...] = ()
    resources: Tuple[NodeSpec, ...] = ()
