# pyright: reportAttributeAccessIssue=false
"""Reader and writer behavior for the ui4 core."""
from __future__ import annotations

import random
import sys
import threading
from pathlib import Path
from typing import List

import pytest

from app.features.form_builder.engine.commands.ops import InsertNodeOp, SetPropertyOp
from app.features.form_builder.engine.ids import IdAllocator, NodeId
from app.features.form_builder.engine.ui4.mutate import OpError, apply
from app.features.form_builder.engine.ui4.reader import UiReadError, read_ui
from app.features.form_builder.engine.ui4.spec import NodeSpec, PropertyEntry
from app.features.form_builder.engine.ui4.values import BoolValue, OpaqueValue, StringValue
from app.features.form_builder.engine.ui4.writer import write_ui

CANONICAL = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <property name="windowTitle">
   <string notr="true">Hello &amp; bye</string>
  </property>
  <property name="enabled">
   <bool>true</bool>
  </property>
  <property name="geometry">
   <rect>
    <x>0</x>
    <y>0</y>
    <width>400</width>
    <height>300</height>
   </rect>
  </property>
  <property name="buddy">
   <cstring>nameEdit</cstring>
  </property>
  <property name="orientation">
   <enum>Qt::Horizontal</enum>
  </property>
  <property name="standardButtons">
   <set>QDialogButtonBox::Cancel|QDialogButtonBox::Ok</set>
  </property>
  <property name="minimumSize">
   <size>
    <width>10</width>
    <height>20</height>
   </size>
  </property>
  <property name="sizePolicy">
   <sizepolicy hsizetype="Preferred" vsizetype="Fixed">
    <horstretch>0</horstretch>
    <verstretch>0</verstretch>
   </sizepolicy>
  </property>
  <property name="font">
   <font>
    <family>Sans</family>
    <pointsize>12</pointsize>
    <bold>true</bold>
   </font>
  </property>
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QPushButton" name="okButton">
     <property name="text">
      <string>OK</string>
     </property>
    </widget>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


def _load(text: str):
    return read_ui(text, allocator=IdAllocator())


def _saved(text: str) -> str:
    return write_ui(_load(text).document).text


@pytest.mark.parity("R3-223")
@pytest.mark.parity("R3-227")
@pytest.mark.parity("R3-228")
@pytest.mark.parity("R3-236")
@pytest.mark.parity("R3-237")
@pytest.mark.parity("R3-258")
@pytest.mark.parity("R3-265")
@pytest.mark.parity("R3-266")
@pytest.mark.parity("R3-271")
@pytest.mark.parity("R3-272")
@pytest.mark.parity("R3-274")
@pytest.mark.parity("R3-283")
@pytest.mark.parity("R3-285")
@pytest.mark.parity("R3-288")
@pytest.mark.parity("R3-289")
@pytest.mark.parity("R3-294")
@pytest.mark.parity("R3-295")
@pytest.mark.parity("R3-297")
@pytest.mark.parity("R3-298")
@pytest.mark.parity("R3-299")
def test_canonical_form_is_byte_stable() -> None:
    first = _saved(CANONICAL)
    assert first == CANONICAL
    assert _saved(first) == first


def test_second_save_matches_first_when_numbers_normalize() -> None:
    text = CANONICAL.replace("<double>1.5</double>", "<double>1.5</double>")
    source = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <widget class="QWidget" name="Form">
  <property name="value">
   <double>1.5</double>
  </property>
 </widget>
</ui>
"""
    first = _saved(source)
    assert "<double>1.500000000000000</double>" in first
    assert write_ui(_load(first).document).text == first


def test_ids_follow_schema_preorder_and_stay_stable() -> None:
    first = _load(CANONICAL)
    second = _load(CANONICAL)
    assert first.document.structure_fingerprint() == second.document.structure_fingerprint()
    assert [node.id for node in first.document.iter_preorder()] == [
        node.id for node in second.document.iter_preorder()
    ]
    root = first.document.root
    assert root.object_name == "Form"
    parent = first.document.parent(root.id)
    assert parent is not None
    assert parent.id == first.document.ui.id
    button_ids = first.document.by_name("okButton")
    assert button_ids
    assert first.document.node(button_ids[0]).field("object_name") == "okButton"
    layout_id = first.document.by_name("verticalLayout")[0]
    layout_parent = first.document.parent(layout_id)
    assert layout_parent is not None
    assert layout_parent.id == root.id


def test_spaced_bool_stays_opaque_and_matches_qt(qapp: object) -> None:
    del qapp
    text = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <widget class="QWidget" name="Form">
  <property name="enabled">
   <bool> true</bool>
  </property>
  <property name="font">
   <font>
    <bold> true</bold>
   </font>
  </property>
 </widget>
</ui>
"""
    from app.qt.QtCore import QBuffer, QIODevice
    from app.qt.QtUiTools import QUiLoader

    def load(xml: str) -> object:
        buffer = QBuffer()
        buffer.setData(xml.encode("utf-8"))
        buffer.open(QIODevice.ReadOnly)
        widget = QUiLoader().load(buffer)
        assert widget is not None
        return widget

    original = load(text)
    saved = write_ui(_load(text).document).text
    assert "<bool> true</bool>" in saved
    assert "<bold> true</bold>" in saved
    rewritten = load(saved)
    assert original.isEnabled() == rewritten.isEnabled()
    assert original.font().bold() == rewritten.font().bold()


