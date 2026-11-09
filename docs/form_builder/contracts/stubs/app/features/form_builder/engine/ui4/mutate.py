"""Mutation primitives. PRIVATE (CONTRACTS.md sections 2.6 and 3.3).

Only ``engine/commands/log.py``, ``engine/commands/context.py`` and
``engine/ui4/reader.py`` may import this module (dune file role
``form_builder.mutate_guard``). Every other module changes a document through
the command log.

Each primitive applies one op, keeps the id index, parent map, name index and
per-node property maps consistent, bumps ``UiDocument.revision`` by one, and
returns the exact inverse op. ``apply(doc, op)`` followed by
``apply(doc, inverse)`` leaves ``doc.fingerprint()`` unchanged (section 13).
Each primitive validates its preconditions and raises ``OpError`` before
changing anything, so a failed primitive leaves the document untouched.
"""

from __future__ import annotations

from app.features.form_builder.engine.commands.ops import Op
from app.features.form_builder.engine.ui4.document import UiDocument


class OpError(ValueError):
    """An op's precondition failed (unknown id, wrong slot, index out of range,
    kind not accepted by slot, duplicate id, single-child slot occupied,
    moving a node into its own subtree). Raised before any change."""


def apply(doc: UiDocument, op: Op) -> Op:
    """Apply ``op`` and return its inverse. O(changed): O(1) for property and
    field ops, O(subtree) for insert/remove (index maintenance), O(siblings) for
    list splicing, O(form) only for ReplaceRootOp."""
    ...
