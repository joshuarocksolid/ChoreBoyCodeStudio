# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportOptionalMemberAccess=false
"""K31, K32, K33 and K34 back to back on one main window. Keys only."""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.qt.QtTest import QTest  # noqa: E402
from app.qt.QtWidgets import (  # noqa: E402
    QApplication,
    QComboBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QMenu,
    QSpinBox,
    QWidget,
)
from app.shell.main_window import MainWindow  # noqa: E402
from tests.form_builder.qtside.test_m3_keyboard_scripts import (  # noqa: E402
    Kb,
    _NoMouse,
    _close,
    _key,
    _mods,
    _open,
    _project,
    _require,
)
from tests.form_builder.walk.test_m8_7_walk import (  # noqa: E402
    _alt,
    _button_text,
    _chord,
    _dialog,
    _focus_named,
    _focus_widget,
    _reject_modal,
)

pytestmark = [pytest.mark.unit, pytest.mark.timeout(300)]

_INVOICE = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Invoice</class>
 <widget class="QWidget" name="Invoice">
  <layout class="QFormLayout" name="formLayout">
   <item row="0" column="0">
    <widget class="QLabel" name="notesLabel">
     <property name="text"><string>Notes</string></property>
    </widget>
   </item>
   <item row="0" column="1">
    <widget class="QLineEdit" name="notesEdit"/>
   </item>
  </layout>
 </widget>
</ui>
"""

_TESTING = "Testing\u2026"
_INSERTS = ("id", "invoice_no", "invoice_date", "total")


class _Hand:
    """The walk helpers' keyboard stand-in. Shots stay off: CBCS_FB_WALK is unset."""

    def __init__(self, kb: Kb) -> None:
        self.kb = kb
        self.window = kb.window
        self.phase = "keys"
        self._focus_fallback = ""

    def confuse(self, text: str) -> None:
        self.kb.check(False, text)


def _on(window: MainWindow, qapp: QApplication, root: Path, name: str, text: str) -> Kb:
    path = root / "forms" / name
    surface = _open(window, qapp, path, text)
    kb = Kb(window, qapp, surface, path)
    surface.focus_primary()  # type: ignore[attr-defined]
    kb.pump()
    return kb


def _away(window: MainWindow, qapp: QApplication, path: Path) -> None:
    """Close that form and drop its widgets before the next script."""

    from app.qt.QtCore import QEvent

    window._editor_tab_workflow.close_tab_discarding_edits(str(path))  # noqa: SLF001
    types = getattr(QEvent, "Type", QEvent)
    kind = int(getattr(types, "DeferredDelete"))
    for _ in range(8):
        QApplication.sendPostedEvents(None, kind)
        qapp.processEvents()
    assert window.findChildren(QWidget, "formBuilder.events") == []


def _modal(
    kb: Kb,
    open_action: Callable[[], None],
    tick: Callable[[Dict[str, Any]], None],
    limit: int = 80,
    interval: int = 50,
) -> None:
    """Run ``tick`` while ``open_action`` holds a modal dialog open."""

    from app.qt.QtCore import QTimer

    state = {"n": 0, "stop": False, "error": None}  # type: Dict[str, Any]
    busy = {"on": False}

    def on_timeout() -> None:
        if busy["on"] or state["stop"]:
            return
        busy["on"] = True
        state["n"] = int(state["n"]) + 1
        try:
            if int(state["n"]) > limit:
                state["stop"] = True
                state["error"] = AssertionError(
                    "the dialog did not finish (phase %s)" % state.get("phase", "")
                )
                _reject_modal()
                return
            tick(state)
        except Exception as exc:  # noqa: BLE001 - close the dialog, then fail the script
            state["stop"] = True
            state["error"] = exc
            _reject_modal()
        finally:
            busy["on"] = False

    timer = QTimer(kb.window)
    timer.setInterval(interval)
    timer.timeout.connect(on_timeout)
    timer.start()
    try:
        open_action()
    finally:
        timer.stop()
        state["stop"] = True
    error = state["error"]
    if isinstance(error, BaseException):
        raise error


