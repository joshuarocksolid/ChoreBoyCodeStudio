# pyright: reportAttributeAccessIssue=false
"""K16: the main-window script, keys only, against the menu editor (UX-MAIN-004 ... 008)."""

from __future__ import annotations

import pytest

from app.features.form_builder.engine.commands.catalog_ext.main_window import AddMainWindowPart
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.project.templates import build_template_ui
from app.features.form_builder.engine.query import actions as q
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.writer import write_ui
from app.features.form_builder.qtside.actions.editing import GRAMMAR, Key, MenuEditor
from app.features.form_builder.qtside.actions.env import SessionEnv

pytestmark = pytest.mark.unit


def _session():  # type: ignore[no-untyped-def]
    text = build_template_ui("main_window", "shop_window")
    return FormSession.open(text, path="/tmp/shop_window.ui", scope=FormScope(kind="external", ui_path="/tmp/shop_window.ui"))


def _keys(editor: MenuEditor, *items: str) -> None:
    for item in items:
        if len(item) == 1 and item.isprintable() and item != " " or item == " ":
            editor.handle(Key("", item))
            continue
        alt = item.startswith("Alt+")
        name = item[4:] if alt else item
        editor.handle(Key(name, "", alt=alt))


def _type(editor: MenuEditor, text: str) -> None:
    for char in text:
        editor.handle(Key("", char))


@pytest.mark.pain("P-17")
@pytest.mark.parity("R3-114", "R3-116", "R3-117", "R3-136", "R3-137")
def test_k16_menu_editing_by_keys_only() -> None:
    session = _session()
    initial = write_ui(session.document).text
    said = []
    toasts = []
    env = SessionEnv(session, said.append, toasts.append)
    editor = MenuEditor(env)
    doc = session.document
    bar = doc.by_name("menubar")[0]
    assert editor.start(bar) and said[-1] == GRAMMAR
    _type(editor, "&File")
    _keys(editor, "Enter")
    assert "menuFile" in doc.names()
    _keys(editor, "Down")  # File opens with focus on its Type here
    assert len(editor.levels) == 2 and editor.levels[-1].slot == 0
    _type(editor, "New sale")
    _keys(editor, "Enter")
    _type(editor, "Print receipt")
    _keys(editor, "Enter")
    menu = doc.by_name("menuFile")[0]
    assert editor.levels[-1].slot == 2  # Type here again after each entry
    _keys(editor, "Down", "Enter")  # Add separator
    kinds = [e.kind for e in q.entries(doc, menu)]
    assert kinds == ["action", "action", "separator"]
    assert editor.levels[-1].slot == 4  # focus stays on "Add separator"
    _keys(editor, "Up")
    _type(editor, "Quit")
    _keys(editor, "Enter")
    _keys(editor, "Up")  # on Quit
    _keys(editor, "Alt+Up")
    assert [e.name for e in q.entries(doc, menu)] == [
        "actionNew_sale", "actionPrint_receipt", "actionQuit", "separator"
    ]
    _keys(editor, "Alt+Down")
    assert [e.kind for e in q.entries(doc, menu)] == ["action", "action", "separator", "action"]
    _keys(editor, "Escape")  # File closes, its title has focus
    assert len(editor.levels) == 1 and editor.levels[0].slot == 0
    _keys(editor, "Right")
    _type(editor, "Help")
    _keys(editor, "Enter")
    assert [e.name for e in q.entries(doc, bar)] == ["menuFile", "menuHelp"]
    _keys(editor, "Escape")
    assert not editor.active
    # A toolbar button reusing an existing action (pain 17).
    session.log.execute(AddMainWindowPart("toolbar"))
    tool = doc.by_name("toolBar")[0]
    editor.start(tool)
    _type(editor, "Pri")
    view = editor.view().levels[-1]
    assert view.reuse[0].label == "New action “Pri”" and view.reuse[1].label == "Print receipt"
    _keys(editor, "Down", "Enter")
    assert [e.name for e in q.entries(doc, tool)] == ["actionPrint_receipt"]
    info = {item.name: item for item in q.list_actions(doc)}
    assert info["actionPrint_receipt"].used_line == "File menu, toolBar"
    # Delete on the toolbar button keeps the action; the toast says where it still is.
    _keys(editor, "Left", "Delete")
    assert toasts and "from toolBar. It's still on the File menu." in toasts[-1] and "actionPrint_receipt" in doc.names()
    # One undo step per edit, each with its 13.2.10 name (UX-M5-008).
    assert [entry.label for entry in session.log.entries()] == [
        "Add menu File",
        "Add New sale to the File menu",
        "Add Print receipt to the File menu",
        "Add separator",
        "Add Quit to the File menu",
        "Move Quit",
        "Move Quit",
        "Add menu Help",
        "Add toolbar",
        "Add Print receipt to toolBar",
        "Remove Print receipt",
    ]
    # Undo all: back to the bytes the form had when it was created.
    while session.log.can_undo():
        session.log.undo()
    assert write_ui(session.document).text == initial


def test_a_typed_menu_text_that_matches_an_action_makes_that_row_current() -> None:
    session = _session()
    editor = MenuEditor(SessionEnv(session))
    doc = session.document
    editor.start(doc.by_name("menubar")[0])
    _type(editor, "File")
    _keys(editor, "Enter", "Down")
    _type(editor, "Save")
    _keys(editor, "Enter")
    _type(editor, "save")
    row = editor.view().levels[-1]
    assert row.reuse[row.reuse_current].kind == "action"


def test_the_first_entry_typed_into_an_empty_submenu_turns_the_entry_into_a_menu() -> None:
    session = _session()
    editor = MenuEditor(SessionEnv(session))
    doc = session.document
    editor.start(doc.by_name("menubar")[0])
    _type(editor, "File")
    _keys(editor, "Enter", "Down")
    _type(editor, "Recent")
    _keys(editor, "Enter", "Up", "Right")  # an unwritten submenu is open; nothing written yet
    assert len(editor.levels) == 3 and "menuRecent" not in doc.names()
    _type(editor, "Old sale")
    _keys(editor, "Enter")
    assert "menuRecent" in doc.names() and "actionRecent" not in doc.names()
    assert [e.name for e in q.entries(doc, doc.by_name("menuRecent")[0])] == ["actionOld_sale"]
    session.log.undo()
    assert "menuRecent" not in doc.names() and "actionRecent" in doc.names()
