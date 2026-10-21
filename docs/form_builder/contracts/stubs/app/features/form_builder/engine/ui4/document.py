"""The document: node index and read-only queries (CONTRACTS.md section 2).

Complexities are part of the contract (section 12).
"""

from __future__ import annotations

from typing import FrozenSet, Iterator, Literal, Optional, Tuple

from app.features.form_builder.engine.ids import DOCUMENT_ID, NodeId
from app.features.form_builder.engine.ui4.nodes import (
    LayoutNode,
    Node,
    WidgetNode,
)
from app.features.form_builder.engine.ui4.spec import NodeSpec

EnumStyle = Literal["short", "qualified"]


class InvariantError(AssertionError):
    """A model-integrity invariant failed. Always a bug; never a user error."""


class UiDocument:
    """One form. Created by the reader (``engine.ui4.reader.read_ui``) or by
    ``UiDocument.from_spec``; mutated only by ``engine.ui4.mutate`` primitives,
    which the command log calls.

    ``revision`` increases by one for every primitive op applied (do, undo and
    redo all increase it). It is the cache key for lazy serialization, the hit
    index and diagnostics. It is not the undo position.
    """

    @classmethod
    def from_spec(cls, spec: NodeSpec) -> "UiDocument":
        """Build a document from a ``ui`` spec whose ids are all set and unique."""
        ...

    # ------------------------------------------------------------- identity
    @property
    def revision(self) -> int:
        ...

    @property
    def ui(self) -> Node:
        """The ``ui`` node (id DOCUMENT_ID)."""
        ...

    @property
    def root(self) -> WidgetNode:
        """The form's root widget. A document always has one (reader enforces)."""
        ...

    def node(self, node_id: NodeId) -> Node:
        """O(1). KeyError when absent."""
        ...

    def get(self, node_id: NodeId) -> Optional[Node]:
        """O(1). None when absent."""
        ...

    def contains(self, node_id: NodeId) -> bool:
        """O(1)."""
        ...

    def parent(self, node_id: NodeId) -> Optional[Node]:
        """O(1)."""
        ...

    def ancestors(self, node_id: NodeId) -> Tuple[NodeId, ...]:
        """Parent first, ``ui`` last. O(depth)."""
        ...

    def is_ancestor(self, ancestor: NodeId, node_id: NodeId) -> bool:
        """True when ``ancestor`` is a strict ancestor. O(depth)."""
        ...

    def depth(self, node_id: NodeId) -> int:
        """``ui`` is 0, root widget 1. O(depth)."""
        ...

    # ---------------------------------------------------------------- names
    def by_name(self, name: str) -> Tuple[NodeId, ...]:
        """Widgets, layouts, spacers, actions, action groups and button groups whose
        name is ``name``, in document order. More than one means a duplicate
        (FB010). O(k)."""
        ...

    def names(self) -> FrozenSet[str]:
        """Every name in the shared object-name namespace. O(1) (maintained)."""
        ...

    def unique_name(self, base: str) -> str:
        """``base`` if free, else ``base_2``, ``base_3``... (Designer's rule). The
        first free suffix wins. Deterministic. O(k) in the number of collisions."""
        ...

    def form_class_name(self) -> str:
        """``<class>`` text, else the root widget's object name, else ``Form``."""
        ...

    # ------------------------------------------------------------ traversal
    def iter_preorder(self, start: NodeId = DOCUMENT_ID) -> Iterator[Node]:
        """Pre-order, schema slot order, explicit stack (no recursion). O(subtree)."""
        ...

    def iter_widgets(self) -> Iterator[WidgetNode]:
        """Every widget, document order. O(form)."""
        ...

    def layout_of(self, widget_id: NodeId) -> Optional[LayoutNode]:
        """O(1)."""
        ...

    def owning_widget(self, node_id: NodeId) -> Optional[WidgetNode]:
        """Nearest widget ancestor-or-self that owns ``node_id`` visually: for a
        widget, itself; for a layout/item/spacer, the widget whose layout tree
        contains it. O(depth)."""
        ...

    def containing_layout_item(self, node_id: NodeId) -> Optional[NodeId]:
        """The layout item whose ``content`` is ``node_id``, or None. O(1)."""
        ...

    # ---------------------------------------------------------- form-level
    def tabstops(self) -> Optional[Tuple[str, ...]]:
        """``<tabstops>`` names, or None when the element is absent."""
        ...

    def connections(self) -> Tuple[Node, ...]:
        """ConnectionNodes in document order."""
        ...

    def custom_widget(self, class_name: str) -> Optional[Node]:
        """The ``<customwidget>`` declaring ``class_name``. O(1)."""
        ...

    def enum_style(self) -> EnumStyle:
        """Spelling used for new enum/set values: "qualified" when most enum texts in
        the document name the enum type (``Qt::Orientation::Horizontal``), else
        "short". Ties and documents without enums use ``DEFAULT_ENUM_STYLE``.
        Recomputed lazily per revision."""
        ...

    def logic_version(self) -> Optional[int]:
        """``cbcsLogic`` on the root, or None."""
        ...

    # ------------------------------------------------------------- checking
    def fingerprint(self) -> str:
        """sha256 hex of a canonical encoding of the whole tree INCLUDING ids.
        Used by replay and undo tests. O(form)."""
        ...

    def structure_fingerprint(self) -> str:
        """Same, with ids excluded. Equal for two documents read from the same text."""
        ...

    def validate(self) -> None:
        """Check every integrity invariant (CONTRACTS.md section 2.7); raise
        InvariantError naming the first violation. O(form). Called after every
        log entry when ``CBCS_FB_VALIDATE=1`` (always on in tests)."""
        ...

    def to_spec(self) -> NodeSpec:
        """Frozen snapshot of the whole document (the ``ui`` spec)."""
        ...


#: Enum spelling for a document with no enum values. Set from the M0.4b
#: Designer-resave corpus (what Designer 6.8 writes for a fresh form).
DEFAULT_ENUM_STYLE: EnumStyle = "qualified"