def _tab_named(kb: Kb, name: str, limit: int = 40) -> None:
    for _ in range(limit):
        if kb.focus_name() == name:
            return
        kb.press("Key_Tab")
    kb.check(kb.focus_name() == name, "Tab never reached %s (focus %s)" % (name, kb.focus_name()))


def _column_row(kb: Kb, name: str) -> Optional[QWidget]:
    panel = kb.window.findChild(QWidget, "formBuilder.dataPanel")
    if panel is None:
        return None
    for row in panel.findChildren(QWidget, "formBuilder.data.columnRow"):
        if str(row.property("column") or "") == name and row.isVisible():
            return row
    return None


def _enter_column(kb: Kb, hand: _Hand, name: str, shift: bool = False) -> None:
    """Ctrl+Shift+D, then Enter on that column row.

    Tab leaves the Data pane, and focusing a row that the insert then destroys
    drops focus onto the activity bar. The key is delivered to the row itself.
    """

    _focus_form(kb)
    _chord(hand, "Key_D", "Control", "Shift")
    kb.pump()
    row = _column_row(kb, name)
    listed = []
    panel = kb.window.findChild(QWidget, "formBuilder.dataPanel")
    if panel is not None:
        listed = [
            "%s:%s" % (item.property("column"), "shown" if item.isVisible() else "hidden")
            for item in panel.findChildren(QWidget, "formBuilder.data.columnRow")
        ]
    kb.check(row is not None, "the Data tab has no visible %s row (%s)" % (name, ", ".join(listed)))
    assert row is not None
    modifiers = ("Shift",) if shift else ()
    QTest.keyClick(row, _key("Key_Return"), _mods(*modifiers))
    kb.pump()
    kb.log.append(
        "%sKey_Return on %s -> focus=%s sel=%s"
        % ("Shift+" if shift else "", name, kb.focus_name(), kb.selected())
    )


def _select_named(kb: Kb, hand: _Hand, name: str) -> None:
    if kb.selected() == (name,):
        return
    _alt(hand, "Key_1")
    kb.press("Key_Home")
    kb.press("Key_Right")
    seen = []  # type: List[str]
    for _ in range(30):
        current = kb.selected()
        seen.append(",".join(current) or "(none)")
        if current == (name,):
            return
        kb.press("Key_Down")
    kb.check(False, "the outline never selected %s. It passed %s" % (name, ", ".join(seen)))


def _binds(kb: Kb) -> Dict[str, str]:
    from app.features.form_builder.engine.ui4.values import StringValue

    found = {}  # type: Dict[str, str]
    for node in kb.session.document.iter_widgets():  # type: ignore[attr-defined]
        entry = node.prop("cbcsBind")
        if entry is None or not isinstance(getattr(entry, "value", None), StringValue):
            continue
        column = str(entry.value.text or "")
        if column:
            found[column] = "%s:%s" % (node.object_name or "", node.class_name)
    return found


def _logic(kb: Kb, name: str, key: str) -> str:
    from app.features.form_builder.engine.ui4.values import StringValue

    document = kb.session.document  # type: ignore[attr-defined]
    ids = document.by_name(name)
    kb.check(len(ids) == 1, "%s is on the form (%s)" % (name, ids))
    entry = document.node(ids[0]).prop(key)
    if entry is None or not isinstance(getattr(entry, "value", None), StringValue):
        return ""
    return str(entry.value.text or "")


def _class_name(kb: Kb, name: str) -> str:
    document = kb.session.document  # type: ignore[attr-defined]
    ids = document.by_name(name)
    if len(ids) != 1:
        return ""
    return str(document.node(ids[0]).class_name)


