"""Hug, Fill, and Fixed round-trip through the document and the .ui text."""

from __future__ import annotations

from typing import Optional

import pytest

from app.features.form_builder.engine.commands.catalog_ext.sizing import ApplySizing, from_write
from app.features.form_builder.engine.sizing import (
    QWIDGET_SIZE_MAX,
    WORD_FILL,
    WORD_FIXED,
    WORD_HUG,
    AxisFacts,
    ShareSlot,
    chip_axis,
    clear_property,
    effective_word,
    encode_axis,
    explain,
    outlined_word,
    preview_pill,
    project_axis,
    reset_words,
    share_slots,
    splice_stretch,
    stretch_at,
)
from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.engine.ui4.reader import read_ui
from app.features.form_builder.engine.ui4.values import SizePolicyValue, SizeValue
from app.features.form_builder.engine.ui4.writer import write_ui
from tests.form_builder.engine.commands._support import BOX, GRID, nid, open_log

_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <layout class="QFormLayout" name="formLayout">
   <item row="0" column="0">
    <widget class="QLabel" name="label"><property name="text"><string>Email</string></property></widget>
   </item>
   <item row="0" column="1">
    <widget class="QLineEdit" name="email"/>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


def test_hug_fill_and_fixed_round_trip_the_words() -> None:
    cases = ((WORD_HUG, None), (WORD_FILL, None), (WORD_FIXED, 240))
    for word, pixels in cases:
        write = encode_axis(
            axis="h",
            word=word,
            pixels=pixels,
            current_policy=None,
            current_minimum=None,
            current_maximum=None,
            class_default_h="Preferred",
            class_default_v="Preferred",
        )
        assert write.policy is not None
        minimum = None if write.minimum is None else write.minimum.width
        maximum = None if write.maximum is None else write.maximum.width
        viewed = project_axis(
            stored_policy=write.policy.hsizetype,
            minimum=minimum,
            maximum=maximum,
            class_default_policy="Preferred",
            class_phrase="line edit",
        )
        assert viewed.word == word
        assert viewed.filled
        assert not viewed.custom
        if word == WORD_FIXED:
            assert viewed.pixels == 240
        else:
            assert viewed.pixels is None


def test_an_unstored_soft_default_is_outlined_hug() -> None:
    viewed = project_axis(
        stored_policy=None,
        minimum=None,
        maximum=None,
        class_default_policy="Preferred",
        class_phrase="line edit",
    )
    assert viewed.word == WORD_HUG
    assert not viewed.filled
    assert viewed.caption == (
        "Default for a line edit: hugs its content, and grows when nothing else wants the room."
    )


def test_a_designer_minimum_is_custom_and_the_chip_omits_it() -> None:
    viewed = project_axis(
        stored_policy="Minimum",
        minimum=None,
        maximum=None,
        class_default_policy="Preferred",
        class_phrase="line edit",
    )
    assert viewed.custom
    assert viewed.word is None
    assert not viewed.filled
    assert viewed.caption.startswith("Custom: Minimum — grows, never smaller than its content.")
    assert effective_word("Minimum", False) is None


def test_reset_removes_minimum_size_from_the_xml() -> None:
    log = open_log(BOX)
    button = nid(log.document, "okButton")
    log.execute(
        ApplySizing(button, minimum=SizeValue(80, 24), touch_minimum=True)
    )
    assert 'name="minimumSize"' in write_ui(log.document).text
    log.execute(from_write(button, clear_property("minimumSize")))
    text = write_ui(log.document).text
    assert "minimumSize" not in text
    assert log.undo_label() == "Reset"
    assert log.undo()
    assert 'name="minimumSize"' in write_ui(log.document).text


def test_one_sizing_edit_is_one_undo_and_writes_no_geometry() -> None:
    log = open_log(BOX)
    original = write_ui(log.document).text
    button = nid(log.document, "okButton")
    label = nid(log.document, "label")
    write = encode_axis(
        axis="v",
        word=WORD_FILL,
        pixels=None,
        current_policy=None,
        current_minimum=None,
        current_maximum=None,
        class_default_h="Preferred",
        class_default_v="Preferred",
    )
    stretched = splice_stretch(None, 1, 1, 2)
    log.execute(from_write(button, write, layout=nid(log.document, "verticalLayout"), stretch_field="stretch", stretch=stretched))
    assert log.undo_label() == "Size"
    saved = write_ui(log.document).text
    assert "<x>" not in saved
    assert "<y>" not in saved
    assert 'hsizetype="Expanding"' in saved or 'vsizetype="Expanding"' in saved
    assert 'stretch="0,1"' in saved
    assert log.undo()
    assert not log.can_undo()
    assert write_ui(log.document).text == original
    untouched = log.document.get(label)
    assert isinstance(untouched, WidgetNode)
    assert untouched.prop("geometry") is None


