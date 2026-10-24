"""Size words projected onto Qt policy, limits, and stretch."""

from __future__ import annotations

from typing import Optional, Tuple

import pytest

from app.features.form_builder.engine.commands.catalog import (
    SetGeometry,
    SetLayoutStretch,
    SetProperty,
    SetPropertyMany,
)
from app.features.form_builder.engine.commands.log import CommandLog
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.sizing import (
    AxisMode,
    AxisView,
    Custom,
    Empty,
    Fill,
    Fixed,
    Hug,
    LimitView,
    MixedLimit,
    Outlined,
    Pixels,
    ResetLimits,
    ResetPolicy,
    SetLimit,
    SetShare,
    SetWord,
    ShareView,
    SizeEdit,
    SizeFacts,
    SizePanel,
    WhyLive,
    can_grow,
    chip_words,
    cuts_off,
    edit_label,
    facts_from_document,
    plan,
    project,
    qt_policy_text,
    why_lines,
)
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.engine.ui4.values import SizePolicyValue, SizeValue
from app.features.form_builder.engine.ui4.writer import write_ui
from tests.form_builder.engine.commands._support import nid, open_log

pytestmark = pytest.mark.unit

_TIMES = "\u00d7"
_QT_MAX = 16777215
_CATALOG = (SetProperty, SetPropertyMany, SetLayoutStretch)


def _ui(inner: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<ui version="4.0">\n'
        " <class>Form</class>\n"
        ' <widget class="QWidget" name="Form">\n'
        "%s"
        " </widget>\n"
        " <resources/>\n"
        " <connections/>\n"
        "</ui>\n"
    ) % inner


def _column(*names: str) -> str:
    items = []
    for name in names:
        items.append(
            "  <item>\n"
            '   <widget class="QPushButton" name="%s">\n'
            '    <property name="text"><string>%s</string></property>\n'
            "   </widget>\n"
            "  </item>\n" % (name, name)
        )
    return _ui(
        '  <layout class="QVBoxLayout" name="verticalLayout">\n'
        "%s"
        "  </layout>\n" % "".join(items)
    )


def _button_with_policy(
    horizontal: str,
    vertical: str,
    horstretch: int = 0,
    verstretch: int = 0,
    minimum: Optional[Tuple[int, int]] = None,
    maximum: Optional[Tuple[int, int]] = None,
) -> str:
    parts = ['   <widget class="QPushButton" name="okButton">\n']
    if horizontal or vertical:
        parts.append(
            '    <property name="sizePolicy">\n'
            '     <sizepolicy hsizetype="%s" vsizetype="%s">\n'
            "      <horstretch>%d</horstretch>\n"
            "      <verstretch>%d</verstretch>\n"
            "     </sizepolicy>\n"
            "    </property>\n" % (horizontal, vertical, horstretch, verstretch)
        )
    if minimum is not None:
        parts.append(
            '    <property name="minimumSize">\n'
            "     <size><width>%d</width><height>%d</height></size>\n"
            "    </property>\n" % minimum
        )
    if maximum is not None:
        parts.append(
            '    <property name="maximumSize">\n'
            "     <size><width>%d</width><height>%d</height></size>\n"
            "    </property>\n" % maximum
        )
    parts.append("   </widget>\n")
    return _ui(
        '  <layout class="QVBoxLayout" name="verticalLayout">\n'
        "   <item>\n"
        "%s"
        "   </item>\n"
        "  </layout>\n" % "".join(parts)
    )


def _facts(
    doc: UiDocument,
    name: str,
    class_h: str,
    class_v: str,
    friendly: str = "Push button",
) -> SizeFacts:
    node = doc.node(nid(doc, name))
    assert isinstance(node, WidgetNode)
    return facts_from_document(doc, node, class_h, class_v, friendly)


def _apply(log: CommandLog, facts: Tuple[SizeFacts, ...], edit: SizeEdit):
    commands = plan(facts, edit)
    with log.transaction(edit_label(edit)) as txn:
        for command in commands:
            txn.execute(command)
    return commands


def _xml(doc: UiDocument) -> str:
    return write_ui(doc).text