def _replace_field(kb: Kb, hand: _Hand, dialog: object, name: str, text: str) -> None:
    _focus_named(hand, dialog, name)
    kb.press("Key_A", "Control")
    kb.type(text)


def _seed(root: Path) -> None:
    from app.features.form_builder.engine.data.connections import Connection, ConnectionSet
    from app.features.form_builder.engine.data.connections_module import save_project_connections
    from app.features.form_builder.engine.data.schema_cache import install_schema_reader, store_schema
    from app.features.form_builder.engine.data.schema_sqlite import read_sqlite_file
    from tests.form_builder.fixtures.m8.make_shop import build

    database = root / "data" / "shop.db"
    build(str(database))
    save_project_connections(
        str(root),
        ConnectionSet((Connection("shop", "Shop database", "sqlite", file="data/shop.db"),)),
        slug="shop",
    )
    store_schema(str(root), read_sqlite_file(str(database), "shop", read_at="2026-11-02T12:00:00"))
    install_schema_reader(str(root))


def _open_settings(kb: Kb) -> None:
    kb.press("Key_F", "Alt")
    menu = QApplication.activePopupWidget()
    kb.check(isinstance(menu, QMenu), "Alt+F opens File (focus %s)" % kb.focus_name())
    assert isinstance(menu, QMenu)
    for _ in range(24):
        active = menu.activeAction()
        if active is not None and active.text() == "Settings...":
            break
        kb.press("Key_Down")
    else:
        kb.check(False, "File has no Settings... row")
    kb.press("Key_Return")


def _fill_postgres(kb: Kb, hand: _Hand, dialog: QWidget) -> None:
    _replace_field(kb, hand, dialog, "formBuilder.connections.title", "Shop postgres")
    _replace_field(kb, hand, dialog, "formBuilder.connections.host", "127.0.0.1")
    _focus_named(hand, dialog, "formBuilder.connections.port")
    kb.press("Key_A", "Control")
    kb.type("5432")
    _replace_field(kb, hand, dialog, "formBuilder.connections.database", "cbcs")
    _replace_field(kb, hand, dialog, "formBuilder.connections.user", "cbcs")
    _replace_field(kb, hand, dialog, "formBuilder.connections.schema", "public")
    _focus_named(hand, dialog, "formBuilder.connections.password")
    password = dialog.findChild(QComboBox, "formBuilder.connections.password")
    kb.check(password is not None, "the password row is on the page")
    assert password is not None
    for _ in range(4):
        if str(password.currentData() or "") == "none":
            break
        kb.press("Key_Down")
    if str(password.currentData() or "") != "none":
        kb.press("Key_Return")
    host = dialog.findChild(QLineEdit, "formBuilder.connections.host")
    database = dialog.findChild(QLineEdit, "formBuilder.connections.database")
    user = dialog.findChild(QLineEdit, "formBuilder.connections.user")
    schema = dialog.findChild(QLineEdit, "formBuilder.connections.schema")
    port = dialog.findChild(QSpinBox, "formBuilder.connections.port")
    kb.check(host is not None and host.text() == "127.0.0.1", "host was filled")
    kb.check(database is not None and database.text() == "cbcs", "database was filled")
    kb.check(user is not None and user.text() == "cbcs", "user was filled")
    kb.check(schema is not None and schema.text() == "public", "schema was filled")
    kb.check(port is not None and port.value() == 5432, "port was filled")
    kb.check(str(password.currentData() or "") == "none", "password row is No password")


def _add_postgres(kb: Kb, dialog: QWidget) -> None:
    """Empty page uses + Add PostgreSQL. A page that already has a connection uses + Add."""

    empty = dialog.findChild(QWidget, "formBuilder.connections.addPostgres")
    if empty is not None and empty.isVisible():
        _tab_named(kb, "formBuilder.connections.addPostgres")
        kb.press("Key_Space")
        return
    _tab_named(kb, "formBuilder.connections.add")
    kb.press("Key_Space")
    menu = QApplication.activePopupWidget()
    if not isinstance(menu, QMenu):
        kb.press("Key_Down")
        menu = QApplication.activePopupWidget()
    kb.check(isinstance(menu, QMenu), "Add opens the connection menu (focus %s)" % kb.focus_name())
    assert isinstance(menu, QMenu)
    for _ in range(6):
        active = menu.activeAction()
        if active is not None and "PostgreSQL" in active.text():
            break
        kb.press("Key_Down")
    else:
        kb.check(False, "the Add menu has no PostgreSQL row")
    kb.press("Key_Return")


