# pyright: reportAttributeAccessIssue=false, reportOptionalMemberAccess=false
"""Form designer keys, the F1 card, the Buddy drop-down, the Tab order list and the Designer key map (M5.6).

UX-MODE-005 .. 007 and the test table of UX-MODE-006 (R3 199 .. 221).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.features.form_builder.engine.query import tab_stops as q  # noqa: E402
from app.features.form_builder.engine.shell_commands import FORM_COMMANDS, INERT_SHORTCUTS  # noqa: E402
from app.features.form_builder.integration import form_menu_ext, keys_ext  # noqa: E402
from app.features.form_builder.integration.widget_help import keys_groups, show_keys_page  # noqa: E402
from app.features.form_builder.qtside.keys_page.model import DESIGNER_GROUP, DESIGNER_MOVES, filter_groups  # noqa: E402
from app.qt.QtCore import Qt  # noqa: E402
from app.qt.QtGui import QKeySequence  # noqa: E402
from app.qt.QtTest import QTest  # noqa: E402
from app.qt.QtWidgets import QApplication, QComboBox, QLabel, QListWidget, QWidget  # noqa: E402
from app.shell.shortcut_preferences import SHORTCUT_COMMANDS  # noqa: E402
from tests.form_builder.qtside.test_m3_keyboard_scripts import Kb, _close, _session, _walk_to  # noqa: E402
from tests.form_builder.qtside.test_m5_6_keyboard_k23 import K23_FORM  # noqa: E402

pytestmark = [pytest.mark.unit, pytest.mark.timeout(300)]


def _rows(window: Any) -> Dict[str, Any]:
    return {row.command_id: row for group in keys_groups(window) for row in group.rows if row.bound}


@pytest.mark.parity("R3-210")
def test_the_keys_page_lists_every_registered_form_command_with_the_key_it_is_bound_to(
    tmp_path: Path, qapp: QApplication
) -> None:
    window, kb, guard = _session(tmp_path, qapp, K23_FORM)
    try:
        effective = dict(window._effective_shortcuts)
        rows = _rows(window)
        commands = {c.command_id: c for c in FORM_COMMANDS + keys_ext.extra_commands() if c.shortcut}
        missing = sorted(set(commands) - set(rows))
        assert not missing, "registered form commands missing from the page: %s" % missing
        unbound = sorted(
            command_id
            for command_id, row in rows.items()
            if row.keys != (effective.get(command_id) or effective.get(commands[command_id].shell_action_id or "-") or commands[command_id].shortcut)
        )
        assert not unbound, "the page lists keys that are not the bound ones: %s" % unbound
        # Settings > Keyboard rebinds a key: the page shows it the next time it is shown.
        window._effective_shortcuts = {**effective, "form.action.wrap": "Ctrl+Alt+K"}
        assert _rows(window)["form.action.wrap"].keys == "Ctrl+Alt+K"
        window._effective_shortcuts = effective
    finally:
        _close(window, qapp, guard)


def test_the_keys_page_opens_with_the_filter_focused_and_wrap_finds_the_wrap_key(tmp_path: Path, qapp: QApplication) -> None:
    window, kb, guard = _session(tmp_path, qapp, K23_FORM)
    try:
        dialog = show_keys_page(kb.surface)
        kb.pump()
        page = dialog.findChild(QWidget, "formBuilder.keysPage")
        assert page.filter.placeholderText() == "Search keys"
        assert page.filter.hasFocus()
        assert [page.table.headerItem().text(i) for i in range(4)] == ["Keys", "What it does", "Where", "In Qt Designer"]
        QTest.keyClicks(page.filter, "wrap")
        assert page.first_row_keys() == "Ctrl+Shift+G"
        page.filter.clear()
        # An inert key and a Designer key that moved are listed, with the words for them.
        titles = [group.title for group in filter_groups(keys_groups(window), "")]
        assert titles[0] == "File and history" and titles[-1] == DESIGNER_GROUP
        assert len(DESIGNER_MOVES) == 20
        assert all(key in " ".join(row.keys for group in keys_groups(window) for row in group.rows) for key in INERT_SHORTCUTS)
        dialog.close()
    finally:
        _close(window, qapp, guard)


def _shell_key(action_id: str) -> str:
    return next(command.default_shortcut for command in SHORTCUT_COMMANDS if command.action_id == action_id)


def _form_key(command_id: str) -> str:
    return next(command.shortcut for command in FORM_COMMANDS + keys_ext.extra_commands() if command.command_id == command_id)


def _form_menu(path: tuple) -> bool:
    from app.features.form_builder.engine.shell_commands import menu_commands

    in_table = any(command.menu_path == path for command in menu_commands())
    registry = form_menu_ext.default_registry()
    in_items = any(item.path == path for _module, item in registry.items(form_menu_ext.FORM))
    return in_table or in_items


def _check_new_form(window: Any) -> None:
    from app.features.form_builder.integration.surface import _shell_registry

    assert _shell_registry(window).action("shell.action.file.newForm") is not None
    assert _shell_key("shell.action.file.newProject") == "Ctrl+N"


def _check_open() -> None:
    assert _shell_key("shell.action.file.quickOpen") == "Ctrl+P"


def _check_same_keys(*pairs: tuple) -> None:
    for command_id, key in pairs:
        assert _form_key(command_id) == key, command_id


def _check_help_item() -> None:
    items = form_menu_ext.default_registry().items(form_menu_ext.HELP)
    assert [item.path for _module, item in items] == [("Form designer keys",)]


def _check_status_f4(kb: Kb) -> None:
    kb.surface.workbench.canvas.setFocus()
    kb.press("Key_F4")
    assert "Connections are in the Behavior tab. Alt+4 goes there." in kb.surface.editor_status_sentence()


def _check_f3(kb: Kb) -> None:
    kb.surface.workbench.canvas.setFocus()
    kb.press("Key_F8")
    assert kb.surface.modes.active == "tab_order"
    kb.press("Key_F3")
    assert kb.surface.modes.active == ""


def _check_enter_edits_f2_renames(kb: Kb) -> None:
    _check_same_keys(("form.action.editText", "Return"), ("form.action.rename", "F2"))


def _check_esc_selects_the_parent(kb: Kb) -> None:
    kb.surface.workbench.canvas.setFocus()
    _walk_to(kb, "nameEdit", limit=12)
    kb.press("Key_Escape")
    assert kb.current() == "formLayout"


def _check_arrows(kb: Kb) -> None:
    _check_same_keys(
        ("form.action.moveOrNudgeUp", "Alt+Up"),
        ("form.action.moveOrNudgeLeft", "Alt+Left"),
        ("form.action.nudgeOneUp", "Alt+Shift+Up"),
        ("form.action.selectUp", "Up"),
    )


_DESIGNER: Dict[int, Callable[[Any, Kb], None]] = {
    199: lambda window, kb: _check_new_form(window),
    200: lambda window, kb: _check_open(),
    201: lambda window, kb: _check_same_keys(("form.action.save", "Ctrl+S")),
    202: lambda window, kb: _check_same_keys(("form.action.saveAll", "Ctrl+Shift+S")),
    203: lambda window, kb: _check_same_keys(("form.action.closeTab", "Ctrl+W")),
    204: lambda window, kb: _shell_key("shell.action.file.exit") == "Ctrl+Q" or pytest.fail("Ctrl+Q quits"),
    205: lambda window, kb: _check_same_keys(("form.action.undo", "Ctrl+Z"), ("form.action.redo", "Ctrl+Shift+Z")),
    206: lambda window, kb: _check_same_keys(
        ("form.action.cut", "Ctrl+X"), ("form.action.copy", "Ctrl+C"), ("form.action.paste", "Ctrl+V"), ("form.action.delete", "Delete")
    ),
    207: lambda window, kb: _check_same_keys(("form.action.preview", "Ctrl+Shift+R"), ("form.action.goToWidget", "Ctrl+R")),
    208: lambda window, kb: [
        pytest.fail("Print has no key") for command in FORM_COMMANDS + keys_ext.extra_commands() if command.shortcut == "Ctrl+P"
    ]
    or _check_open(),
    209: lambda window, kb: _check_same_keys(("form.action.widgetHelp", "F1")),
    210: lambda window, kb: _check_help_item(),
    211: lambda window, kb: _check_f3(kb),
    212: lambda window, kb: _check_status_f4(kb),
    213: lambda window, kb: _check_enter_edits_f2_renames(kb),
    214: lambda window, kb: _check_same_keys(("form.action.find", "Ctrl+F")),
    215: lambda window, kb: _check_same_keys(
        ("form.action.layoutHorizontal", "Ctrl+1"),
        ("form.action.layoutVertical", "Ctrl+2"),
        ("form.action.layoutHorizontalSplitter", "Ctrl+3"),
        ("form.action.layoutVerticalSplitter", "Ctrl+4"),
        ("form.action.layoutGrid", "Ctrl+5"),
        ("form.action.layoutForm", "Ctrl+6"),
    ),
    216: lambda window, kb: (
        _check_same_keys(("form.action.unwrap", "Ctrl+Shift+B"), ("form.action.zoomReset", "Ctrl+0")),
        _form_menu(("Layout", "Remove layout…")) or pytest.fail("Remove layout is in the Layout menu"),
    ),
    217: lambda window, kb: _check_same_keys(("form.action.adjustSize", "Ctrl+J")),
    219: lambda window, kb: _check_arrows(kb),
    220: lambda window, kb: _check_esc_selects_the_parent(kb),
}


@pytest.mark.parametrize(
    "number",
    [
        pytest.param(199, marks=pytest.mark.parity("R3-199"), id="R3-199"),
        pytest.param(200, marks=pytest.mark.parity("R3-200"), id="R3-200"),
        pytest.param(201, marks=pytest.mark.parity("R3-201"), id="R3-201"),
        pytest.param(202, marks=pytest.mark.parity("R3-202"), id="R3-202"),
        pytest.param(203, marks=pytest.mark.parity("R3-203"), id="R3-203"),
        pytest.param(204, marks=pytest.mark.parity("R3-204"), id="R3-204"),
        pytest.param(205, marks=pytest.mark.parity("R3-205"), id="R3-205"),
        pytest.param(206, marks=pytest.mark.parity("R3-206"), id="R3-206"),
        pytest.param(207, marks=pytest.mark.parity("R3-207"), id="R3-207"),
        pytest.param(208, marks=pytest.mark.parity("R3-208"), id="R3-208"),
        pytest.param(209, marks=pytest.mark.parity("R3-209"), id="R3-209"),
        pytest.param(210, marks=pytest.mark.parity("R3-210"), id="R3-210"),
        pytest.param(211, marks=pytest.mark.parity("R3-211"), id="R3-211"),
        pytest.param(212, marks=pytest.mark.parity("R3-212"), id="R3-212"),
        pytest.param(213, marks=pytest.mark.parity("R3-213"), id="R3-213"),
        pytest.param(214, marks=pytest.mark.parity("R3-214"), id="R3-214"),
        pytest.param(215, marks=pytest.mark.parity("R3-215"), id="R3-215"),
        pytest.param(216, marks=pytest.mark.parity("R3-216"), id="R3-216"),
        pytest.param(217, marks=pytest.mark.parity("R3-217"), id="R3-217"),
        pytest.param(219, marks=pytest.mark.parity("R3-219"), id="R3-219"),
        pytest.param(220, marks=pytest.mark.parity("R3-220"), id="R3-220"),
    ],
)
def test_designer_key_map(number: int, tmp_path: Path, qapp: QApplication) -> None:
    """UX-MODE-006: each Designer key does what the table says in Code Studio."""
    window, kb, guard = _session(tmp_path, qapp, K23_FORM)
    try:
        _DESIGNER[number](window, kb)
        listed = {rows.split(", ")[0] for rows, _was, _now in DESIGNER_MOVES}
        assert str(number) in listed or any(str(number) in rows.split(", ") for rows, _was, _now in DESIGNER_MOVES)
    finally:
        _close(window, qapp, guard)


@pytest.mark.parity("R3-209")
def test_f1_opens_a_help_card_for_the_selected_widget_and_the_keys_page_for_the_form(
    tmp_path: Path, qapp: QApplication
) -> None:
    window, kb, guard = _session(tmp_path, qapp, K23_FORM)
    try:
        canvas = kb.surface.workbench.canvas
        canvas.setFocus()
        kb.pump()
        _walk_to(kb, "nameEdit", limit=12)
        kb.press("Key_F1")
        card = kb.surface.findChild(QWidget, "formBuilder.widgetHelp")
        assert card is not None and card.isVisible() and card.width() == 320
        text = card.text()
        assert "Line edit" in text and "One line of text the user can type." in text
        assert "Qt class: QLineEdit" in text
        assert "You can set: " in text and "…" in text
        assert [button.text() for button in card.findChildren(__import__("app.qt.QtWidgets", fromlist=["QPushButton"]).QPushButton)] == [
            "All form designer keys"
        ]
        kb.press("Key_Escape")
        assert kb.surface.findChild(QWidget, "formBuilder.widgetHelp") is None or not kb.surface.findChild(QWidget, "formBuilder.widgetHelp").isVisible()
        assert kb.focus_in("formBuilder.canvas")
        # With only the form selected, F1 opens Form designer keys.
        for _ in range(6):
            if kb.current() == "Contact":
                break
            kb.press("Key_Escape")
        kb.press("Key_F1")
        dialog = window._form_keys_dialog
        assert dialog.isVisible()
        dialog.close()
    finally:
        _close(window, qapp, guard)


@pytest.mark.parity("R3-9")
def test_the_buddy_row_is_a_drop_down_of_the_form_fields_with_type_to_filter(tmp_path: Path, qapp: QApplication) -> None:
    window, kb, guard = _session(tmp_path, qapp, K23_FORM)
    try:
        canvas = kb.surface.workbench.canvas
        canvas.setFocus()
        kb.pump()
        _walk_to(kb, "phoneLabel", limit=12)
        kb.surface.workbench.inspector.flush()
        kb.pump()
        combo = kb.surface.findChild(QComboBox, "formBuilder.buddyPicker")
        assert combo is not None
        assert [combo.itemText(i) for i in range(combo.count())] == [
            "None",
            "nameEdit · Line edit",
            "emailEdit · Line edit",
            "phoneEdit · Line edit",
        ]
        combo.lineEdit().setText("mail")
        combo._owner.pick_typed()
        document = kb.session.document
        assert q.buddy_of(document, document.by_name("phoneLabel")[0]) == "emailEdit"
        assert kb.session.log.undo_label() == "Set buddy of Phone"
        combo.setCurrentIndex(0)
        combo._owner.pick_typed()
        assert q.buddy_of(document, document.by_name("phoneLabel")[0]) is None
    finally:
        _close(window, qapp, guard)


@pytest.mark.parity("R3-11")
def test_the_tab_order_list_reorders_by_key_and_by_drag_and_says_which_order_it_follows(
    tmp_path: Path, qapp: QApplication
) -> None:
    window, kb, guard = _session(tmp_path, qapp, K23_FORM)
    try:
        kb.surface.focus_tab_order_list()
        kb.pump()
        rows = kb.surface.findChild(QListWidget, "formBuilder.tabOrderRows")
        caption = kb.surface.findChild(QLabel, "formBuilder.tabOrderCaption")
        assert [rows.item(i).text() for i in range(rows.count())] == [
            "1 · nameEdit · Line edit",
            "2 · emailEdit · Line edit",
            "3 · phoneEdit · Line edit",
        ]
        assert caption.text() == "Follows reading order: top to bottom, left to right."
        assert not kb.surface.findChild(QWidget, "formBuilder.tabOrderReset").isVisible()
        rows.setCurrentRow(0)
        QTest.keyClick(rows, Qt.Key.Key_Down, Qt.KeyboardModifier.AltModifier)
        kb.pump()
        document = kb.session.document
        assert document.tabstops() == ("emailEdit", "nameEdit", "phoneEdit")
        assert caption.text() == "Custom order. New fields join it where they sit on the form."
        assert kb.session.log.undo_label() == "Change tab order"
        # Drag the last row to the top.
        rows.model().moveRow(rows.rootIndex(), 2, rows.rootIndex(), 0)
        kb.pump()
        assert document.tabstops() == ("phoneEdit", "emailEdit", "nameEdit")
        # Enter selects the widget on the canvas.
        rows.setCurrentRow(1)
        QTest.keyClick(rows, Qt.Key.Key_Return)
        assert kb.current() == "emailEdit"
        kb.surface.findChild(QWidget, "formBuilder.tabOrderReset").click()
        assert document.tabstops() is None
    finally:
        _close(window, qapp, guard)


@pytest.mark.parity("R3-11")
def test_a_form_with_no_inputs_says_so(tmp_path: Path, qapp: QApplication) -> None:
    only_labels = K23_FORM.replace('<widget class="QLineEdit" name="nameEdit"/>', '<widget class="QLabel" name="a"/>').replace(
        '<widget class="QLineEdit" name="emailEdit"/>', '<widget class="QLabel" name="b"/>'
    ).replace('<widget class="QLineEdit" name="phoneEdit"/>', '<widget class="QLabel" name="c"/>')
    window, kb, guard = _session(tmp_path, qapp, only_labels)
    try:
        kb.surface.focus_tab_order_list()
        kb.pump()
        empty = kb.surface.findChild(QLabel, "formBuilder.tabOrderEmpty")
        assert empty.isVisible() and empty.text() == "No fields to visit yet. Inputs join the order as you add them."
    finally:
        _close(window, qapp, guard)


def test_the_form_menu_has_the_overlay_items_in_order() -> None:
    registry = form_menu_ext.default_registry()
    overlay = [(item.rank, item.path[-1]) for _module, item in registry.items(form_menu_ext.FORM) if item.path[0] == "Overlays"]
    assert [name for _rank, name in sorted(overlay)] == ["Tab order", "Buddies", "Tab order list…"]
    assert QKeySequence(_form_key("form.action.tabOrder")).toString() == "F8"
