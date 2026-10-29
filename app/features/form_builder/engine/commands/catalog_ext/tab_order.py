"""Tab order and buddy commands (UX-OVL-005, UX-OVL-006, UX-OVL-008, UX-MODE-002 .. 004).

``ChangeTabOrder`` writes ``<tabstops>`` (None removes it). ``SetLabelBuddy`` and
``PairLabels`` write the ``buddy`` property. ``join_order`` is what an insert
calls so new inputs join a custom order where they sit on the form and are not
appended (pain 20, UX-OVL-006). Nothing here touches Qt.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Hashable, Optional, Sequence, Tuple

from app.features.form_builder.engine.commands import planning
from app.features.form_builder.engine.commands.base import PlanContext
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.query import tab_stops as q
from app.features.form_builder.engine.query.tree import reading_order, splice_tab_order, takes_tab_focus
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import WidgetNode

USE_READING_ORDER = "Use reading order"
CHANGE_TAB_ORDER = "Change tab order"
PAIR_LABELS = "Pair labels"


def register(registry: object) -> None:
    add = getattr(registry, "add", None)
    if add is None:
        return
    add(ChangeTabOrder)
    add(SetLabelBuddy)
    add(PairLabels)


@dataclass(frozen=True)
class ChangeTabOrder:
    """Write the tab order. ``names`` None goes back to the reading order. One ``merge_token`` is one overlay session."""

    command_type: ClassVar[str] = "change_tab_order"
    names: Optional[Tuple[str, ...]]
    merge_token: Optional[str] = None

    @property
    def label(self) -> str:
        return USE_READING_ORDER if self.names is None else CHANGE_TAB_ORDER

    def merge_key(self) -> Optional[Hashable]:
        return ("change_tab_order", self.merge_token) if self.merge_token else None

    def apply(self, doc: UiDocument, ctx: PlanContext) -> None:
        planning.set_tabstops(doc, ctx, self.names)


@dataclass(frozen=True)
class SetLabelBuddy:
    """Set (or clear, with ``target`` None) a label's buddy. ``caption`` is the label's words for the undo name."""

    command_type: ClassVar[str] = "set_label_buddy"
    label_widget: NodeId
    target: Optional[str]
    caption: str = ""
    merge_token: Optional[str] = None

    @property
    def label(self) -> str:
        return "Set buddy of %s" % self.caption if self.caption else "Set buddy"

    def merge_key(self) -> Optional[Hashable]:
        return None

    def apply(self, doc: UiDocument, ctx: PlanContext) -> None:
        planning.set_buddy(doc, ctx, self.label_widget, self.target)


@dataclass(frozen=True)
class PairLabels:
    """Give each label in ``pairs`` the field of its row as buddy, when it has none. Returns how many were set."""

    command_type: ClassVar[str] = "pair_labels"
    pairs: Tuple[Tuple[NodeId, str], ...]
    merge_token: Optional[str] = None

    @property
    def label(self) -> str:
        return PAIR_LABELS

    def merge_key(self) -> Optional[Hashable]:
        return None

    def apply(self, doc: UiDocument, ctx: PlanContext) -> int:
        paired = 0
        for label_id, target in self.pairs:
            if q.buddy_of(doc, label_id):
                continue
            planning.set_buddy(doc, ctx, label_id, target)
            paired += 1
        return paired


def join_order(doc: UiDocument, ctx: PlanContext, scope: Sequence[NodeId]) -> None:
    """After an insert: new inputs join a custom order by reading position (pain 20).

    Does nothing while the form follows its reading order, because then the new
    widgets already sit where they belong.
    """
    saved = doc.tabstops()
    if saved is None:
        return
    fresh = []
    for node_id in scope:
        node = doc.get(node_id)
        if isinstance(node, WidgetNode) and node.object_name and takes_tab_focus(node):
            fresh.append(node.object_name)
    if not fresh:
        return
    alive = doc.names()
    order = tuple(name for name in saved if name in alive)
    joined = splice_tab_order(order, reading_order(doc), tuple(fresh))
    if joined != tuple(saved):
        planning.set_tabstops(doc, ctx, joined)