def _k31_tick(kb: Kb, hand: _Hand, state: Dict[str, Any], read: Dict[str, str]) -> None:
    dialog = _dialog("shell.settingsDialog")
    if not isinstance(dialog, QWidget):
        return
    phase = str(state.get("phase") or "nav")
    if phase == "nav":
        page = dialog.findChild(QWidget, "formBuilder.connections.page")
        if page is not None and page.isVisible():
            state["phase"] = "add"
            return
        focus = kb.focus()
        if focus is not None and type(focus).__name__ == "QTabBar":
            kb.press("Key_Right")
        else:
            kb.press("Key_Tab")
        return
    if phase == "add":
        _add_postgres(kb, dialog)
        state["phase"] = "fill"
        return
    if phase == "fill":
        _fill_postgres(kb, hand, dialog)
        state["phase"] = "test"
        return
    if phase == "test":
        _focus_named(hand, dialog, "formBuilder.connections.test")
        kb.press("Key_Space")
        state["phase"] = "read"
        return
    if phase == "read":
        label = dialog.findChild(QLabel, "formBuilder.connections.result")
        text = "" if label is None else str(label.text() or "")
        if not text or text == _TESTING:
            return
        read["result"] = text
        state["phase"] = "save"
        return
    if phase == "save":
        _focus_named(hand, dialog, "shell.settingsDialog.okBtn")
        kb.press("Key_Space")
        state["stop"] = True


def script_k31(kb: Kb) -> None:
    """Settings, Connections, Add PostgreSQL, fill the rows, Test, read the result."""

    hand = _Hand(kb)
    read = {}  # type: Dict[str, str]
    _modal(kb, lambda: _open_settings(kb), lambda state: _k31_tick(kb, hand, state, read), limit=220, interval=100)
    kb.check(bool(read.get("result")), "K31 read the Test result (%r)" % read.get("result", ""))
    kb.check(_TESTING not in read["result"], "K31 finished the Test (%r)" % read["result"])


def _connect_tick(kb: Kb, hand: _Hand, state: Dict[str, Any]) -> None:
    dialog = _dialog("formBuilder.data.connectSheet")
    if not isinstance(dialog, QWidget) or state.get("phase") == "done":
        return
    combo = dialog.findChild(QComboBox, "formBuilder.data.connection")
    if combo is not None and combo.currentData() != "shop":
        _focus_named(hand, dialog, "formBuilder.data.connection")
        for _ in range(8):
            if combo.currentData() == "shop":
                break
            kb.press("Key_Down")
        kb.check(combo.currentData() == "shop", "the connection is the shop database (%r)" % combo.currentText())
        return
    listed = dialog.findChild(QListWidget, "formBuilder.data.tables")
    if listed is None or listed.count() == 0:
        return
    _focus_named(hand, dialog, "formBuilder.data.tables")
    kb.press("Key_Home")
    landed = ""
    for _ in range(8):
        item = listed.currentItem()
        landed = "" if item is None else item.text()
        if landed == "invoices":
            break
        kb.press("Key_Down")
    kb.check(landed == "invoices", "the table list landed on invoices (%r)" % landed)
    _focus_named(hand, dialog, "formBuilder.data.connectOk")
    state["phase"] = "done"
    kb.press("Key_Space")