def _widget_body(xml: str, class_name: str, name: str) -> str:
    token = '<widget class="%s" name="%s">' % (class_name, name)
    start = xml.index(token)
    end = xml.index("</widget>", start)
    return xml[start:end]


def _policy(doc: UiDocument, name: str) -> Optional[SizePolicyValue]:
    value = doc.node(nid(doc, name)).value("sizePolicy")
    if value is None:
        return None
    assert isinstance(value, SizePolicyValue)
    return value


def _size(doc: UiDocument, name: str, prop: str) -> Optional[SizeValue]:
    value = doc.node(nid(doc, name)).value(prop)
    if value is None:
        return None
    assert isinstance(value, SizeValue)
    return value


def _live(**overrides: object) -> WhyLive:
    values = {
        "width": 180,
        "height": 40,
        "hint_w": 80,
        "hint_h": 24,
        "min_hint_w": 10,
        "min_hint_h": 8,
        "min_w": 0,
        "min_h": 0,
        "max_w": _QT_MAX,
        "max_h": _QT_MAX,
        "share_k": 0,
        "share_total": 0,
        "parent_phrase": "vertical layout",
        "class_friendly": "Push button",
        "form_label_width": None,
        "canvas_floor": False,
        "policy_h": "Preferred",
        "policy_v": "Fixed",
    }
    values.update(overrides)
    return WhyLive(**values)  # type: ignore[arg-type]


def _panel(horizontal: AxisMode, vertical: AxisMode) -> SizePanel:
    return SizePanel(
        horizontal=AxisView(horizontal, "", True, isinstance(horizontal, Fixed)),
        vertical=AxisView(vertical, "", True, isinstance(vertical, Fixed)),
        at_least=LimitView(Empty(), Empty(), False),
        at_most=LimitView(Empty(), Empty(), False),
        share_width=ShareView(False, None, False, False, ""),
        share_height=ShareView(False, None, False, False, ""),
        why_owner=NodeId(1),
    )


def _texts(panel: SizePanel, live: WhyLive) -> Tuple[str, ...]:
    return tuple(line.text for line in why_lines(panel, live))


def test_class_default_minimum_outlines_hug() -> None:
    log = open_log(_column("okButton"))
    panel = project((_facts(log.document, "okButton", "Minimum", "Fixed"),))
    mode = panel.horizontal.mode
    assert isinstance(mode, Outlined)
    assert mode.word == "Hug"
    assert mode.soft is True
    assert mode.policy_name == "Minimum"
    assert panel.horizontal.changed is False
    assert panel.horizontal.caption == (
        "Default for a push button: hugs its content, "
        "and grows when nothing else wants the room."
    )
    assert chip_words(panel) == ("Hug", "Hug")


def test_stored_minimum_drops_that_axis_from_the_chip() -> None:
    log = open_log(_button_with_policy("Minimum", "Expanding"))
    panel = project((_facts(log.document, "okButton", "Preferred", "Preferred"),))
    mode = panel.horizontal.mode
    assert isinstance(mode, Custom)
    assert mode.policy_name == "Minimum"
    assert panel.horizontal.caption == (
        "Custom: Minimum \u2014 grows, never smaller than its content. "
        "Change it in All properties, or pick a word to replace it."
    )
    assert chip_words(panel) == (None, "Fill")


def test_hug_on_a_laid_out_button_writes_fixed_without_geometry() -> None:
    log = open_log(_column("okButton"))
    facts = (_facts(log.document, "okButton", "Minimum", "Preferred"),)
    commands = _apply(log, facts, SetWord("width", "Hug", None))
    assert commands
    policy = _policy(log.document, "okButton")
    assert policy is not None
    assert policy.hsizetype == "Fixed"
    assert policy.vsizetype == "Preferred"
    body = _widget_body(_xml(log.document), "QPushButton", "okButton")
    assert 'hsizetype="Fixed"' in body
    assert 'name="geometry"' not in body
    assert "<x>" not in body
    assert "<y>" not in body