def test_unknown_sibling_after_a_wrapper_stays_outside() -> None:
    text = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <widget class="QWidget" name="Form"/>
 <resources>
  <include location="other.qrc"/>
  <zzin/>
 </resources>
 <zzout/>
 <connections/>
</ui>
"""
    loaded = _load(text)
    saved = write_ui(loaded.document).text
    compact = "".join(line.strip() for line in saved.splitlines())
    assert "<resources><include" in compact
    assert "<zzin/></resources><zzout/><connections" in compact
    again = _load(saved)
    assert again.document.structure_fingerprint() == loaded.document.structure_fingerprint()
    empty = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <widget class="QWidget" name="Form"/>
 <resources/>
 <zz/>
 <connections/>
</ui>
"""
    loaded = _load(empty)
    saved = write_ui(loaded.document).text
    compact = "".join(line.strip() for line in saved.splitlines())
    assert "<resources/><zz/><connections" in compact
    assert _load(saved).document.structure_fingerprint() == loaded.document.structure_fingerprint()


def test_odd_property_content_rereads_with_the_same_fingerprint() -> None:
    text = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <widget class="QWidget" name="Form">
  <property name="empty"/>
  <property name="text"/>
  <property name="noted"><!--c--><string>A</string></property>
  <property name="two"><string>A</string><string>B</string></property>
 </widget>
</ui>
"""
    loaded = _load(text)
    saved = write_ui(loaded.document).text
    assert "#value" not in saved
    assert '<property name="empty"/>' in saved
    assert '<property name="text"/>' in saved
    again = _load(saved)
    assert again.document.structure_fingerprint() == loaded.document.structure_fingerprint()
    assert write_ui(again.document).text == saved


def test_duplicate_property_keeps_the_last_value() -> None:
    text = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <widget class="QWidget" name="Form">
  <property name="windowTitle">
   <string>First</string>
  </property>
  <property name="windowTitle">
   <string>Last</string>
  </property>
 </widget>
</ui>
"""
    result = _load(text)
    entry = result.document.root.prop("windowTitle")
    assert entry is not None
    assert isinstance(entry.value, StringValue)
    assert entry.value.text == "Last"
    assert any(item.code == "FB007" for item in result.diagnostics)
    saved = write_ui(result.document).text
    assert saved.index("First") < saved.index("Last")
    assert write_ui(_load(saved).document).text == saved


def test_earlier_duplicate_stays_at_its_position() -> None:
    # A1, B, A2 -> write A1, B, A2. B, A1, A2 -> write B, A1, A2.
    first = _saved(
        """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <widget class="QWidget" name="Form">
  <property name="windowTitle"><string>A1</string></property>
  <property name="toolTip"><string>B</string></property>
  <property name="windowTitle"><string>A2</string></property>
 </widget>
</ui>
"""
    )
    assert first.index(">A1<") < first.index(">B<") < first.index(">A2<")
    second = _saved(
        """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <widget class="QWidget" name="Form">
  <property name="toolTip"><string>B</string></property>
  <property name="windowTitle"><string>A1</string></property>
  <property name="windowTitle"><string>A2</string></property>
 </widget>
</ui>
"""
    )
    assert second.index(">B<") < second.index(">A1<") < second.index(">A2<")
    between = _saved(
        """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <widget class="QWidget" name="Form">
  <property name="windowTitle"><string>A1</string></property>
  <extra/>
  <property name="windowTitle"><string>A2</string></property>
 </widget>
</ui>
"""
    )
    assert between.index(">A1<") < between.index("<extra") < between.index(">A2<")


def test_empty_pair_is_one_line_and_the_table_is_the_flip_point() -> None:
    from app.features.form_builder.engine.ui4 import writer as writer_module

    text = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <widget class="QWidget" name="Form">
  <property name="value"><number></number></property>
 </widget>