def _focus_form(kb: Kb) -> None:
    """Form shortcuts are live only while focus is inside the form tab."""

    surface = kb.surface
    for _ in range(40):
        focus = kb.focus()
        if isinstance(focus, QWidget) and (focus is surface or surface.isAncestorOf(focus)):
            return
        kb.press("Key_Tab")
    kb.check(False, "Tab never entered the form (focus %s)" % kb.focus_name())


def script_k32(kb: Kb) -> None:
    """Ctrl+Shift+D, connect to invoices, four Enters, Shift+Enter, Add record toolbar."""

    from app.features.form_builder.engine.data.schema_cache import install_schema_reader

    hand = _Hand(kb)
    install_schema_reader(str(kb.path.resolve().parents[1]))
    _focus_form(kb)
    _chord(hand, "Key_D", "Control", "Shift")
    _tab_named(kb, "formBuilder.data.connect")
    _modal(kb, lambda: kb.press("Key_Space"), lambda state: _connect_tick(kb, hand, state), limit=40)
    kb.check(kb.session.log.undo_label() == "Connect to invoices", "connect undo is Connect to invoices")  # type: ignore[attr-defined]
    _select_named(kb, hand, "notesEdit")
    for column in _INSERTS:
        _enter_column(kb, hand, column)
    if kb.selected() != ("notesEdit",):
        _select_named(kb, hand, "notesEdit")
    _enter_column(kb, hand, "notes", shift=True)
    bound = _binds(kb)
    for column in _INSERTS:
        kb.check(column in bound, "Enter inserted a field for %s (%s)" % (column, bound))
    kb.check(bound.get("notes", "").startswith("notesEdit:"), "Shift+Enter bound notes to the existing field (%s)" % bound)
    kb.check("customer_id" not in bound, "customer_id stays for K33 (%s)" % bound)
    _focus_named(hand, kb.window, "formBuilder.data.addToolbar")
    kb.press("Key_Space")
    kb.check(kb.session.log.undo_label() == "Add record toolbar", "the last step is Add record toolbar")  # type: ignore[attr-defined]
    kb.check(_class_name(kb, "saveButton") == "QPushButton", "the record toolbar has Save")


def _show_is_name(kb: Kb, hand: _Hand) -> None:
    _alt(hand, "Key_D")
    show = kb.window.findChild(QComboBox, "formBuilder.inspectorData.lookupShow")
    kb.check(show is not None and show.isVisible(), "Enter on customer_id opened Show")
    assert show is not None
    if str(show.currentData() or show.currentText()) == "name":
        return
    _focus_named(hand, show.window(), "formBuilder.inspectorData.lookupShow")
    for _ in range(8):
        if str(show.currentData() or show.currentText()) == "name":
            return
        kb.press("Key_Down")
    kb.check(str(show.currentData() or "") == "name", "Show is name (%r)" % show.currentText())


def _land(kb: Kb, hand: _Hand, widget: QWidget) -> None:
    for _ in range(24):
        if kb.focus() is widget:
            return
        kb.press("Key_Tab")
    _focus_widget(hand, widget)


def _lines_tick(kb: Kb, hand: _Hand, state: Dict[str, Any]) -> None:
    dialog = _dialog("formBuilder.data.linesSheet")
    if not isinstance(dialog, QWidget) or state.get("phase") == "done":
        return
    edits = [item for item in dialog.findChildren(QLineEdit) if item.isVisible() and item.placeholderText()]
    named = {item.placeholderText(): item for item in edits}
    kb.check("Name" in named and "Header" in named and "Formula" in named, "the lines sheet has the calculated-column boxes")
    _land(kb, hand, named["Name"])
    kb.type("line_total")
    kb.press("Key_Tab")
    kb.type("Line total")
    kb.press("Key_Tab")
    kb.type("qty * price")
    calc = dialog.findChild(QWidget, "formBuilder.data.linesCalc")
    kb.check(isinstance(calc, QWidget), "the lines sheet has Calculated column")
    assert isinstance(calc, QWidget)
    _land(kb, hand, calc)
    kb.press("Key_Space")
    accept = _button_text(dialog, "Add lines")
    kb.check(isinstance(accept, QWidget), "the lines sheet has Add lines")
    assert isinstance(accept, QWidget)
    _land(kb, hand, accept)
    state["phase"] = "done"
    kb.press("Key_Space")


