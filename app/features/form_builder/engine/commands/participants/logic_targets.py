"""A rename keeps step targets pointing at the widget (CONTRACTS.md section 15.8, UX-LST-006).

The ``target`` of a ``slot`` step, and the object-name fields other verbs declare in
``engine.logic.refs.NAME_FIELDS``. The step-list property names (``cbcsOnClicked``)
are signal names and never change.
"""

from __future__ import annotations

from typing import FrozenSet, Optional, Tuple

from app.features.form_builder.engine.commands.ops import Op
from app.features.form_builder.engine.commands.participants import ParticipantRegistry
from app.features.form_builder.engine.commands.participants._logic_common import references, rewrite_ops
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.logic.refs import rename_step_targets, step_target_names
from app.features.form_builder.engine.logic.storage import is_signal_property
from app.features.form_builder.engine.ui4.document import UiDocument


def _rewrite(mapping: dict, key: str, text: str) -> Optional[str]:
    if not is_signal_property(key):
        return None
    return rename_step_targets(text, mapping)


class LogicTargetParticipant:
    participant_id = "logic_targets"

    def rename_ops(
        self,
        doc: UiDocument,
        renames: Tuple[Tuple[str, str], ...],
        scope: Optional[FrozenSet[NodeId]],
    ) -> Tuple[Op, ...]:
        mapping = {old: new for old, new in renames if old != new}
        if not mapping:
            return ()
        return rewrite_ops(doc, scope, lambda key, text: _rewrite(mapping, key, text))

    def references(self, doc: UiDocument, name: str) -> Tuple[Tuple[NodeId, str], ...]:
        return references(doc, lambda key, text: is_signal_property(key) and name in step_target_names(text))


def register(registry: ParticipantRegistry) -> None:
    registry.add_rename(LogicTargetParticipant())
