# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
"""Form settings commands (UX-FSET-002 ... 006): every field round-trips and writes one step."""

from __future__ import annotations

import pytest

from app.features.form_builder.engine.commands.base import CommandRejected
from app.features.form_builder.engine.commands.catalog_ext.form_fields import (
    FormGrid,
    SetFormGrid,
    SetFormSetting,
    form_grid,
    has_free_container,
    include_lines,
)
from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.project.templates import build_template_ui
from app.features.form_builder.engine.ui4.reader import read_ui
from app.features.form_builder.engine.ui4.schema import LayoutDefault, LayoutFunction
from app.features.form_builder.engine.ui4.writer import write_ui
from tests.form_builder.engine.commands._support import open_log, saved
from tests.form_builder.inspector.m5_5b_support import LAID_OUT, free_form

pytestmark = pytest.mark.unit

#: Every form setting the Code and Translation groups show, written the way Qt Designer writes them.
FULL = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0" language="C++" displayname="Till" idbasedtr="true" stdsetdef="1">
 <author>Pat</author>
 <comment>Kept as written</comment>
 <exportmacro>SHOP_EXPORT</exportmacro>
 <class>Till</class>
 <widget class="QWidget" name="Till"/>
 <layoutdefault spacing="6" margin="11"/>
 <layoutfunction spacing="spacing_for" margin="margin_for"/>
 <pixmapfunction>load_picture</pixmapfunction>
 <includes>
  <include location="local" impldecl="in-implementation">shop.h</include>
  <include location="global">vector</include>
 </includes>
 <resources/>
 <connections/>
 <designerdata>
  <property name="gridDeltaX">
   <number>10</number>
  </property>
  <property name="gridDeltaY">
   <number>10</number>
  </property>
  <property name="gridSnapX">
   <bool>true</bool>
  </property>
  <property name="gridSnapY">
   <bool>true</bool>
  </property>
  <property name="gridVisible">
   <bool>false</bool>
  </property>
 </designerdata>
