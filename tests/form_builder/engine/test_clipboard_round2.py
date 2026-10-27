"""Round-2 clipboard rules. Each test fails on the M3.4 round-1 tree."""

from __future__ import annotations

import random
from typing import List, Sequence, Tuple

from app.features.form_builder.engine.clipboard import (
    paste_auto_layout,
    paste_placement,
    paste_sentence,
    plan_paste,
    selection_fragment,
    sibling_ids,
)
from app.features.form_builder.engine.commands.catalog import (
    InsertFragment,
    InsertResult,
    Rename,
    SetProperty,
)
from app.features.form_builder.engine.commands.placement import InContainer, InFormRow
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.query.connections import missing_connection_diagnostics
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.nodes import LayoutNode, SpacerNode, WidgetNode
from app.features.form_builder.engine.ui4.reader import read_fragment
from app.features.form_builder.engine.ui4.spec import Fragment, NodeSpec
from app.features.form_builder.engine.ui4.values import RectValue, StringValue
from app.features.form_builder.engine.ui4.writer import write_fragment
from tests.form_builder.engine.commands._support import BOX, button_spec, cell_of, nid, open_log

_UI = '<?xml version="1.0" encoding="UTF-8"?>\n<ui version="4.0">\n <class>Form</class>\n%s\n <resources/>\n <connections/>\n</ui>\n'

_BARE = _UI % """
 <widget class="QDialog" name="Dialog">
  <widget class="QLineEdit" name="nameEdit">
   <property name="geometry"><rect><x>20</x><y>30</y><width>100</width><height>24</height></rect></property>
  </widget>
  <widget class="QPushButton" name="okButton">
   <property name="geometry"><rect><x>290</x><y>250</y><width>80</width><height>24</height></rect></property>
   <property name="text"><string>OK</string></property>
  </widget>
 </widget>
"""

_FORM = _UI % """
 <widget class="QWidget" name="Form">
  <layout class="QFormLayout" name="formLayout">
   <item row="0" column="0">
    <widget class="QLabel" name="phoneLabel"><property name="text"><string>Phone</string></property></widget>
   </item>
   <item row="0" column="1"><widget class="QLineEdit" name="phone"/></item>
   <item row="1" column="0">
    <widget class="QLabel" name="emailLabel"><property name="text"><string>Email</string></property></widget>
   </item>
   <item row="1" column="1"><widget class="QLineEdit" name="email"/></item>
  </layout>
 </widget>
"""

_WIRED = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <layout class="QVBoxLayout" name="verticalLayout">
   <item><widget class="QPushButton" name="save"><property name="text"><string>Save</string></property></widget></item>
   <item><widget class="QLineEdit" name="email"/></item>
   <item><widget class="QPushButton" name="clear"><property name="text"><string>Clear</string></property></widget></item>
  </layout>
 </widget>
 <resources/>
 <connections>
  <connection>
   <sender>save</sender><signal>clicked()</signal><receiver>email</receiver><slot>clear()</slot>
  </connection>
  <connection>
   <sender>clear</sender><signal>clicked()</signal><receiver>email</receiver><slot>clear()</slot>
  </connection>
 </connections>
</ui>
"""

_MIXED = _UI % """
 <widget class="QWidget" name="Form">
  <layout class="QVBoxLayout" name="verticalLayout">
   <item><widget class="QPushButton" name="alpha"><property name="text"><string>A</string></property></widget></item>
   <item><layout class="QHBoxLayout" name="row"/></item>
   <item><spacer name="gap"><property name="sizeHint"><size><width>8</width><height>12</height></size></property></spacer></item>
   <item><widget class="QLineEdit" name="beta"/></item>
   <item><layout class="QGridLayout" name="grid"/></item>
  </layout>
 </widget>
"""

_EMPTY = _UI % """
 <widget class="QWidget" name="Form"/>
"""

_FREE = _UI % """
 <widget class="QWidget" name="Form">
  <widget class="QPushButton" name="okButton">
   <property name="geometry"><rect><x>10</x><y>12</y><width>40</width><height>20</height></rect></property>
  </widget>
 </widget>