def script_k33(kb: Kb) -> None:
    """Enter on customer_id makes a lookup and fixes Show. Then Add lines with a calculated column."""

    hand = _Hand(kb)
    _enter_column(kb, hand, "customer_id")
    kb.check(kb.session.log.undo_label() == "Add lookup", "Enter on customer_id is Add lookup")  # type: ignore[attr-defined]
    bound = _binds(kb)
    field = bound.get("customer_id", "")
    kb.check(field.endswith(":QComboBox"), "customer_id is a lookup combo (%s)" % field)
    name = field.split(":", 1)[0]
    kb.check("customers" in _logic(kb, name, "cbcsLookup"), "the lookup fills from customers")
    _show_is_name(kb, hand)
    show = kb.window.findChild(QComboBox, "formBuilder.inspectorData.lookupShow")
    assert show is not None
    kb.check(str(show.currentData() or show.currentText()) == "name", "Show is name")
    _focus_named(hand, kb.window, "formBuilder.data.linesAdd")
    _modal(kb, lambda: kb.press("Key_Space"), lambda state: _lines_tick(kb, hand, state), limit=40)
    text = kb.text()
    kb.check("line_total" in text and "qty * price" in text, "Add lines stored the calculated column")
    kb.check(kb.session.log.undo_label() == "Add lines", "the lines step is Add lines")  # type: ignore[attr-defined]


