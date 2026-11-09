"""Document invariants and fingerprints."""
from __future__ import annotations

import random

import pytest

from app.features.form_builder.engine.commands.ops import (
    InsertNodeOp,
    MoveNodeOp,
    RemoveNodeOp,
    SetFieldOp,
    SetPropertyOp,
)
from app.features.form_builder.engine.ids import DOCUMENT_ID, IdAllocator
from app.features.form_builder.engine.ui4.document import InvariantError, UiDocument
from app.features.form_builder.engine.ui4.mutate import OpError, apply
from app.features.form_builder.engine.ui4.reader import read_ui
from app.features.form_builder.engine.ui4.spec import NodeSpec, PropertyEntry
from app.features.form_builder.engine.ui4.values import StringValue
from app.features.form_builder.engine.ui4.writer import write_ui

_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form"/>
</ui>
"""
_SEED = 20261021


def _load() -> UiDocument:
    return read_ui(_FORM, allocator=IdAllocator()).document


def test_a_field_must_hold_its_declared_type() -> None:
    spec = _load().to_spec()
    fields = tuple((key, 1 if key == "version" else value) for key, value in spec.fields)
    bad = NodeSpec(
        kind=spec.kind,
        id=spec.id,
        fields=fields,
        properties=spec.properties,
        attributes=spec.attributes,
        slots=spec.slots,
        extra_attrs=spec.extra_attrs,
    )
    with pytest.raises(InvariantError):
        UiDocument.from_spec(bad)


def test_random_ops_leave_the_fingerprint_unchanged() -> None:
    print("FB_SEED %s" % _SEED)
    rng = random.Random(_SEED)
    document = _load()
    allocator = IdAllocator(start=1000)
    inserted = []
    for _step in range(40):
        kind = rng.randrange(4)
        try:
            if kind == 0:
                apply(document, SetFieldOp(DOCUMENT_ID, "author", "A%d" % rng.randrange(10)))
            elif kind == 1:
                exists = any(entry.name == "windowTitle" for entry in document.root.properties())
                apply(
                    document,
                    SetPropertyOp(
                        document.root.id,
                        "property",
                        "windowTitle",
                        PropertyEntry("property", "windowTitle", StringValue("T%d" % rng.randrange(10))),
                        None if exists else 0,
                    ),
                )
            elif kind == 2:
                node_id = allocator.alloc()
                apply(
                    document,
                    InsertNodeOp(
                        document.root.id,
                        "children",
                        0,
                        NodeSpec(
                            kind="widget",
                            id=node_id,
                            fields=(("class_name", "QPushButton"), ("object_name", "b%s" % int(node_id))),
                        ),
                    ),
                )
                inserted.append(node_id)
            elif kind == 3 and inserted:
                apply(document, MoveNodeOp(inserted[0], document.root.id, "children", 0))
            elif inserted:
                node_id = inserted.pop()
                apply(document, RemoveNodeOp(node_id))
        except OpError:
            continue
        before = document.fingerprint()
        document.validate()
        document.names()
        document.unique_name("Form")
        document.form_class_name()
        document.enum_style()
        document.connections()
        document.tabstops()
        list(document.iter_preorder())
        list(document.iter_widgets())
        document.structure_fingerprint()
        assert document.fingerprint() == before


def test_fingerprint_works_at_max_depth() -> None:
    depth = 254
    text = "<ui version=\"4.0\">" + "<widget class=\"QWidget\" name=\"w\">" * depth + "</widget>" * depth + "</ui>"
    document = read_ui(text, allocator=IdAllocator()).document
    saved = write_ui(document).text
    assert read_ui(saved, allocator=IdAllocator()).document.structure_fingerprint() == document.structure_fingerprint()
    document.fingerprint()