def test_fixed_then_reset_leaves_no_size_policy_or_lock() -> None:
    log = open_log(BOX)
    button = nid(log.document, "okButton")
    write = encode_axis(
        axis="h",
        word=WORD_FIXED,
        pixels=180,
        current_policy=None,
        current_minimum=None,
        current_maximum=None,
        class_default_h="Preferred",
        class_default_v="Preferred",
    )
    log.execute(from_write(button, write))
    text = write_ui(log.document).text
    assert "minimumSize" in text
    assert "maximumSize" in text
    assert "sizePolicy" in text
    node = log.document.get(button)
    assert isinstance(node, WidgetNode)
    policy = node.prop("sizePolicy")
    minimum = node.prop("minimumSize")
    maximum = node.prop("maximumSize")
    policy_value = None if policy is None else policy.value
    minimum_value = None if minimum is None else minimum.value
    maximum_value = None if maximum is None else maximum.value
    assert isinstance(policy_value, SizePolicyValue)
    assert isinstance(minimum_value, SizeValue)
    assert isinstance(maximum_value, SizeValue)
    log.execute(
        from_write(
            button,
            reset_words(
                current_policy=policy_value,
                current_minimum=minimum_value,
                current_maximum=maximum_value,
            ),
        )
    )
    cleared = write_ui(log.document).text
    assert "sizePolicy" not in cleared
    assert "minimumSize" not in cleared
    assert "maximumSize" not in cleared


def test_share_slots_follow_the_parent_layout() -> None:
    box = open_log(BOX).document
    assert share_slots(box, nid(box, "okButton"))[0].axis == "v"
    assert share_slots(box, nid(box, "label")) == (ShareSlot(nid(box, "verticalLayout"), "stretch", 1, "v"),)
    grid = open_log(GRID).document
    slots = share_slots(grid, nid(grid, "b"))
    assert {slot.axis for slot in slots} == {"h", "v"}
    form = read_ui(_FORM, allocator=IdAllocator()).document
    email = next(node.id for node in form.iter_preorder() if isinstance(node, WidgetNode) and node.object_name == "email")
    assert share_slots(form, email) == ()


def test_splice_stretch_drops_an_all_zero_list() -> None:
    assert splice_stretch("0,1", 1, 0, 2) is None
    assert splice_stretch(None, 1, 2, 2) == "0,2"
    assert stretch_at("0,2", 1) == 2


def test_why_text_uses_only_the_measured_numbers() -> None:
    facts = (
        AxisFacts(
            "Width",
            120,
            80,
            0,
            QWIDGET_SIZE_MAX,
            "Expanding",
            WORD_FILL,
            1,
            3,
            40,
            "vertical layout",
            "push button",
            False,
            False,
            False,
            False,
            False,
        ),
        AxisFacts(
            "Height",
            28,
            28,
            0,
            QWIDGET_SIZE_MAX,
            "Fixed",
            WORD_HUG,
            0,
            0,
            0,
            "vertical layout",
            "push button",
            False,
            False,
            False,
            False,
            False,
        ),
    )
    text = explain(120, 28, facts, qt_names=False)
    assert text.startswith("120 × 28 px.")
    assert "It gets 1 of every 3 px of spare room (share 1 of 3)." in text
    assert "what a push button needs for its content: 28 px." in text


_POLICIES = (
    "Fixed",
    "Minimum",
    "Maximum",
    "Preferred",
    "Expanding",
    "MinimumExpanding",
    "Ignored",
)


def _view(
    policy: str,
    default: str,
    minimum: Optional[int] = None,
    maximum: Optional[int] = None,
):
    return project_axis(
        stored_policy=policy,
        minimum=minimum,
        maximum=maximum,
        class_default_policy=default,
        class_phrase="push button",
    )


