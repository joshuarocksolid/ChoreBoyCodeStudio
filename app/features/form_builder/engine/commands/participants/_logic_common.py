"""Shared walk for the logic participants (CONTRACTS.md section 15.8).

A participant rewrites one ``cbcs*`` text at a time with ``SetPropertyOp``, keeps the
entry's ``stdset`` and attributes, and does nothing at all while the form's logic is
read-only (FB402): that text is written back exactly as it was read.
"""

from __future__ import annotations

from typing import Callable, FrozenSet, Iterator, Optional, Tuple

from app.features.form_builder.engine.commands.ops import Op, SetPropertyOp
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.logic.codec import marker_read_only
from app.features.form_builder.engine.logic.storage import is_user_logic_key
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.spec import PropertyEntry
from app.features.form_builder.engine.ui4.values import StringValue


def logic_texts(
    doc: UiDocument,
    scope: Optional[FrozenSet[NodeId]],
    *,
    writable_only: bool = True,
) -> Iterator[Tuple[NodeId, PropertyEntry, str]]:
    """``(owner, entry, text)`` for each text-valued logic property in ``scope``.

    Nothing at all for a form without logic (O(1)), or, unless ``writable_only`` is
    False, with read-only logic."""
    if doc.logic_property_count() == 0:
        return
    if writable_only and marker_read_only(doc.root.prop("cbcsLogic")):
        return
    for node in doc.iter_preorder():
        if scope is not None and node.id not in scope:
            continue
        for entry in node.properties():
            if is_user_logic_key(entry.name) and isinstance(entry.value, StringValue):
                yield node.id, entry, entry.value.text


def rewrite_ops(
    doc: UiDocument,
    scope: Optional[FrozenSet[NodeId]],
    rewrite: Callable[[str, str], Optional[str]],
) -> Tuple[Op, ...]:
    """One ``SetPropertyOp`` per property whose text ``rewrite(key, text)`` changes (None keeps it)."""
    found = []
    for owner, entry, text in logic_texts(doc, scope):
        changed = rewrite(entry.name, text)
        if changed is None or changed == text:
            continue
        value = entry.value
        assert isinstance(value, StringValue)
        replaced = StringValue(changed, value.notr, value.comment, value.extracomment, value.id)
        replacement = PropertyEntry("property", entry.name, replaced, entry.stdset, entry.extra_attrs)
        found.append(SetPropertyOp(owner, "property", entry.name, replacement, None))
    return tuple(found)


def references(
    doc: UiDocument,
    check: Callable[[str, str], bool],
) -> Tuple[Tuple[NodeId, str], ...]:
    """``(owner, property)`` for each logic text where ``check(key, text)`` is true."""
    return tuple((owner, entry.name) for owner, entry, text in logic_texts(doc, None, writable_only=False) if check(entry.name, text))