def test_second_button_in_a_column_fills_with_stretch_one() -> None:
    log = open_log(_column("first", "second"))
    _apply(
        log,
        (_facts(log.document, "second", "Minimum", "Preferred"),),
        SetWord("height", "Fill", None),
    )
    _apply(
        log,
        (_facts(log.document, "second", "Minimum", "Preferred"),),
        SetShare("height", 1),
    )
    policy = _policy(log.document, "second")
    assert policy is not None
    assert policy.vsizetype == "Expanding"
    assert policy.horstretch == 0
    assert policy.verstretch == 0
    layout = log.document.root.layout
    assert layout is not None
    assert layout.field("stretch") == "0,1"
    assert 'stretch="0,1"' in _xml(log.document)
    assert _policy(log.document, "first") is None
    panel = project((_facts(log.document, "second", "Minimum", "Preferred"),))
    assert panel.vertical.mode == Fill()
    assert panel.share_height.shown is True
    assert panel.share_height.factor == 1
    assert panel.share_width.shown is False
    assert [entry.label for entry in log.entries()] == ["Fill height", "Share"]


def test_fixed_80_writes_equal_minimum_and_maximum() -> None:
    log = open_log(_column("okButton"))
    _apply(
        log,
        (_facts(log.document, "okButton", "Minimum", "Preferred"),),
        SetWord("width", "Fixed", 80),
    )
    assert _size(log.document, "okButton", "minimumSize") == SizeValue(80, 0)
    assert _size(log.document, "okButton", "maximumSize") == SizeValue(80, _QT_MAX)
    policy = _policy(log.document, "okButton")
    assert policy is not None
    assert policy.hsizetype == "Fixed"
    assert "<width>80</width>" in _xml(log.document)
    panel = project((_facts(log.document, "okButton", "Minimum", "Preferred"),))
    assert panel.horizontal.mode == Fixed(80)


def test_reset_minimum_removes_the_minimum_size_element() -> None:
    log = open_log(_column("okButton"))
    _apply(
        log,
        (_facts(log.document, "okButton", "Minimum", "Preferred"),),
        SetLimit("minimum", "width", 24),
    )
    assert "minimumSize" in _xml(log.document)
    assert _size(log.document, "okButton", "minimumSize") == SizeValue(24, 0)
    _apply(
        log,
        (_facts(log.document, "okButton", "Minimum", "Preferred"),),
        ResetLimits("minimum"),
    )
    assert "minimumSize" not in _xml(log.document)
    assert _size(log.document, "okButton", "minimumSize") is None


def test_plan_does_not_emit_set_geometry() -> None:
    log = open_log(_column("okButton"))
    facts = (_facts(log.document, "okButton", "Minimum", "Preferred"),)
    commands = plan(facts, SetWord("width", "Fixed", 80))
    assert commands
    assert not any(isinstance(command, SetGeometry) for command in commands)
    assert all(isinstance(command, _CATALOG) for command in commands)
    _apply(log, facts, SetWord("width", "Fixed", 80))
    body = _widget_body(_xml(log.document), "QPushButton", "okButton")
    assert 'name="geometry"' not in body
    assert "<x>" not in body
    assert "<y>" not in body


def test_a_second_identical_hug_plan_is_empty() -> None:
    log = open_log(_column("okButton"))
    edit = SetWord("width", "Hug", None)
    facts = (_facts(log.document, "okButton", "Minimum", "Preferred"),)
    first = _apply(log, facts, edit)
    assert first
    before = len(log.entries())
    second = plan((_facts(log.document, "okButton", "Minimum", "Preferred"),), edit)
    assert second == ()
    _apply(log, (_facts(log.document, "okButton", "Minimum", "Preferred"),), edit)
    assert len(log.entries()) == before


def test_why_lines_quotes_the_live_width_and_height() -> None:
    panel = _panel(Custom("Minimum"), Custom("Preferred"))
    narrow = _texts(panel, _live(width=180, height=40))
    wide = _texts(panel, _live(width=640, height=480))
    assert narrow == ("180 %s 40 px." % _TIMES,)
    assert wide == ("640 %s 480 px." % _TIMES,)


def test_undo_of_the_hug_transaction_restores_the_document() -> None:
    log = open_log(_column("okButton"))
    before = _xml(log.document)
    edit = SetWord("width", "Hug", None)
    commands = _apply(
        log,
        (_facts(log.document, "okButton", "Minimum", "Preferred"),),
        edit,
    )
    assert commands
    assert len(log.entries()) == 1
    assert log.undo_label() == "Hug width"
    assert _xml(log.document) != before
    assert log.undo() is True
    assert _xml(log.document) == before
    assert log.entries() == ()