</ui>
"""
    saved = _saved(text)
    assert "<number></number>" in saved
    original = writer_module.EMPTY_ELEMENT_FORM["number"]
    writer_module.EMPTY_ELEMENT_FORM["number"] = "self"
    try:
        flipped = _saved(text)
    finally:
        writer_module.EMPTY_ELEMENT_FORM["number"] = original
    assert "<number/>" in flipped
    assert flipped != saved


def test_empty_string_matches_designer_self_close() -> None:
    saved = _saved(
        """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <widget class="QWidget" name="Form">
  <property name="windowTitle"><string></string></property>
  <property name="toolTip"><string notr="true"></string></property>
 </widget>
</ui>
"""
    )
    assert "<string/>" in saved
    assert '<string notr="true"/>' in saved
    assert "<string></string>" not in saved


def test_text_escapes_quote_and_cr_and_keeps_utf8() -> None:
    saved = _saved(
        """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <widget class="QWidget" name="Form">
  <property name="windowTitle"><string comment="a&#9;b&#10;c&#13;d">say &#13; "hi" café</string></property>
 </widget>
</ui>
"""
    )
    assert "say &#13; &quot;hi&quot; café" in saved
    assert "comment=\"a&#9;b&#10;c&#13;d\"" in saved
    assert "&#233;" not in saved
    assert write_ui(_load(saved).document).text == saved


@pytest.mark.parity("R3-302")
@pytest.mark.parity("R3-303")
def test_float_uses_eight_decimals_and_double_uses_fifteen() -> None:
    saved = _saved(
        """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <widget class="QWidget" name="Form">
  <property name="a"><float>1.5</float></property>
  <property name="b"><double>1.5</double></property>
 </widget>
</ui>
"""
    )
    assert "<float>1.50000000</float>" in saved
    assert "<double>1.500000000000000</double>" in saved


def test_insert_rejects_an_illegal_xml_char() -> None:
    document = _load(
        """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0"><widget class="QWidget" name="Form"/></ui>
"""
    ).document
    spec = NodeSpec(
        kind="widget",
        id=NodeId(50),
        fields=(("class_name", "QPushButton"), ("object_name", "a\x00b")),
    )
    with pytest.raises(OpError):
        apply(document, InsertNodeOp(document.root.id, "children", 0, spec))


def test_illegal_xml_char_is_rejected() -> None:
    document = _load(
        """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0"><widget class="QWidget" name="Form"/></ui>
"""
    ).document
    with pytest.raises(OpError):
        apply(
            document,
            SetPropertyOp(
                owner=document.root.id,
                kind="property",
                name="windowTitle",
                entry=PropertyEntry("property", "windowTitle", StringValue("a\x00b")),
                index=0,
            ),
        )


def test_unknown_value_and_element_are_kept() -> None:
    text = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <widget class="QWidget" name="Form">
  <property name="windowIcon">
   <sparkle>1</sparkle>
  </property>
  <designerdata/>
 </widget>
</ui>
"""
    result = _load(text)
    icon = result.document.root.prop("windowIcon")
    assert icon is not None
    assert isinstance(icon.value, OpaqueValue)
    assert icon.value.element.tag == "sparkle"
    assert any(item.code == "FB005" for item in result.diagnostics)
    assert any(item.code == "FB006" for item in result.diagnostics)
    saved = write_ui(result.document).text
    assert "<sparkle>1</sparkle>" in saved
    assert write_ui(_load(saved).document).text == saved


def test_lossy_bool_and_underflow_stay_verbatim() -> None:
    text = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <widget class="QWidget" name="Form">
  <property name="enabled">
   <bool>1</bool>
  </property>
  <property name="tiny">
   <double>1e-400</double>
  </property>
 </widget>