@pytest.mark.parametrize("policy", _POLICIES)
def test_a_stored_policy_fills_only_an_exact_encoding(policy: str) -> None:
    default = "Minimum" if policy != "Minimum" else "Preferred"
    viewed = _view(policy, default)
    if policy == "Fixed":
        assert viewed.word == WORD_HUG and viewed.filled and not viewed.custom
    elif policy == "Expanding":
        assert viewed.word == WORD_FILL and viewed.filled and not viewed.custom
    else:
        assert viewed.custom and viewed.word is None and not viewed.filled
        assert viewed.policy_name == policy
        assert chip_axis(viewed) == policy
    assert effective_word(policy, False) == (
        WORD_HUG if policy == "Fixed" else WORD_FILL if policy == "Expanding" else None
    )


@pytest.mark.parametrize("policy", _POLICIES)
def test_a_stored_class_default_stays_outlined(policy: str) -> None:
    viewed = _view(policy, policy)
    assert not viewed.filled and not viewed.custom
    assert viewed.word == outlined_word(policy)
    assert chip_axis(viewed) == viewed.word


def test_a_locked_fixed_axis_is_fixed_even_when_that_is_the_class_default() -> None:
    viewed = _view("Fixed", "Fixed", 40, 40)
    assert viewed.word == WORD_FIXED and viewed.filled and viewed.pixels == 40
    assert chip_axis(viewed) == WORD_FIXED


def test_mixed_axes_do_not_share_one_segment() -> None:
    hug = _view("Fixed", "Preferred")
    custom = _view("Ignored", "Preferred")
    assert (hug.word, hug.filled, hug.custom) != (custom.word, custom.filled, custom.custom)
    assert chip_axis(hug) == WORD_HUG
    assert chip_axis(custom) == "Ignored"


def test_picking_the_class_default_stores_no_policy() -> None:
    write = encode_axis(
        axis="h",
        word=WORD_FILL,
        pixels=None,
        current_policy=None,
        current_minimum=None,
        current_maximum=None,
        class_default_h="Expanding",
        class_default_v="Fixed",
    )
    assert write.policy is None
    assert write.minimum is None and write.maximum is None


def test_fill_keeps_an_at_least_and_clears_only_a_lock() -> None:
    kept = encode_axis(
        axis="h",
        word=WORD_FILL,
        pixels=None,
        current_policy=None,
        current_minimum=SizeValue(200, 0),
        current_maximum=None,
        class_default_h="Preferred",
        class_default_v="Preferred",
    )
    assert kept.minimum is not None and kept.minimum.width == 200
    cleared = encode_axis(
        axis="h",
        word=WORD_HUG,
        pixels=None,
        current_policy=None,
        current_minimum=SizeValue(80, 0),
        current_maximum=SizeValue(80, QWIDGET_SIZE_MAX),
        class_default_h="Preferred",
        class_default_v="Preferred",
    )
    assert cleared.minimum is None
    assert cleared.maximum is None


def test_a_squeezed_axis_cannot_go_below_the_hint() -> None:
    facts = (
        AxisFacts(
            "Width",
            30,
            80,
            0,
            QWIDGET_SIZE_MAX,
            "Minimum",
            None,
            0,
            0,
            0,
            "horizontal layout",
            "push button",
            False,
            False,
            False,
            True,
            False,
            minimum_hint=23,
        ),
    )
    text = explain(30, 24, facts, qt_names=False)
    assert "can't go below 23 px." in text
    assert "can't go below 0 px." not in text


def test_hug_with_a_maximum_names_the_maximum_when_the_size_is_not_the_hint() -> None:
    facts = (
        AxisFacts(
            "Width",
            160,
            105,
            0,
            160,
            "Fixed",
            WORD_HUG,
            0,
            0,
            0,
            "horizontal layout",
            "push button",
            False,
            True,
            False,
            False,
            False,
        ),
    )
    text = explain(160, 28, facts, qt_names=False)
    assert "stops at its maximum of 160 px." in text
    assert "needs" not in text


def test_preview_pill_is_absent_at_normal_and_names_a_cutoff() -> None:
    assert preview_pill(10, 1.0, 100, None, 0) is None
    assert preview_pill(10, 1.0, 100, None, 3) is None
    assert preview_pill(10, 1.25, 100, None, 0) == "Previewing larger text · Reset"
    assert preview_pill(10, 1.25, 100, None, 2) == "Previewing larger text · 2 widgets cut off text · Reset"
    assert preview_pill(10, 1.0, 100, 16, 0) == "Previewing larger text · Reset"
    assert preview_pill(10, 1.0, 150, None, 0) == "Previewing 150% screen · Reset"