</ui>
"""


@pytest.mark.parity("R3-185")
@pytest.mark.parity("R3-186")
@pytest.mark.parity("R3-187")
@pytest.mark.parity("R3-188")
@pytest.mark.parity("R3-189")
@pytest.mark.parity("R3-190")
@pytest.mark.parity("R3-191")
@pytest.mark.parity("R3-192")
@pytest.mark.parity("R3-193")
def test_every_form_field_round_trips_byte_for_byte_and_undo_restores_it() -> None:
    document = read_ui(FULL, allocator=IdAllocator()).document
    assert write_ui(document).text == FULL
    log = open_log(FULL)
    doc = log.document
    steps = [
        SetFormSetting("author", "Sam"),
        SetFormSetting("comment", "New"),
        SetFormSetting("exportmacro", "OTHER"),
        SetFormSetting("layoutdefault", LayoutDefault(8, 8)),
        SetFormSetting("layoutfunction", LayoutFunction("gap_of", None)),
        SetFormSetting("pixmapfunction", "pictures.load"),
        SetFormSetting("includes", (("global", "map"),)),
        SetFormSetting("idbasedtr", None),
        SetFormSetting("language", "Python"),
        SetFormSetting("displayname", "Till window"),
        SetFormSetting("stdsetdef", None),
        SetFormGrid("across", 16),
    ]
    for command in steps:
        log.execute(command)
        text = saved(doc)
        assert write_ui(read_ui(text, allocator=IdAllocator()).document).text == text
    for _ in steps:
        assert log.undo()
    assert saved(doc) == FULL


def test_the_new_form_templates_write_no_older_file_setting_or_grid() -> None:
    for kind in ("widget", "dialog", "main_window"):
        text = build_template_ui(kind, "shop_form")
        assert "stdsetdef" not in text.lower() and "designerdata" not in text, kind


def test_a_setting_equal_to_what_is_stored_adds_no_step() -> None:
    log = open_log(FULL)
    before = len(log.entries())
    log.execute(SetFormSetting("author", "Pat"))
    log.execute(SetFormSetting("exportmacro", "SHOP_EXPORT"))
    assert len(log.entries()) == before


def test_the_command_names_the_undo_step_for_the_row() -> None:
    log = open_log(LAID_OUT)
    log.execute(SetFormSetting("author", "Shop", "Change form setting: author"))
    assert log.undo_label() == "Change form setting: author"


@pytest.mark.parametrize("name", ["margin for", "2fast", "def", "a..b", "x(1)"])
def test_function_names_are_checked_as_python_names(name: str) -> None:
    log = open_log(LAID_OUT)
    with pytest.raises(CommandRejected, match="Use a function name like margin_for."):
        log.execute(SetFormSetting("pixmapfunction", name))
    with pytest.raises(CommandRejected, match="Use a function name like margin_for."):
        log.execute(SetFormSetting("layoutfunction", LayoutFunction(name, None)))
    assert saved(log.document) == LAID_OUT


def test_a_dotted_function_name_is_a_python_name() -> None:
    log = open_log(LAID_OUT)
    log.execute(SetFormSetting("layoutfunction", LayoutFunction("sizes.gap", "sizes.margin")))
    assert '<layoutfunction spacing="sizes.gap" margin="sizes.margin"/>' in saved(log.document)


def test_the_builder_never_writes_the_older_attributes() -> None:
    log = open_log(LAID_OUT)
    for field in ("stdsetdef", "stdSetDef"):
        with pytest.raises(CommandRejected):
            log.execute(SetFormSetting(field, "1"))
    with pytest.raises(CommandRejected):
        log.execute(SetFormSetting("version", "9"))
    assert saved(log.document) == LAID_OUT


def test_an_older_attribute_the_file_has_survives_every_other_edit() -> None:
    log = open_log(FULL)
    log.execute(SetFormSetting("author", "Sam"))
    log.execute(SetFormSetting("idbasedtr", None))
    assert 'stdsetdef="1"' in saved(log.document)


def test_both_older_spellings_can_be_removed() -> None:
    text = FULL.replace('stdsetdef="1"', 'stdsetdef="1" stdSetDef="0"')
    log = open_log(text)
    log.execute(SetFormSetting("stdsetdef", None))
    log.execute(SetFormSetting("stdSetDef", None))
    assert "stdsetdef" not in saved(log.document).lower()


@pytest.mark.parity("R3-189")
def test_include_lines_keep_the_bytes_of_lines_that_did_not_change() -> None:
    log = open_log(FULL)
    assert include_lines(log.document) == (("local", "shop.h"), ("global", "vector"))
    log.execute(SetFormSetting("includes", (("local", "shop.h"), ("global", "map"), ("local", "more.h"))))
    text = saved(log.document)
    assert '<include location="local" impldecl="in-implementation">shop.h</include>' in text
    assert '<include location="global">map</include>' in text and '<include location="local">more.h</include>' in text
    log.execute(SetFormSetting("includes", ()))
    assert "<includes>" not in saved(log.document)


def test_the_grid_defaults_are_shown_and_snapping_at_8_px() -> None:
    doc = open_log(free_form()).document
    assert form_grid(doc) == FormGrid(show=True, across=8, down=8, snap=True)
    assert has_free_container(doc)
    assert not has_free_container(open_log(LAID_OUT).document)


@pytest.mark.parity("R3-222")
def test_grid_values_are_written_only_when_they_differ_from_the_defaults() -> None:
    log = open_log(free_form())
    plain = saved(log.document)
    log.execute(SetFormGrid("across", 8))
    log.execute(SetFormGrid("show", True))
    log.execute(SetFormGrid("snap", True))
    assert saved(log.document) == plain and "designerdata" not in plain
    log.execute(SetFormGrid("across", 16))
    log.execute(SetFormGrid("down", 4))
    log.execute(SetFormGrid("show", False))
    log.execute(SetFormGrid("snap", False))
    text = saved(log.document)
    assert form_grid(read_ui(text, allocator=IdAllocator()).document) == FormGrid(False, 16, 4, False)
    for name in ("gridDeltaX", "gridDeltaY", "gridSnapX", "gridSnapY", "gridVisible"):
        assert 'name="%s"' % name in text
    # Back to the defaults: nothing is left in the file, as if the grid had never been touched.
    for part, value in (("across", 8), ("down", 8), ("show", True), ("snap", True)):
        log.execute(SetFormGrid(part, value))
    assert saved(log.document) == plain


def test_a_designer_grid_is_read_and_other_designer_data_stays() -> None:
    text = free_form(extra=(
        " <designerdata>\n"
        '  <property name="gridDeltaX">\n   <number>10</number>\n  </property>\n'
        '  <property name="somethingElse">\n   <number>3</number>\n  </property>\n'
        " </designerdata>\n"
    ))
    log = open_log(text)
    assert form_grid(log.document).across == 10 and form_grid(log.document).down == 8
    log.execute(SetFormGrid("across", 8))
    assert 'name="somethingElse"' in saved(log.document) and "gridDeltaX" not in saved(log.document)


@pytest.mark.parametrize("value", [1, 101, 0, -4, True, "8"])
def test_a_step_is_whole_pixels_from_2_to_100(value: object) -> None:
    log = open_log(free_form())
    with pytest.raises(CommandRejected):
        log.execute(SetFormGrid("across", value))