"""


def _rect(doc, name: str) -> Tuple[int, int, int, int]:
    value = doc.node(nid(doc, name)).prop("geometry")
    assert value is not None and isinstance(value.value, RectValue)
    rect = value.value
    return rect.x, rect.y, rect.width, rect.height


def _connect(sender: str, receiver: str) -> NodeSpec:
    return NodeSpec(
        "connection",
        None,
        (
            ("sender", sender),
            ("signal", "clicked()"),
            ("receiver", receiver),
            ("slot", "clear()"),
        ),
    )


def _ends(doc) -> List[Tuple[object, object]]:
    return [(node.field("sender"), node.field("receiver")) for node in doc.ui.children("connections")]


def _identity(kind: str, class_name: object, name: object) -> Tuple[str, str]:
    label = class_name if isinstance(class_name, str) and class_name else kind
    title = name if isinstance(name, str) else ""
    return label, title


def _spec_identity(spec: NodeSpec) -> Tuple[str, str]:
    return _identity(spec.kind, spec.field("class_name"), spec.field("object_name") or spec.field("name"))


def _node_identity(node: object) -> Tuple[str, str]:
    if isinstance(node, SpacerNode):
        return _identity(node.kind, "", node.name)
    class_name = getattr(node, "class_name", "")
    object_name = getattr(node, "object_name", "")
    return _identity(getattr(node, "kind", ""), class_name, object_name)


def _pasted_top(doc) -> List[Tuple[str, str]]:
    layout = doc.root.layout
    assert isinstance(layout, LayoutNode)
    found = []
    for item in layout.items:
        assert item.content is not None
        found.append(_node_identity(item.content))
    return found


def _paste(log, fragment: Fragment, anchor: Sequence[NodeId]) -> None:
    doc = log.document
    place, fragment, auto_layout = plan_paste(doc, anchor, fragment)
    outcome = log.execute(InsertFragment(place, fragment, auto_layout=auto_layout, undo_label="Paste"))
    assert isinstance(outcome.result, InsertResult)


def test_paste_onto_a_bare_dialog_keeps_free_children() -> None:
    log = open_log(_BARE)
    doc = log.document
    before = {name: _rect(doc, name) for name in ("nameEdit", "okButton")}
    _paste(log, Fragment(nodes=(button_spec("extra", "Extra"),)), (doc.root.id,))
    assert doc.root.layout is None
    assert _rect(doc, "nameEdit") == before["nameEdit"]
    assert _rect(doc, "okButton") == before["okButton"]
    # 16, 16 px past okButton would cover it, so the paste drops just below.
    assert _rect(doc, "extra") == (306, 282, 80, 24)
    assert log.undo_label() == "Paste"


def test_a_label_and_field_paste_as_one_row_after_either_anchor() -> None:
    for anchor_name in ("email", "emailLabel"):
        log = open_log(_FORM)
        doc = log.document
        pair = selection_fragment(doc, (nid(doc, "phoneLabel"), nid(doc, "phone")))
        _paste(log, pair, (nid(doc, anchor_name),))
        assert cell_of(doc, "phoneLabel_2") == (2, 0)
        assert cell_of(doc, "phone_2") == (2, 1)
        assert cell_of(doc, "email") == (1, 1)
        assert cell_of(doc, "emailLabel") == (1, 0)


def test_a_lone_form_widget_takes_its_own_column() -> None:
    log = open_log(_FORM)
    doc = log.document
    label = selection_fragment(doc, (nid(doc, "phoneLabel"),))
    _paste(log, label, (nid(doc, "email"),))
    assert cell_of(doc, "phoneLabel_2") == (2, 0)
    field = selection_fragment(doc, (nid(doc, "phone"),))
    _paste(log, field, (nid(doc, "emailLabel"),))
    assert cell_of(doc, "phone_2") == (2, 1)
    assert cell_of(doc, "phoneLabel_2") == (3, 0)


def test_an_outside_connection_is_dropped_when_that_widget_exists() -> None:
    log = open_log(_WIRED)
    doc = log.document
    fragment = selection_fragment(doc, (nid(doc, "save"),))
    _paste(log, fragment, (nid(doc, "clear"),))
    assert ("save_2", "email") not in _ends(doc)
    assert missing_connection_diagnostics(doc) == ()


def test_a_copied_pair_does_not_rewire_a_widget_left_behind() -> None:
    log = open_log(_WIRED)
    doc = log.document
    fragment = selection_fragment(doc, (nid(doc, "save"), nid(doc, "email")))
    _paste(log, fragment, (nid(doc, "clear"),))
    assert ("clear", "email_2") not in _ends(doc)
    assert ("save_2", "email_2") in _ends(doc)


def test_a_missing_outside_end_is_kept_and_named() -> None:
    log = open_log(_EMPTY)
    source = open_log(_WIRED).document
    fragment = selection_fragment(source, (nid(source, "save"),))
    _paste(log, fragment, ())
    assert ("save", "email") in _ends(log.document)
    rows = missing_connection_diagnostics(log.document)
    assert len(rows) == 1
    assert rows[0].message == (
        "The connection save.clicked → email.clear points at email, which isn't in this form. "
        "Add a widget named email or delete the connection."
    )


def test_copying_the_form_copies_its_contents() -> None:
    log = open_log(BOX)
    doc = log.document
    fragment = selection_fragment(doc, (doc.root.id,))
    assert [_spec_identity(spec) for spec in fragment.nodes] == [
        ("QPushButton", "okButton"),
        ("QLabel", "label"),
    ]
    everyone = selection_fragment(doc, tuple(node.id for node in doc.iter_preorder()))
    assert [_spec_identity(spec) for spec in everyone.nodes] == [
        ("QPushButton", "okButton"),
        ("QLabel", "label"),
    ]


def test_sibling_subsets_paste_in_document_order() -> None:
    rng = random.Random(4)
    source = open_log(_MIXED).document
    layout = source.root.layout
    assert isinstance(layout, LayoutNode)
    contents = [item.content for item in layout.items]
    assert all(node is not None for node in contents)
    ids = [node.id for node in contents if node is not None]
    expected = [_node_identity(node) for node in contents if node is not None]
    for _trial in range(8):
        count = rng.randint(1, len(ids))
        picked = tuple(sorted(rng.sample(range(len(ids)), count)))
        chosen = tuple(ids[index] for index in picked)
        fragment = selection_fragment(source, chosen)
        again = read_fragment(write_fragment(fragment))
        want = [expected[index] for index in picked]
        assert [_spec_identity(spec) for spec in again.nodes] == want
        dest = open_log(_EMPTY)
        _paste(dest, again, ())
        assert _pasted_top(dest.document) == want


def test_a_layout_pasted_beside_a_free_widget_keeps_the_widget() -> None:
    source = open_log(_MIXED).document
    fragment = selection_fragment(source, (nid(source, "row"),))
    log = open_log(_FREE)
    doc = log.document
    before = _rect(doc, "okButton")
    _paste(log, fragment, (nid(doc, "okButton"),))
    assert doc.root.layout is None
    assert _rect(doc, "okButton") == before
    holders = [
        node
        for node in doc.iter_preorder()
        if isinstance(node, WidgetNode) and node.object_name.startswith("widget")
    ]
    assert len(holders) == 1
    assert holders[0].layout is not None
    assert holders[0].layout.class_name == "QHBoxLayout"


def test_paste_into_a_container_uses_its_visible_text() -> None:
    log = open_log(_BARE)
    doc = log.document
    doc.root  # the dialog has no text, so the sentence uses the object name
    sentence = paste_sentence(doc, (doc.root.id,), 1)
    assert sentence == "Pasted 1 widget into Dialog"
    titled = open_log(BOX)
    titled.document.root
    outcome = titled.execute(
        SetProperty(titled.document.root.id, "windowTitle", StringValue("Contact details"))
    )
    assert outcome.noop is False
    assert paste_sentence(titled.document, (titled.document.root.id,), 1) == (
        "Pasted 1 widget into Contact details"
    )


def test_ctrl_a_selects_the_siblings_of_the_anchor() -> None:
    log = open_log(BOX)
    doc = log.document
    button = nid(doc, "okButton")
    label = nid(doc, "label")
    assert sibling_ids(doc, button, (button,)) == (button, label)
    assert sibling_ids(doc, doc.root.id, (doc.root.id,)) == (button, label)


def test_a_property_edit_does_not_rescan_missing_connections(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    calls: List[int] = []
    real = missing_connection_diagnostics

    def wrapped(document):  # type: ignore[no-untyped-def]
        calls.append(1)
        return real(document)

    monkeypatch.setattr(
        "app.features.form_builder.engine.session.missing_connection_diagnostics",
        wrapped,
    )
    session = FormSession.open(
        BOX,
        path="/tmp/cbcs-scan.ui",
        scope=FormScope(kind="external", ui_path="/tmp/cbcs-scan.ui"),
    )
    try:
        before = len(calls)
        button = nid(session.document, "okButton")
        session.log.execute(SetProperty(button, "text", StringValue("Save")))
        assert len(calls) == before
        session.log.execute(Rename(button, "save"))
        assert len(calls) == before + 1
    finally:
        session.dispose()


def test_two_empty_containers_still_grow_a_vertical_layout() -> None:
    log = open_log(_EMPTY)
    place = paste_placement(log.document, ())
    assert isinstance(place, InContainer)
    assert place.geometry is None
    assert paste_auto_layout(place) is True
    log.execute(InsertFragment(place, Fragment(nodes=(button_spec("extra"),))))
    assert log.document.root.layout is not None
    assert log.document.root.layout.class_name == "QVBoxLayout"
