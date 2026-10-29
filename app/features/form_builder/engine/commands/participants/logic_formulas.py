"""A rename keeps formulas pointing at the widget (CONTRACTS.md section 15.8, UX-LST-006).

``cbcsEnabledWhen``, ``cbcsVisibleWhen``, ``cbcsReadOnlyWhen``, ``cbcsValue``,
``cbcsDefault`` and the ``when``, ``formula``, ``default``, ``min`` and ``max``
strings inside the JSON properties are tokenized. Only a NAME token equal to the
old name changes, and only its own characters.
"""

from __future__ import annotations

from typing import FrozenSet, Optional, Tuple

from app.features.form_builder.engine.commands.ops import Op
from app.features.form_builder.engine.commands.participants import ParticipantRegistry
from app.features.form_builder.engine.commands.participants._logic_common import references, rewrite_ops
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.logic.refs import formula_mentions_in_logic, rename_formulas_in_logic
from app.features.form_builder.engine.ui4.document import UiDocument


class LogicFormulaParticipant:
    participant_id = "logic_formulas"

    def rename_ops(
        self,
        doc: UiDocument,
        renames: Tuple[Tuple[str, str], ...],
        scope: Optional[FrozenSet[NodeId]],
    ) -> Tuple[Op, ...]:
        mapping = {old: new for old, new in renames if old != new}
        if not mapping:
            return ()
        return rewrite_ops(doc, scope, lambda key, text: rename_formulas_in_logic(key, text, mapping))

    def references(self, doc: UiDocument, name: str) -> Tuple[Tuple[NodeId, str], ...]:
        return references(doc, lambda key, text: formula_mentions_in_logic(key, text, name))


def register(registry: ParticipantRegistry) -> None:
    registry.add_rename(LogicFormulaParticipant())
