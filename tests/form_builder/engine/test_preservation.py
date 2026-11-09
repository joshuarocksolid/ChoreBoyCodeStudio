"""Unknown XML must survive a save in the same place."""
from __future__ import annotations

import glob
import os
import random
import re

from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.ui4.reader import UiReadError, read_ui
from app.features.form_builder.engine.ui4.writer import write_ui

_SEED = 20261021
_LEAF = re.compile(r"^(\s*)<([A-Za-z][\w]*)([^<>]*)>([^<]*)</\2>\s*$")
_TAG = re.compile(r"<(/?)([A-Za-z][\w]*)([^<>]*?)(/?)>")


def _saved(text: str) -> str:
    return write_ui(read_ui(text, allocator=IdAllocator()).document).text


def _place(text: str, token: str) -> str:
    """The element that owns an injected attribute, or the parent of a ``zzunk``."""
    stack = []
    for match in _TAG.finditer(text):
        close, tag, _attrs, empty = match.groups()
        if close:
            if stack:
                stack.pop()
            continue
        if token in match.group(0):
            if tag == "zzunk":
                return stack[-1] if stack else ""
            return tag
        if not empty:
            stack.append(tag)
    return ""


def test_opaque_string_space_survives_a_save() -> None:
    text = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <widget class="QWidget" name="Form">
  <property name="odd"><string> </string><string>A</string></property>
 </widget>
</ui>
"""
    loaded = read_ui(text, allocator=IdAllocator())
    saved = write_ui(loaded.document).text
    assert "<string> </string>" in saved
    assert read_ui(saved, allocator=IdAllocator()).document.structure_fingerprint() == loaded.document.structure_fingerprint()
    root = os.path.join(os.path.dirname(__file__), "..", "corpus", "synthetic")
    for path in (
        os.path.join(root, "properties", "brush.ui"),
        os.path.join(root, "properties", "palette.ui"),
        os.path.join(root, "schema", "kitchen_sink.ui"),
    ):
        original = read_ui(open(path, encoding="utf-8").read(), allocator=IdAllocator()).document
        again = read_ui(write_ui(original).text, allocator=IdAllocator()).document
        assert again.structure_fingerprint() == original.structure_fingerprint()


def test_unknown_content_on_typed_leaves_is_kept() -> None:
    text = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <author zz="1">Ada</author>
 <comment>Hi<zzunk n="comment"/></comment>
 <class zz="2">Form<zzunk n="class"/></class>
 <widget class="QWidget" name="Form"/>
 <layoutdefault spacing="nope" zz="3"/>
 <layoutfunction margin="pad" zz="4"/>
 <customwidgets>
  <customwidget>
   <class>Foo</class>
   <extends>QWidget</extends>
   <header location="global" zz="5">foo.h<zzunk n="header"/></header>
   <sizehint>
    <width>10</width>
    <height>20</height>
    <zzunk n="sizehint"/>
   </sizehint>
  </customwidget>
 </customwidgets>
 <tabstops>
  <tabstop>Form</tabstop>
  <tabstop zz="6">nameEdit</tabstop>
  <zzunk n="tabstops"/>
 </tabstops>
 <slots>
  <slot>on_clicked()</slot>
  <zzunk n="slots"/>
 </slots>
 <connections>
  <connection>
   <sender>Form</sender>
   <signal>clicked()</signal>
   <receiver>Form</receiver>
   <slot>on_clicked()</slot>
   <hints>
    <hint>
     <x>1</x>
    </hint>
    <zzunk n="hints"/>
   </hints>
  </connection>
 </connections>
</ui>
"""
    loaded = read_ui(text, allocator=IdAllocator())
    saved = write_ui(loaded.document).text
    for token in (
        'zz="1"',
        'n="comment"',
        'zz="2"',
        'n="class"',
        'spacing="nope"',
        'zz="3"',
        'zz="4"',
        'zz="5"',
        'n="header"',
        'n="sizehint"',
        'zz="6"',
        'n="tabstops"',
        'n="slots"',
        'n="hints"',
    ):
        assert token in saved
    assert "<y>0</y>" not in saved
    assert any(item.code == "FB006" for item in loaded.diagnostics)
    assert read_ui(saved, allocator=IdAllocator()).document.structure_fingerprint() == loaded.document.structure_fingerprint()
    assert _place(saved, 'n="hints"') == "hints"
    assert _place(saved, 'n="slots"') == "slots"
    assert _place(saved, 'n="comment"') == "comment"


def test_seeded_injection_keeps_unknowns_in_place() -> None:
    rng = random.Random(_SEED)
    root = os.path.join(os.path.dirname(__file__), "..", "corpus")
    files = sorted(glob.glob(os.path.join(root, "**", "*.ui"), recursive=True))
    checked = 0
    for path in files:
        if checked >= 20:
            break
        if "/malformed/" in path.replace("\\", "/"):
            continue
        try:
            canon = _saved(open(path, encoding="utf-8").read())
        except (UiReadError, OSError, UnicodeError):
            continue
        injected = _inject(canon, rng, checked)
        if injected is None:
            continue
        xml, tokens = injected
        try:
            saved = _saved(xml)
        except UiReadError as exc:
            raise AssertionError("seed %s dropped %s into an unreadable form" % (_SEED, path)) from exc
        for token, parent in tokens:
            assert token in saved, "seed %s lost %s from %s" % (_SEED, token, path)
            assert _place(saved, token) == parent, "seed %s moved %s in %s" % (_SEED, token, path)
        checked += 1
    assert checked >= 12


def _inject(text: str, rng: random.Random, serial: int):
    lines = text.split("\n")
    leaves = []
    starts = []
    for index, line in enumerate(lines):
        leaf = _LEAF.match(line)
        if leaf and leaf.group(2) not in ("ui",):
            leaves.append(index)
        start = _TAG.search(line.strip())
        if start and not line.strip().startswith("</"):
            starts.append(index)
    if not leaves or not starts:
        return None
    tokens = []
    leaf_at = leaves[rng.randrange(len(leaves))]
    leaf = _LEAF.match(lines[leaf_at])
    assert leaf is not None
    element_token = 'n="z%d"' % serial
    lines[leaf_at] = "%s<%s%s>%s<zzunk %s/></%s>" % (
        leaf.group(1),
        leaf.group(2),
        leaf.group(3),
        leaf.group(4),
        element_token,
        leaf.group(2),
    )
    tokens.append((element_token, leaf.group(2)))
    choices = [index for index in starts if index != leaf_at] or starts
    start_at = choices[rng.randrange(len(choices))]
    start = _TAG.search(lines[start_at])
    assert start is not None
    attr_token = 'zz="%d"' % serial
    _close, tag, attrs, empty = start.groups()
    lines[start_at] = lines[start_at].replace(
        start.group(0),
        "<%s%s %s%s>" % (tag, attrs, attr_token, empty),
        1,
    )
    tokens.append((attr_token, tag))
    return "\n".join(lines), tokens