</ui>
"""
    result = _load(text)
    enabled = result.document.root.prop("enabled")
    tiny = result.document.root.prop("tiny")
    assert enabled is not None and tiny is not None
    assert isinstance(enabled.value, OpaqueValue)
    assert isinstance(tiny.value, OpaqueValue)
    saved = write_ui(result.document).text
    assert "<bool>1</bool>" in saved
    assert "<double>1e-400</double>" in saved
    assert write_ui(_load(saved).document).text == saved


def test_crlf_and_bom_are_accepted() -> None:
    body = "<ui version=\"4.0\"><widget class=\"QWidget\" name=\"Form\"/></ui>"
    result = _load("\ufeff" + body.replace(">", ">\r\n"))
    assert result.document.root.object_name == "Form"


def test_malformed_xml_reports_a_column() -> None:
    with pytest.raises(UiReadError) as caught:
        _load("<ui")
    assert caught.value.code == "FB001"
    assert caught.value.column >= 1


def test_doctype_is_refused() -> None:
    with pytest.raises(UiReadError) as caught:
        _load("<!DOCTYPE ui>\n<ui version=\"4.0\"><widget class=\"QWidget\" name=\"Form\"/></ui>")
    assert caught.value.code == "FB004"


def test_missing_root_widget_is_refused() -> None:
    with pytest.raises(UiReadError) as caught:
        _load("<ui version=\"4.0\"></ui>")
    assert caught.value.code == "FB002"


def test_newer_version_warns_and_still_loads() -> None:
    result = _load("<ui version=\"5.0\"><widget class=\"QWidget\" name=\"Form\"/></ui>")
    assert result.document.root.class_name == "QWidget"
    assert any(item.code == "FB003" for item in result.diagnostics)


def test_set_property_inverse_restores_the_fingerprint() -> None:
    document = _load(CANONICAL).document
    before = document.fingerprint()
    inverse = apply(
        document,
        SetPropertyOp(
            owner=document.root.id,
            kind="property",
            name="enabled",
            entry=PropertyEntry("property", "enabled", BoolValue(False)),
            index=None,
        ),
    )
    enabled = document.root.prop("enabled")
    assert enabled is not None
    assert enabled.value == BoolValue(False)
    apply(document, inverse)
    assert document.fingerprint() == before


def test_seeded_random_documents_round_trip() -> None:
    rng = random.Random(20261021)
    for _case in range(40):
        text = _random_form(rng)
        first = _saved(text)
        second = write_ui(_load(first).document).text
        assert second == first


def _random_form(rng: random.Random) -> str:
    widgets = []
    count = rng.randint(1, 6)
    for index in range(count):
        title = "t%s_%s" % (index, rng.choice(["a", "b&c", "d<e", ""]))
        escaped = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        widgets.append(
            '<widget class="QLabel" name="lab%s"><property name="text"><string>%s</string></property></widget>'
            % (index, escaped)
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?><ui version="4.0"><class>Form</class>'
        '<widget class="QWidget" name="Form">%s</widget></ui>' % "".join(widgets)
    )


_QT_CORPUS = Path(__file__).resolve().parents[1] / "corpus" / "qt_examples"


def _corpus_texts(count: int) -> List[str]:
    paths = sorted(_QT_CORPUS.rglob("*.ui"))[:count]
    if not paths:
        pytest.skip("qt_examples corpus is not checked out")
    return [path.read_text(encoding="utf-8") for path in paths]


def test_concurrent_reads_match_sequential() -> None:
    # Overlapping reads used to share module-level reuse pools and corrupt each other.
    texts = _corpus_texts(20)
    expected = [_load(text).document.structure_fingerprint() for text in texts]
    wrong: List[str] = []
    unexpected: List[BaseException] = []
    lock = threading.Lock()

    def work() -> None:
        for _round in range(5):
            for index, text in enumerate(texts):
                try:
                    got = _load(text).document.structure_fingerprint()
                except BaseException as exc:  # recorded, then asserted below
                    with lock:
                        unexpected.append(exc)
                    continue
                if got != expected[index]:
                    with lock:
                        wrong.append("round %s file %s" % (_round, index))

    previous = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    try:
        threads = [threading.Thread(target=work) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    finally:
        sys.setswitchinterval(previous)
    assert not unexpected, "%s reads raised, first: %r" % (len(unexpected), unexpected[0])
    assert not wrong, "%s reads differ from the sequential read, first: %s" % (len(wrong), wrong[0])


class _NestingAllocator(IdAllocator):
    """Starts a second read on the same thread while the first is mid-read."""

    def __init__(self, nested_text: str, every: int) -> None:
        super().__init__()
        self.nested_text = nested_text
        self.every = every
        self.nested: List[str] = []

    def alloc(self) -> NodeId:
        node_id = super().alloc()
        if int(node_id) % self.every == 0:
            nested = read_ui(self.nested_text, allocator=IdAllocator())
            self.nested.append(nested.document.structure_fingerprint())
        return node_id


def test_reentrant_read_from_the_allocator_matches_plain_reads() -> None:
    texts = _corpus_texts(20)
    outer_text = max(texts, key=len)
    nested_text = texts[0] if texts[0] is not outer_text else texts[1]
    expected_outer = _load(outer_text).document.structure_fingerprint()
    expected_nested = _load(nested_text).document.structure_fingerprint()
    allocator = _NestingAllocator(nested_text, every=3)
    outer = read_ui(outer_text, allocator=allocator)
    assert allocator.nested, "the outer read allocated too few ids to nest"
    assert outer.document.structure_fingerprint() == expected_outer
    assert set(allocator.nested) == {expected_nested}
