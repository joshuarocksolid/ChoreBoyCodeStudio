# pyright: reportAttributeAccessIssue=false
"""Menus, toolbars, status bar, actions and groups: commands and uic parity (M5.1, UX-MAIN-*)."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType

import pytest

from app.features.form_builder.engine.commands.catalog_ext.actions import (
    DeleteActions,
    GroupActions,
    MakeButtonGroup,
    NewAction,
    SetActionGroup,
    SetWidgetAction,
    UngroupActions,
    UngroupButtons,
)
from app.features.form_builder.engine.commands.base import CommandRejected
from app.features.form_builder.engine.commands.catalog import SetProperty
from app.features.form_builder.engine.commands.catalog_ext.main_window import (
    AddEntry,
    AddMainWindowPart,
    AddMenu,
    AddSeparator,
    MoveEntry,
    RemoveEntry,
    RemoveMainWindowPart,
    RenameEntry,
)
from app.features.form_builder.engine.project.templates import build_template_ui
from app.features.form_builder.engine.query import actions as q
from app.features.form_builder.engine.ui4.values import BoolValue
from app.features.form_builder.engine.ui4.writer import write_ui
from tests.form_builder.engine.commands._support import open_log

pytestmark = pytest.mark.unit

_HERE = Path(__file__).resolve().parent
_BAR = (
    '<?xml version="1.0" encoding="UTF-8"?>\n<ui version="4.0">\n <class>shop_window</class>\n'
    ' <widget class="QMainWindow" name="shop_window">\n'
    '  <widget class="QWidget" name="centralwidget">\n'
    '   <layout class="QVBoxLayout" name="verticalLayout">\n'
    "    <item>\n"
    '     <widget class="QRadioButton" name="a"/>\n'
    "    </item>\n"
    "    <item>\n"
    '     <widget class="QRadioButton" name="b"/>\n'
    "    </item>\n"
    "   </layout>\n"
    "  </widget>\n"
    ' </widget>\n <resources/>\n <connections/>\n</ui>\n'
)


def _log():  # type: ignore[no-untyped-def]
    log = open_log(_BAR)
    return log, log.document


def _build_shop(log):  # type: ignore[no-untyped-def]
    """The K16 walk, by commands."""
    doc = log.document
    root = doc.root.id
    bar = log.execute(AddMainWindowPart("menubar")).result
    status = log.execute(AddMainWindowPart("statusbar")).result
    file_menu = log.execute(AddMenu(bar, 0, "&File")).result
    log.execute(AddEntry(file_menu, 0, "New sale"))
    log.execute(AddEntry(file_menu, 1, "Print receipt"))
    log.execute(AddSeparator(file_menu, 2))
    log.execute(AddEntry(file_menu, 3, "Quit"))
    log.execute(AddMenu(bar, 1, "Help"))
    tool = log.execute(AddMainWindowPart("toolbar")).result
    log.execute(AddEntry(tool, 0, action="actionPrint_receipt"))
    del root, status
    return doc, bar, file_menu, tool


def test_a_main_window_part_is_refused_on_other_forms() -> None:
    log = open_log(
        '<?xml version="1.0" encoding="UTF-8"?>\n<ui version="4.0">\n <class>F</class>\n'
        ' <widget class="QWidget" name="F"/>\n <resources/>\n <connections/>\n</ui>\n'
    )
    with pytest.raises(CommandRejected, match="main window"):
        log.execute(AddMainWindowPart("toolbar"))


def test_typing_a_menu_and_entries_names_objects_as_designer_does() -> None:
    log, _ = _log()
    doc, bar, file_menu, tool = _build_shop(log)
    assert doc.node(file_menu).field("object_name") == "menuFile"
    assert [e.kind for e in q.entries(doc, file_menu)] == ["action", "action", "separator", "action"]
    assert [e.name for e in q.entries(doc, file_menu)][:2] == ["actionNew_sale", "actionPrint_receipt"]
    assert [e.name for e in q.entries(doc, bar)] == ["menuFile", "menuHelp"]
    info = {item.name: item for item in q.list_actions(doc)}
    assert info["actionPrint_receipt"].used_line == "File menu, toolBar"
    assert [e.name for e in q.entries(doc, tool)] == ["actionPrint_receipt"]


def test_removing_an_entry_keeps_an_action_used_elsewhere_and_drops_a_lone_one() -> None:
    log, _ = _log()
    doc, bar, file_menu, tool = _build_shop(log)
    ref_on_tool = q.entries(doc, tool)[0].ref
    still = log.execute(RemoveEntry(ref_on_tool, "Print receipt")).result
    assert still == ("File menu",)
    assert "actionPrint_receipt" in doc.names()
    quit_ref = q.entries(doc, file_menu)[-1].ref
    assert log.execute(RemoveEntry(quit_ref, "Quit")).result == ()
    assert "actionQuit" not in doc.names()
    log.undo()
    assert "actionQuit" in doc.names()


def test_removing_a_menu_removes_its_submenus_and_the_actions_left_unused() -> None:
    log, _ = _log()
    doc, bar, file_menu, tool = _build_shop(log)
    sub = log.execute(AddMenu(file_menu, 0, "Recent")).result
    log.execute(AddEntry(sub, 0, "Old sale"))
    menu_ref = q.entries(doc, bar)[0].ref
    log.execute(RemoveEntry(menu_ref, "File", "menu"))
    names = doc.names()
    assert "menuFile" not in names and "menuRecent" not in names and "actionOld_sale" not in names
    assert "actionPrint_receipt" in names  # still on the toolbar
    assert "actionNew_sale" not in names


def test_moving_an_entry_up_and_copying_it_to_a_toolbar() -> None:
    log, _ = _log()
    doc, bar, file_menu, tool = _build_shop(log)
    quit_ref = q.entries(doc, file_menu)[3].ref
    log.execute(MoveEntry(quit_ref, file_menu, 2, text="Quit"))
    assert [e.kind for e in q.entries(doc, file_menu)] == ["action", "action", "action", "separator"]
    log.execute(MoveEntry(quit_ref, tool, 1, copy=True, text="Quit"))
    assert [e.name for e in q.entries(doc, tool)] == ["actionPrint_receipt", "actionQuit"]
    with pytest.raises(CommandRejected):
        log.execute(MoveEntry(q.entries(doc, bar)[0].ref, file_menu, 0))  # a menu into itself


def test_renaming_a_menu_and_an_entry_writes_the_title_and_the_text() -> None:
    log, _ = _log()
    doc, bar, file_menu, tool = _build_shop(log)
    log.execute(RenameEntry(q.entries(doc, bar)[0].ref, "&Files", "&File", "menu"))
    assert q.text_of(doc.node(file_menu), "title") == "&Files"
    assert q.plain_text("Save && close &As") == "Save & close As"


def test_a_widget_action_and_action_groups_round_trip_through_undo() -> None:
    log, _ = _log()
    doc, bar, file_menu, tool = _build_shop(log)
    a = log.execute(NewAction("Left")).result
    b = log.execute(NewAction("Right")).result
    group = log.execute(GroupActions((a, b))).result
    assert q.group_of(doc, doc.node(a)) == "actionGroup"
    log.execute(SetActionGroup(a, None))
    assert q.group_of(doc, doc.node(a)) is None
    log.execute(UngroupActions(group))
    assert not q.action_groups(doc)
    button = doc.by_name("a")[0]
    log.execute(SetWidgetAction(button, "actionLeft", True, "a"))
    assert [e.name for e in q.entries(doc, button)] == ["actionLeft"]
    log.execute(DeleteActions((a,), "Left"))
    assert "actionLeft" not in doc.names() and not q.entries(doc, button)


def test_button_groups_do_not_reorder_the_buttons() -> None:
    log, _ = _log()
    doc = log.document
    a, b = doc.by_name("a")[0], doc.by_name("b")[0]
    before = write_ui(doc).text
    name = log.execute(MakeButtonGroup((b, a))).result
    after = write_ui(doc).text
    assert after.index('name="a"') < after.index('name="b"') and name == "buttonGroup"
    assert [(n, len(m)) for n, _, m in q.button_groups(doc)] == [("buttonGroup", 2)]
    log.execute(UngroupButtons(name))
    assert write_ui(doc).text == before
    with pytest.raises(CommandRejected):
        log.execute(MakeButtonGroup((a, doc.root.id)))


def test_fb036_and_fb037_name_unused_actions_and_widgets_in_bars() -> None:
    log, _ = _log()
    doc, bar, file_menu, tool = _build_shop(log)
    log.execute(NewAction("Lonely"))
    codes = [(d.code, d.location.object_name) for d in q.main_window_diagnostics(doc)]
    assert codes == [("FB036", "actionLonely")]


def test_the_blank_main_window_template_has_menubar_central_and_status_bar() -> None:
    text = build_template_ui("main_window", "shop_window")
    log = open_log(text)
    kids = [c.object_name for c in log.document.root.child_widgets]
    assert kids == ["menubar", "centralwidget", "statusbar"]


# ---------------------------------------------------------------- uic parity

def _load_helper(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def uic_env(monkeypatch):  # type: ignore[no-untyped-def]
    uic = os.environ.get("CBCS_FB_UIC", "") or "/Applications/FreeCAD.app/Contents/Resources/lib/qt6/uic"
    if not Path(uic).is_file():
        pytest.skip("CBCS_FB_UIC is not set")
    monkeypatch.setenv("CBCS_FB_UIC", uic)


@pytest.mark.parity("R3-113")
@pytest.mark.parity("R3-114")
@pytest.mark.parity("R3-115")
@pytest.mark.parity("R3-137")
def test_the_k16_window_matches_uic(tmp_path: Path, qapp, uic_env) -> None:  # type: ignore[no-untyped-def]
    del qapp, uic_env
    uic = _load_helper("cbcs_uic_compare_m51", _HERE.parents[1] / "engine" / "codegen" / "uic_compare.py")
    log, _ = _log()
    doc, bar, file_menu, tool = _build_shop(log)
    sub = log.execute(AddMenu(file_menu, 0, "Recent files")).result
    log.execute(AddEntry(sub, 0, "Old sale"))
    log.execute(SetProperty(q.entries(doc, file_menu)[1].target, "shortcut", __import__(
        "app.features.form_builder.engine.ui4.values", fromlist=["StringValue"]).StringValue("Ctrl+N")))
    a = log.execute(NewAction("Left")).result
    b = log.execute(NewAction("Right")).result
    log.execute(GroupActions((a, b)))
    log.execute(AddEntry(tool, 1, action="actionLeft"))
    log.execute(AddEntry(tool, 2, action="actionRight"))
    log.execute(SetProperty(doc.by_name("actionLeft")[0], "checkable", BoolValue(True)))
    log.execute(SetProperty(doc.by_name("actionRight")[0], "checkable", BoolValue(True)))
    log.execute(MakeButtonGroup((doc.by_name("a")[0], doc.by_name("b")[0])))
    path = tmp_path / "shop.ui"
    path.write_text(write_ui(doc).text, encoding="utf-8")
    result = uic.compare(path)
    assert result[0] == "ok", result
