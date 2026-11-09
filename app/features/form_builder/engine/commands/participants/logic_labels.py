"""A rename keeps error labels pointing at the widget (CONTRACTS.md section 15.8).

``cbcsErrorLabel`` and ``cbcsErrorSummary`` hold one object name.
"""

from __future__ import annotations

from typing import FrozenSet, Optional, Tuple

from app.features.form_builder.engine.commands.ops import Op
from app.features.form_builder.engine.commands.participants import ParticipantRegistry
from app.features.form_builder.engine.commands.participants._logic_common import references, rewrite_ops
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.logic.storage import LABEL_KEYS
from app.features.form_builder.engine.ui4.document import UiDocument


class LogicLabelParticipant:
    participant_id = "logic_labels"

    def rename_ops(
        self,
        doc: UiDocument,
        renames: Tuple[Tuple[str, str], ...],
        scope: Optional[FrozenSet[NodeId]],
    ) -> Tuple[Op, ...]:
        mapping = {old: new for old, new in renames if old != new}
        if not mapping:
            return ()

        def rewrite(key: str, text: str) -> Optional[str]:
            if key in LABEL_KEYS:
                return mapping.get(text)
            return None

        return rewrite_ops(doc, scope, rewrite)

    def references(self, doc: UiDocument, name: str) -> Tuple[Tuple[NodeId, str], ...]:
        return references(doc, lambda key, text: key in LABEL_KEYS and text == name)


def register(registry: ParticipantRegistry) -> None:
    registry.add_rename(LogicLabelParticipant())
