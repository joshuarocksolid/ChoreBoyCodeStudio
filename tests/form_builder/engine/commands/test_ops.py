"""Primitive op inverses and failed preconditions (CONTRACTS.md section 3.3)."""

from __future__ import annotations

from typing import Optional, cast

import pytest

from app.features.form_builder.engine.commands.catalog import SetProperty
from app.features.form_builder.engine.commands.ops import (
    InsertNodeOp,
    MoveNodeOp,
    Op,
    RemoveNodeOp,
    ReplaceRootOp,
    SetFieldOp,
    SetPropertyOp,
)
from app.features.form_builder.engine.ids import DOCUMENT_ID, IdAllocator, NodeId
from app.features.form_builder.engine.ui4 import mutate
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.mutate import OpError
from app.features.form_builder.engine.ui4.reader import read_ui
from app.features.form_builder.engine.ui4.spec import NodeSpec, PropertyEntry
from app.features.form_builder.engine.ui4.values import StringValue
from tests.form_builder.engine.commands._support import BOX, nid, open_log, saved


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


def test_all_six_ops_round_trip() -> None:
    log = open_log(BOX)
    doc = log.document
    button = nid(doc, "okButton")
    assert doc.node(button).parent_id is not None
    replacement = read_ui(BOX, allocator=IdAllocator(10000)).document.to_spec()
    ops = (
        InsertNodeOp(doc.root.id, "children", 0, _widget(NodeId(9000))),
        RemoveNodeOp(button),
        MoveNodeOp(button, doc.root.id, "children", 0),
        SetPropertyOp(
            button,
            "property",
            "toolTip",
            PropertyEntry("property", "toolTip", StringValue("hint")),
            len(doc.node(button).properties()),
        ),
        SetFieldOp(button, "object_name", "submit"),
        ReplaceRootOp(replacement),
    )
    for op in ops:
        fingerprint = doc.fingerprint()
        inverse = mutate.apply(doc, op)
        mutate.apply(doc, inverse)
        assert doc.fingerprint() == fingerprint


def test_property_removal_puts_the_entry_back_where_it_was() -> None:
    text = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0"><widget class="QWidget" name="Form">
 <widget class="QPushButton" name="okButton">
  <property name="text"><string>OK</string></property>
  <property name="geometry"><rect><x>0</x><y>0</y><width>10</width><height>10</height></rect></property>
 </widget>