def _pump_until(qapp: QApplication, predicate: Callable[[], bool], seconds: float = 25.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        qapp.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return False


def _arm_preview() -> None:
    from app.features.form_builder.engine.ipc.timing import DirectorConfig
    from app.features.form_builder.qtside.preview.launch import (
        current_runtime_python,
        python_preview_command,
        repo_root,
    )
    from app.features.form_builder.qtside.preview.pool import PreviewPool

    PreviewPool.reset_shared()
    pool = PreviewPool(
        command=python_preview_command(current_runtime_python(), repo_root()),
        config=DirectorConfig(
            handshake_timeout=20.0,
            request_timeout=20.0,
            shutdown_grace=0.4,
            ping_interval=30.0,
            prewarm=True,
        ),
        root=repo_root(),
    )
    PreviewPool._shared = pool  # noqa: SLF001


def _preview_shell() -> Optional[QWidget]:
    shell = _dialog("formBuilder.previewShell")
    if isinstance(shell, QWidget):
        return shell
    for widget in QApplication.topLevelWidgets():
        if not widget.isVisible():
            continue
        found = widget.findChild(QWidget, "preview.form")
        if isinstance(found, QWidget):
            return found.window()
    return None


def _page_try(kb: Kb, hand: _Hand, shell: QWidget) -> None:
    """PgDown twice, change a field, Ctrl+S. Only when Try's window is in this process."""

    host = shell.findChild(QWidget, "preview.form")
    if host is None:
        host = shell
    _focus_named(hand, host, "preview.form")
    kb.press("Key_PageDown")
    kb.press("Key_PageDown")
    editor = None
    for kind in (QLineEdit,):
        for widget in host.findChildren(kind):
            if widget.isVisible() and widget.isEnabled() and not widget.objectName().startswith("preview."):
                editor = widget
                break
        if editor is not None:
            break
    kb.check(editor is not None, "Try's form has a field to change")
    assert editor is not None
    for _ in range(24):
        if kb.focus() is editor:
            break
        kb.press("Key_Tab")
    kb.check(kb.focus() is editor, "Tab reached a field in Try")
    kb.press("Key_A", "Control")
    kb.type("k34")
    kb.press("Key_S", "Control")


def script_k34(kb: Kb) -> None:
    """Ctrl+Shift+R, PgDown twice, change a field, Ctrl+S, read What ran and the banner."""

    from app.features.form_builder.qtside.preview.pool import PreviewPool

    hand = _Hand(kb)
    surface = kb.surface
    _arm_preview()
    notices = getattr(surface, "own_class_preview", None)
    kb.check(notices is not None, "the form tab has a preview")
    logs = []  # type: List[str]

    def hear(message: object) -> None:
        if getattr(message, "stream", "") == "try":
            text = str(getattr(message, "text", "") or "")
            if text:
                logs.append(text)

    PreviewPool.shared().subscribe(None, hear)
    _chord(hand, "Key_R", "Control", "Shift")
    kb.check(
        _pump_until(kb.qapp, lambda: getattr(notices, "last_response", None) is not None, 30.0),
        "Try answered. stderr: %s" % " | ".join(PreviewPool.shared().stderr_tail()[-6:]),
    )
    response = notices.last_response
    kb.check(bool(getattr(response, "ok", False)), "Try opened: %s" % getattr(response, "detail", ""))
    for _ in range(8):
        kb.pump()
    shell = _preview_shell()
    if shell is not None:
        _page_try(kb, hand, shell)
        for _ in range(8):
            kb.pump()
    result = getattr(response, "result", None)
    texts = result.get("texts", {}) if isinstance(result, dict) else {}
    banner = ""
    ran = ""
    if shell is not None:
        banner_label = shell.findChild(QLabel, "preview.banner")
        strip_label = shell.findChild(QLabel, "preview.dataStrip.label")
        banner = "" if banner_label is None else str(banner_label.text() or "")
        if not banner and strip_label is not None:
            banner = str(strip_label.text() or "")
        ran_widget = shell.findChild(QWidget, "preview.whatRan")
        if ran_widget is not None:
            ran = " ".join(part for part in _blob_lines(ran_widget) if part)
    if not banner:
        banner = str(texts.get("preview.banner") or texts.get("preview.dataStrip.label") or "")
    if not ran:
        ran = " ".join(logs)
    kb.check(bool(banner.strip()), "K34 read the banner (%r)" % banner)
    kb.check(bool(ran.strip()), "K34 read What ran (%r)" % ran[:240])


def _blob_lines(root: QWidget) -> List[str]:
    lines = []
    title = root.findChild(QLabel, "preview.whatRan.title")
    if title is not None and title.text():
        lines.append(str(title.text()))
    tree = root.findChild(QWidget, "preview.whatRan.list")
    count = getattr(tree, "topLevelItemCount", None)
    item_at = getattr(tree, "topLevelItem", None)
    if callable(count) and callable(item_at):
        for index in range(int(count())):
            item = item_at(index)
            if item is not None:
                lines.append(str(item.text(1)))
    return lines


def test_k31_k32_k33_k34_together(tmp_path: Path, qapp: QApplication) -> None:
    _require()
    if sys.platform == "darwin":
        from app.qt.QtGui import qt_set_sequence_auto_mnemonic

        qt_set_sequence_auto_mnemonic(True)
    root = tmp_path / "shop"
    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    _project(window, root)
    _seed(root)
    guard = _NoMouse()
    qapp.installEventFilter(guard)
    try:
        invoice = _on(window, qapp, root, "invoice.ui", _INVOICE)
        script_k31(invoice)
        script_k32(invoice)
        script_k33(invoice)
        script_k34(invoice)
        assert guard.seen == []
        _away(window, qapp, invoice.path)
    finally:
        from app.features.form_builder.qtside.preview.pool import PreviewPool

        PreviewPool.reset_shared()
        _close(window, qapp, guard)
        if sys.platform == "darwin":
            from app.qt.QtGui import qt_set_sequence_auto_mnemonic

            qt_set_sequence_auto_mnemonic(False)
