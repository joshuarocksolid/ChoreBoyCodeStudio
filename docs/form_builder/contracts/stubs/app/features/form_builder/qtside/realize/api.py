"""Realize: model -> live widgets, kept in step by patches (CONTRACTS.md section 5).

Qt-side. Imports Qt only through ``app.qt`` (dune qt-portability). The stub
names Qt types under TYPE_CHECKING so it imports without Qt.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional, Tuple

from app.features.form_builder.engine.events import ChangeSet
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.session import FormSession

if TYPE_CHECKING:  # pragma: no cover
    from app.qt.QtCore import QObject
    from app.qt.QtWidgets import QLayout, QWidget

#: Dynamic Qt property set on every realized QObject (widget, layout, action).
NODE_ID_PROPERTY = "_cbcsNodeId"


@dataclass(frozen=True)
class PatchStats:
    """Per ChangeSet. ``fallback_rebuilds`` must be 0 for every command in the
    standard set (section 13); ``rebuilt_roots`` names subtrees that were rebuilt."""

    patched_properties: int
    reconciled_containers: int
    created_widgets: int
    destroyed_widgets: int
    fallback_rebuilds: int
    rebuilt_roots: Tuple[NodeId, ...]
    cpu_ms: float


class Realizer:
    """One per FormSession, created by the canvas.

    * ``build()`` creates the whole tree once (open, DocumentReplaced, fallback).
    * Subscribed to the log at PRIORITY_REALIZE; ``on_changeset`` patches:
      - PropertyChanged -> re-read the entry from the document and apply it to the
        live object (reset = apply the class-table default; volatile defaults are
        restored from a cached fresh instance of that class, created once per
        class, never per edit). Properties in REBUILD_PROPERTIES rebuild that node.
      - Node insert/remove/move -> collect ``structure_dirty`` containers; for each,
        top-down by depth: detach live children into a pool keyed by node id,
        re-attach in model order, construct only ids not in the pool, destroy
        pooled objects whose ids are in ``changeset.removed``.
      - FieldChanged on layoutitem cells/alignment, layout stretch fields ->
        reconcile that layout. ``class_name`` on a widget or layout -> rebuild
        that node's subtree, reusing child widgets.
      - FieldChanged ``object_name``/``name`` -> ``setObjectName`` and re-resolve
        buddies that name the old or new name.
      - Connections, tab stops, form slots, includes, custom-widget declarations:
        no widget change (the canvas never wires connections and never sets
        focus order); custom-widget ``extends`` changes rebuild users of the class.
      - DocumentReplaced -> ``build()``.
      Any exception inside a patch: log it, rebuild the nearest ancestor widget
      subtree (``fallback_rebuilds += 1``); if that fails, ``build()``.
    * Never connects ``<connections>``, never imports or executes user code,
      generated modules, ``*_rc.py`` files, or Designer plugins. Promoted widgets
      are realized as their ``extends`` class (stand-ins). ``:/`` resources come
      from ``compile_resource_tree`` registered with ``QResource.registerResourceData``.
    * Realized widgets never take focus or input: focus policy NoFocus,
      ``WA_TransparentForMouseEvents``; the canvas overlay receives all input. No
      per-widget event filters.
    * Removed objects are destroyed immediately (an ``app.qt`` immediate-delete
      helper), not with ``deleteLater``.
    """

    def __init__(self, session: FormSession) -> None:
        ...

    def build(self) -> "QWidget":
        """Budget: 90 ms CPU for a 300-widget form."""
        ...

    def on_changeset(self, changeset: ChangeSet) -> PatchStats:
        """Budget: 8 ms CPU for any single standard command on a 300-widget form."""
        ...

    @property
    def root_widget(self) -> "Optional[QWidget]":
        ...

    def widget_for(self, node_id: NodeId) -> "Optional[QWidget]":
        """O(1)."""
        ...

    def layout_for(self, node_id: NodeId) -> "Optional[QLayout]":
        """O(1)."""
        ...

    def object_for(self, node_id: NodeId) -> "Optional[QObject]":
        """Widget, layout, spacer item holder or action. O(1)."""
        ...

    def node_for(self, obj: "QObject") -> Optional[NodeId]:
        """Reads NODE_ID_PROPERTY; walks up parents for internal child widgets
        (a spin box's line edit). O(depth)."""
        ...

    def signature(self) -> Tuple[object, ...]:
        """Canonical description of the live tree (class, object name, parent,
        layout membership and cell, applied property values) used by the
        patch == rebuild property test."""
        ...

    def dispose(self) -> None:
        ...


#: ``(class, property)`` pairs whose change rebuilds the node instead of patching
#: in place. Empty by contract; a WP may add a pair only with a test showing the
#: in-place patch is wrong for it.
REBUILD_PROPERTIES: "frozenset" = frozenset()