def test_stored_fixed_with_an_equal_pin_projects_fixed_pixels() -> None:
    log = open_log(_button_with_policy("Fixed", "Preferred", minimum=(80, 0), maximum=(80, _QT_MAX)))
    panel = project((_facts(log.document, "okButton", "Preferred", "Preferred"),))
    assert panel.horizontal.mode == Fixed(80)
    assert panel.horizontal.hide_limits is True
    assert chip_words(panel)[0] == "Fixed"


def test_stored_fixed_without_an_equal_pin_projects_hug() -> None:
    log = open_log(_button_with_policy("Fixed", "Preferred", minimum=(10, 0), maximum=(40, 90)))
    panel = project((_facts(log.document, "okButton", "Preferred", "Preferred"),))
    assert panel.horizontal.mode == Hug()
    assert panel.horizontal.hide_limits is False
    assert chip_words(panel)[0] == "Hug"


def test_a_width_edit_keeps_the_height_policy_and_the_stretches() -> None:
    log = open_log(_button_with_policy("Expanding", "Minimum", horstretch=2, verstretch=5))
    _apply(
        log,
        (_facts(log.document, "okButton", "Preferred", "Fixed"),),
        SetWord("width", "Hug", None),
    )
    policy = _policy(log.document, "okButton")
    assert policy == SizePolicyValue("Fixed", "Minimum", 2, 5)


def test_hug_clears_an_equal_pin_on_that_axis() -> None:
    log = open_log(_button_with_policy("Fixed", "Preferred", minimum=(80, 4), maximum=(80, 200)))
    _apply(
        log,
        (_facts(log.document, "okButton", "Preferred", "Preferred"),),
        SetWord("width", "Hug", None),
    )
    assert _size(log.document, "okButton", "minimumSize") == SizeValue(0, 4)
    assert _size(log.document, "okButton", "maximumSize") == SizeValue(_QT_MAX, 200)
    panel = project((_facts(log.document, "okButton", "Preferred", "Preferred"),))
    assert panel.horizontal.mode == Hug()


def test_reset_width_deletes_size_policy_when_both_axes_match() -> None:
    log = open_log(_button_with_policy("Fixed", "Preferred"))
    _apply(
        log,
        (_facts(log.document, "okButton", "Preferred", "Preferred"),),
        ResetPolicy("width"),
    )
    assert _policy(log.document, "okButton") is None
    assert "sizePolicy" not in _xml(log.document)


def test_share_reset_drops_the_stretch_field_when_every_factor_is_zero() -> None:
    text = _ui(
        '  <layout class="QVBoxLayout" name="verticalLayout" stretch="0,1">\n'
        "   <item>\n"
        '    <widget class="QPushButton" name="first"/>\n'
        "   </item>\n"
        "   <item>\n"
        '    <widget class="QPushButton" name="second"/>\n'
        "   </item>\n"
        "  </layout>\n"
    )
    log = open_log(text)
    _apply(
        log,
        (_facts(log.document, "second", "Minimum", "Preferred"),),
        SetShare("height", None),
    )
    layout = log.document.root.layout
    assert layout is not None
    assert layout.field("stretch") is None
    assert "stretch=" not in _xml(log.document)


def test_a_new_minimum_fills_the_other_axis_with_zero() -> None:
    log = open_log(_column("okButton"))
    _apply(
        log,
        (_facts(log.document, "okButton", "Minimum", "Preferred"),),
        SetLimit("minimum", "height", 15),
    )
    assert _size(log.document, "okButton", "minimumSize") == SizeValue(0, 15)


def test_a_maximum_at_the_sentinel_displays_empty() -> None:
    log = open_log(
        _button_with_policy("Preferred", "Preferred", maximum=(100, _QT_MAX))
    )
    panel = project((_facts(log.document, "okButton", "Preferred", "Preferred"),))
    assert panel.at_most.width == Pixels(100)
    assert panel.at_most.height == Empty()
    assert panel.at_most.changed is True
    bare = project(( _facts(open_log(_column("okButton")).document, "okButton", "Preferred", "Preferred"),))
    assert bare.at_most.width == Empty()
    assert bare.at_most.changed is False