</widget></ui>
"""
    log = open_log(text)
    doc = log.document
    button = nid(doc, "okButton")
    before = tuple(entry.name for entry in doc.node(button).properties())
    assert before.index("geometry") != 0
    original = saved(doc)
    log.execute(SetProperty(button, "geometry", None))
    inverse = log.entries()[-1].inverse_ops[0]
    assert isinstance(inverse, SetPropertyOp)
    assert inverse.index == before.index("geometry")
    assert log.undo()
    assert tuple(entry.name for entry in doc.node(button).properties()) == before
    assert saved(doc) == original


@pytest.mark.parametrize(
    "build",
    [
        "remove-root",
        "remove-ui",
        "insert-duplicate",
        "insert-index",
        "insert-bad-slot",
        "insert-bad-kind",
        "insert-unset-id",
        "insert-occupied-slot",
        "move-into-self",
        "move-index",
        "move-root",
        "remove-unknown",
        "set-bad-kind",
        "set-no-properties",
        "set-no-attributes",
        "remove-missing",
        "replace-with-index",
        "set-unknown-field",
        "clear-required",
        "invalid-field",
        "replace-not-ui",
        "replace-id-in-use",
        "unknown-op",
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
        elif build == "insert-index":
            mutate.apply(doc, InsertNodeOp(doc.root.id, "children", 99, _widget(NodeId(9001))))
        elif build == "insert-bad-slot":
            mutate.apply(doc, InsertNodeOp(doc.root.id, "nope", 0, _widget(NodeId(9002))))
        elif build == "insert-bad-kind":
            mutate.apply(doc, InsertNodeOp(doc.root.id, "children", 0, _layout(NodeId(9003))))
        elif build == "insert-unset-id":
            mutate.apply(doc, InsertNodeOp(doc.root.id, "children", 0, _widget(None)))
        elif build == "insert-occupied-slot":
            mutate.apply(doc, InsertNodeOp(doc.root.id, "layout", 0, _layout(NodeId(9004))))
        elif build == "move-into-self":
            mutate.apply(doc, MoveNodeOp(button, button, "children", 0))
        elif build == "move-index":
            node = doc.node(button)
            assert node.parent_id is not None and node.parent_slot is not None
            mutate.apply(doc, MoveNodeOp(button, node.parent_id, node.parent_slot, 99))
        elif build == "move-root":
            mutate.apply(doc, MoveNodeOp(doc.root.id, DOCUMENT_ID, "root", 0))
        elif build == "remove-unknown":
            mutate.apply(doc, RemoveNodeOp(NodeId(10**9)))
        elif build == "set-bad-kind":
            mutate.apply(doc, SetPropertyOp(button, "nope", "text", _tip(), 0))
        elif build == "set-no-properties":
            mutate.apply(doc, SetPropertyOp(DOCUMENT_ID, "property", "text", _tip(), 0))
        elif build == "set-no-attributes":
            mutate.apply(doc, SetPropertyOp(DOCUMENT_ID, "attribute", "title", _tip("attribute"), 0))
        elif build == "remove-missing":
            mutate.apply(doc, SetPropertyOp(button, "property", "noSuch", None))
        elif build == "replace-with-index":
            current = doc.node(button).prop("text")
            assert current is not None
            mutate.apply(doc, SetPropertyOp(button, "property", "text", current, 0))
        elif build == "set-unknown-field":
            mutate.apply(doc, SetFieldOp(button, "nope", "x"))
        elif build == "clear-required":
            mutate.apply(doc, SetFieldOp(button, "object_name", None))
        elif build == "invalid-field":
            mutate.apply(doc, SetFieldOp(button, "object_name", {"bad": 1}))
        elif build == "replace-not-ui":
            mutate.apply(doc, ReplaceRootOp(_widget(NodeId(9005))))
        elif build == "replace-id-in-use":
            mutate.apply(doc, ReplaceRootOp(doc.to_spec()))
        else:
            mutate.apply(doc, cast(Op, _NotAnOp()))
    assert doc.fingerprint() == fingerprint
    assert doc.revision == revision


class _NotAnOp:
    pass


def _widget(node_id: Optional[NodeId]) -> NodeSpec:
    return NodeSpec(
        "widget",
        node_id,
        (("class_name", "QPushButton"), ("object_name", "extra")),
    )


def _layout(node_id: NodeId) -> NodeSpec:
    return NodeSpec(
        "layout",
        node_id,
        (("class_name", "QVBoxLayout"), ("object_name", "extraLayout")),
    )


def _tip(kind: str = "property") -> PropertyEntry:
    return PropertyEntry(kind, "toolTip", StringValue("hint"))


def test_moving_a_container_reseats_several_shared_names_under_it() -> None:
    """Two shared-name ids under one moved node must keep document order.

    Regression for the O-logic gate's M1.2 rescue finding: re-seating one id at
    a time compared each insert against siblings still at stale positions.
    """
    from app.features.form_builder.engine.commands.catalog import MoveNodes
    from app.features.form_builder.engine.commands.placement import InBoxLayout

    def label(name: str) -> str:
        return '<item><widget class="QLabel" name="%s"/></item>' % name

    text = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<ui version="4.0"><class>Form</class><widget class="QWidget" name="Form">'
        '<layout class="QVBoxLayout" name="v">%s'
        '<item><widget class="QWidget" name="box"><layout class="QVBoxLayout" name="v2">%s%s</layout></widget></item>'
        "%s</layout></widget><resources/><connections/></ui>"
    ) % (label("dup"), label("dup"), label("dup"), label("dup"))
    log = open_log(text)
    doc = log.document
    box = nid(doc, "box")
    root_layout = doc.root.layout
    assert root_layout is not None
    log.execute(MoveNodes((box,), InBoxLayout(root_layout.id, 3)))
    doc.validate()
    log.undo()
    doc.validate()
