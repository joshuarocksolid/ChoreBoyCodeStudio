"""Primitive op inverses and failed preconditions (CONTRACTS.md section 3.3)."""

from __future__ import annotations

import pytest

from app.features.form_builder.engine.commands.catalog import SetProperty
from app.features.form_builder.engine.commands.ops import (
    InsertNodeOp,
    MoveNodeOp,
    RemoveNodeOp,
    SetPropertyOp,
)
from app.features.form_builder.engine.ids import DOCUMENT_ID
from app.features.form_builder.engine.ui4 import mutate
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.mutate import OpError
from app.features.form_builder.engine.ui4.values import StringValue
from tests.form_builder.engine.commands._support import BOX, nid, open_log


def test_each_op_then_its_inverse_restores_the_fingerprint() -> None:
    log = open_log(BOX)
    doc = log.document
    before = doc.to_spec()
    log.execute(SetProperty(nid(doc, "okButton"), "text", StringValue("Go")))
    clone = UiDocument.from_spec(before)
    entry = log.entries()[-1]
    assert entry.ops
    for op, recorded in zip(entry.ops, entry.inverse_ops):
        fingerprint = clone.fingerprint()
        inverse = mutate.apply(clone, op)
        assert inverse == recorded
        mutate.apply(clone, inverse)
        assert clone.fingerprint() == fingerprint
        mutate.apply(clone, op)
    assert clone.fingerprint() == doc.fingerprint()


@pytest.mark.parametrize(
    "build",
    [
        "remove-root",
        "remove-ui",
        "insert-duplicate",
        "move-into-self",
        "replace-with-index",
    ],
)
def test_failed_precondition_leaves_the_document(build: str) -> None:
    log = open_log(BOX)
    doc = log.document
    fingerprint = doc.fingerprint()
    revision = doc.revision
    button = nid(doc, "okButton")
    with pytest.raises(OpError):
        if build == "remove-root":
            mutate.apply(doc, RemoveNodeOp(doc.root.id))
        elif build == "remove-ui":
            mutate.apply(doc, RemoveNodeOp(DOCUMENT_ID))
        elif build == "insert-duplicate":
            mutate.apply(doc, InsertNodeOp(doc.root.id, "children", 0, doc.node(button).to_spec()))
        elif build == "move-into-self":
            mutate.apply(doc, MoveNodeOp(button, button, "children", 0))
        else:
            current = doc.node(button).prop("text")
            assert current is not None
            mutate.apply(doc, SetPropertyOp(button, "property", "text", current, 0))
    assert doc.fingerprint() == fingerprint
    assert doc.revision == revision