def test_horizontal_layout_share_is_the_width_stretch() -> None:
    text = _ui(
        '  <layout class="QHBoxLayout" name="horizontalLayout">\n'
        "   <item>\n"
        '    <widget class="QPushButton" name="first"/>\n'
        "   </item>\n"
        "   <item>\n"
        '    <widget class="QPushButton" name="second"/>\n'
        "   </item>\n"
        "  </layout>\n"
    )
    log = open_log(text)
    before = project((_facts(log.document, "second", "Minimum", "Preferred"),))
    assert before.share_width.shown is True
    assert before.share_height.shown is False
    _apply(
        log,
        (_facts(log.document, "second", "Minimum", "Preferred"),),
        SetShare("width", 1),
    )
    layout = log.document.root.layout
    assert layout is not None
    assert layout.field("stretch") == "0,1"


def test_grid_share_writes_columnstretch_for_width() -> None:
    text = _ui(
        '  <layout class="QGridLayout" name="gridLayout">\n'
        '   <item row="0" column="1">\n'
        '    <widget class="QPushButton" name="cell"/>\n'
        "   </item>\n"
        "  </layout>\n"
    )
    log = open_log(text)
    panel = project((_facts(log.document, "cell", "Minimum", "Preferred"),))
    assert panel.share_width.shown is True
    assert panel.share_height.shown is True
    _apply(
        log,
        (_facts(log.document, "cell", "Minimum", "Preferred"),),
        SetShare("width", 2),
    )
    layout = log.document.root.layout
    assert layout is not None
    assert layout.field("columnstretch") == "0,2"
    assert layout.field("rowstretch") is None


def test_splitter_share_writes_the_child_policy_stretch() -> None:
    text = _ui(
        '  <widget class="QSplitter" name="split">\n'
        '   <property name="orientation"><enum>Qt::Horizontal</enum></property>\n'
        '   <widget class="QPushButton" name="pane"/>\n'
        "  </widget>\n"
    )
    log = open_log(text)
    panel = project((_facts(log.document, "pane", "Preferred", "Fixed"),))
    assert panel.share_width.shown is True
    assert panel.share_width.factor == 0
    assert panel.share_height.shown is False
    _apply(
        log,
        (_facts(log.document, "pane", "Preferred", "Fixed"),),
        SetShare("width", 3),
    )
    assert _policy(log.document, "pane") == SizePolicyValue("Preferred", "Fixed", 3, 0)


def test_two_selected_siblings_share_one_stretch_command() -> None:
    log = open_log(_column("first", "second"))
    facts = (
        _facts(log.document, "first", "Minimum", "Preferred"),
        _facts(log.document, "second", "Minimum", "Preferred"),
    )
    commands = plan(facts, SetShare("height", 1))
    assert len(commands) == 1
    assert isinstance(commands[0], SetLayoutStretch)
    _apply(log, facts, SetShare("height", 1))
    layout = log.document.root.layout
    assert layout is not None
    assert layout.field("stretch") == "1,1"


def test_a_width_edit_keeps_each_widgets_height_policy() -> None:
    text = _ui(
        '  <layout class="QVBoxLayout" name="verticalLayout">\n'
        "   <item>\n"
        '    <widget class="QPushButton" name="one">\n'
        '     <property name="sizePolicy">\n'
        '      <sizepolicy hsizetype="Expanding" vsizetype="Minimum">\n'
        "       <horstretch>0</horstretch>\n"
        "       <verstretch>0</verstretch>\n"
        "      </sizepolicy>\n"
        "     </property>\n"
        "    </widget>\n"
        "   </item>\n"
        "   <item>\n"
        '    <widget class="QPushButton" name="two">\n'
        '     <property name="sizePolicy">\n'
        '      <sizepolicy hsizetype="Preferred" vsizetype="Fixed">\n'
        "       <horstretch>1</horstretch>\n"
        "       <verstretch>4</verstretch>\n"
        "      </sizepolicy>\n"
        "     </property>\n"
        "    </widget>\n"
        "   </item>\n"
        "  </layout>\n"
    )
    log = open_log(text)
    facts = (
        _facts(log.document, "one", "Preferred", "Preferred"),
        _facts(log.document, "two", "Expanding", "Expanding"),
    )
    commands = plan(facts, SetWord("width", "Hug", None))
    assert all(isinstance(command, SetProperty) for command in commands)
    _apply(log, facts, SetWord("width", "Hug", None))
    assert _policy(log.document, "one") == SizePolicyValue("Fixed", "Minimum", 0, 0)
    assert _policy(log.document, "two") == SizePolicyValue("Fixed", "Fixed", 1, 4)


def test_limits_that_differ_across_a_selection_are_mixed() -> None:
    text = _ui(
        '  <layout class="QVBoxLayout" name="verticalLayout">\n'
        "   <item>\n"
        '    <widget class="QPushButton" name="one">\n'
        '     <property name="minimumSize">\n'
        "      <size><width>10</width><height>0</height></size>\n"
        "     </property>\n"
        "    </widget>\n"
        "   </item>\n"
        "   <item>\n"
        '    <widget class="QPushButton" name="two">\n'
        '     <property name="minimumSize">\n'
        "      <size><width>20</width><height>0</height></size>\n"
        "     </property>\n"
        "    </widget>\n"
        "   </item>\n"
        "  </layout>\n"
    )
    log = open_log(text)
    panel = project(
        (
            _facts(log.document, "one", "Preferred", "Preferred"),
            _facts(log.document, "two", "Preferred", "Preferred"),
        )
    )
    assert panel.at_least.width == MixedLimit()
    assert panel.at_least.changed is True


def test_group_box_phrase_keeps_the_vertical_share() -> None:
    text = _ui(
        '  <widget class="QGroupBox" name="Receipts">\n'
        '   <layout class="QVBoxLayout" name="verticalLayout">\n'
        "    <item>\n"
        '     <widget class="QPushButton" name="okButton"/>\n'
        "    </item>\n"
        "   </layout>\n"
        "  </widget>\n"
    )
    log = open_log(text)
    fact = _facts(log.document, "okButton", "Minimum", "Preferred")
    assert fact.parent_phrase == "group box Receipts"
    panel = project((fact,))
    assert panel.share_height.shown is True
    assert panel.share_width.shown is False


def test_a_form_label_is_marked_from_its_cell() -> None:
    text = _ui(
        '  <layout class="QFormLayout" name="formLayout">\n'
        '   <item row="0" column="0">\n'
        '    <widget class="QLabel" name="nameLabel"/>\n'
        "   </item>\n"
        '   <item row="0" column="1">\n'
        '    <widget class="QLineEdit" name="nameEdit"/>\n'
        "   </item>\n"
        "  </layout>\n"
    )
    log = open_log(text)
    label = _facts(log.document, "nameLabel", "Preferred", "Preferred", "Label")
    field = _facts(log.document, "nameEdit", "Expanding", "Fixed", "Line edit")
    assert label.is_form_label is True
    assert field.is_form_label is False
    assert label.share is None
    assert label.parent_phrase == "form layout"


def test_can_grow_follows_the_policy_name() -> None:
    assert can_grow(Hug()) is False
    assert can_grow(Fixed(10)) is False
    assert can_grow(Fill()) is True
    assert can_grow(Outlined("Hug", True, "Minimum")) is True
    assert can_grow(Outlined("Hug", True, "Maximum")) is True
    assert can_grow(Outlined("Hug", False, "Fixed")) is False
    assert can_grow(Outlined("Fill", False, "Ignored")) is True
    assert can_grow(Custom("Maximum")) is False
    assert can_grow(Custom("Minimum")) is True
    assert can_grow(Custom("Expanding")) is True


def test_cuts_off_when_the_hint_exceeds_a_size_that_cannot_grow() -> None:
    assert cuts_off(40, 20, 80, 20, Hug(), Fill()) is True
    assert cuts_off(40, 20, 80, 20, Fill(), Fill()) is False
    assert cuts_off(100, 50, 80, 20, Hug(), Hug()) is False


@pytest.mark.parametrize(
    ("horizontal", "vertical", "live", "expected"),
    [
        (
            Fixed(80),
            Hug(),
            {"width": 111, "hint_h": 24},
            (
                "111 %s 40 px." % _TIMES,
                "Width is fixed at 80 px.",
                "Height is what a push button needs for its content: 24 px.",
            ),
        ),
        (
            Fill(),
            Hug(),
            {"max_w": 120, "width": 120, "share_k": 1, "share_total": 3},
            (
                "120 %s 40 px." % _TIMES,
                "Width would fill, but stops at its maximum of 120 px.",
                "Height is what a push button needs for its content: 24 px.",
            ),
        ),
        (
            Fill(),
            Hug(),
            {"share_k": 1, "share_total": 3, "parent_phrase": "vertical layout"},
            (
                "180 %s 40 px." % _TIMES,
                "It gets 1 of every 3 px of spare room (share 1 of 3).",
                "Height is what a push button needs for its content: 24 px.",
            ),
        ),
        (
            Fill(),
            Hug(),
            {"parent_phrase": "group box Receipts"},
            (
                "180 %s 40 px." % _TIMES,
                "Width fills the room the group box Receipts gives it.",
                "Height is what a push button needs for its content: 24 px.",
            ),
        ),
        (
            Outlined("Hug", True, "Preferred"),
            Hug(),
            {"width": 200, "hint_w": 40},
            (
                "200 %s 40 px." % _TIMES,
                "Width grew past the 40 px it asks for, because nothing else wanted the room.",
                "Height is what a push button needs for its content: 24 px.",
            ),
        ),
        (
            Outlined("Hug", False, "Fixed"),
            Hug(),
            {"width": 30, "hint_w": 80, "min_hint_w": 12},
            (
                "30 %s 40 px." % _TIMES,
                "Width is squeezed below the 80 px it asks for, because the window is too narrow. "
                "It can't go below 12 px.",
                "Height is what a push button needs for its content: 24 px.",
            ),
        ),
        (
            Outlined("Hug", True, "Preferred"),
            Hug(),
            {"width": 50, "hint_w": 50, "min_hint_w": 20, "min_w": 50},
            (
                "50 %s 40 px." % _TIMES,
                "Width can't go below its minimum of 50 px.",
                "Height is what a push button needs for its content: 24 px.",
            ),
        ),
    ],
)
def test_why_sentence_uses_the_live_number(horizontal, vertical, live, expected) -> None:
    assert _texts(_panel(horizontal, vertical), _live(**live)) == expected


def test_form_label_and_canvas_floor_follow_the_axis_sentences() -> None:
    panel = _panel(Hug(), Hug())
    live = _live(form_label_width=96, canvas_floor=True, hint_w=11, hint_h=22)
    assert _texts(panel, live) == (
        "180 %s 40 px." % _TIMES,
        "Width is what a push button needs for its content: 11 px.",
        "Height is what a push button needs for its content: 22 px.",
        "Labels are as wide as the longest label, 96 px.",
        "The canvas shows empty layouts bigger so you can drop into them; that size isn't saved.",
    )


def test_qt_policy_text_stays_out_of_the_paragraph() -> None:
    panel = _panel(Hug(), Fill())
    live = _live(policy_h="Fixed", policy_v="Expanding")
    paragraph = " ".join(_texts(panel, live))
    aside = qt_policy_text(live)
    assert aside == "(Fixed %s Expanding)" % _TIMES
    assert aside not in paragraph


def test_outlined_fill_and_soft_hug_follow_the_class_default() -> None:
    expanding = open_log(_column("okButton"))
    panel = project((_facts(expanding.document, "okButton", "Expanding", "Maximum"),))
    assert isinstance(panel.horizontal.mode, Outlined)
    assert panel.horizontal.mode.word == "Fill"
    assert panel.horizontal.mode.soft is False
    assert isinstance(panel.vertical.mode, Outlined)
    assert panel.vertical.mode.word == "Hug"
    assert panel.vertical.mode.soft is True
    assert chip_words(panel) == ("Fill", "Hug")
    unknown = project((_facts(expanding.document, "okButton", "", "Preferred"),))
    assert unknown.horizontal.mode == Outlined("Hug", False, "Preferred")
