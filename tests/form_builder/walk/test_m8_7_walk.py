# pyright: reportAttributeAccessIssue=false
"""M8.7 persona walks. Skipped unless CBCS_FB_WALK=1. Not a unit-lane test.

Keys only, on a real MainWindow, over a fresh shop project. Each step writes
a screenshot and a log line under docs/form_builder/orch/m87_walk/.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import pytest

pytestmark = [
    pytest.mark.skipif(
        os.environ.get("CBCS_FB_WALK") != "1",
        reason="persona walk; set CBCS_FB_WALK=1",
    ),
    pytest.mark.timeout(600),
]

_ROOT = Path(__file__).resolve().parents[3]
_OUT = _ROOT / "docs" / "form_builder" / "orch" / "m87_walk"
_OWNER_JARGON = (
    "cbcs",
    "self.",
    "QLineEdit",
    "QComboBox",
    "QSpinBox",
    "QDoubleSpinBox",
    "QTableView",
    "QDialog",
    "QPushButton",
    "QLabel",
    "cbcsOnBeforeSave",
    "search_path",
)


def test_shop_owner_walk(tmp_path: Path, qapp: object) -> None:
    walk = _boot(tmp_path, qapp, "owner", "light")
    try:
        _create_invoice(walk)
        _theme_shot(walk, "dark", "record")
        _fix_show(walk)
        _line_total(walk)
        _form_total(walk)
        _try_data(walk)
        _run_app(walk)
    finally:
        _finish(walk, qapp)


def test_qt_developer_walk(tmp_path: Path, qapp: object) -> None:
    walk = _boot(tmp_path, qapp, "developer", "light")
    try:
        _create_invoice(walk)
        _theme_shot(walk, "high_contrast_dark", "record")
        _before_save(walk)
        _show_sql(walk)
        _setup_function(walk)
        _eject(walk)
    finally:
        _finish(walk, qapp)


class _Walk:
    def __init__(self, window: object, kb: object, qapp: object, persona: str, root: Path) -> None:
        self.window = window
        self.kb = kb
        self.qapp = qapp
        self.persona = persona
        self.root = root
        self.phase = "open"
        self.n = 0
        self.counts = {}  # type: Dict[str, int]
        self.confusions = []  # type: List[str]
        self._jargon = set()  # type: set
        self.log_path = _OUT / ("%s_log.txt" % persona)
        _OUT.mkdir(parents=True, exist_ok=True)
        self.log_path.write_text("", encoding="utf-8")

    def step(self, slug: str, action: Callable[[], None]) -> None:
        self.n += 1
        self.counts[self.phase] = self.counts.get(self.phase, 0) + 1
        before = len(self.kb.log)
        action()
        self.kb.pump()
        keys = " | ".join(self.kb.log[before:]) or "(no key)"
        focus = _focus()
        acc = ""
        if focus is not None:
            acc = str(focus.accessibleName() or "")
        status = _status(self.window)
        body = _pane_text(self, "formBuilder.inspector")
        data = _pane_text(self, "formBuilder.dataPanel")
        if not data:
            data = _pane_text(self, "formBuilder.data")
        dialog = _dialogs(self.window)
        if self.persona == "owner":
            self._scan(_user_text(self) + "\n" + dialog + "\n" + data)
        line = (
            "STEP %02d %s phase=%s\n  keys: %s\n  focus: %s acc=%r\n  status: %s\n"
            "  inspector:\n%s\n  data:\n%s\n  dialogs:\n%s\n"
            % (
                self.n,
                slug,
                self.phase,
                keys,
                _focus_name(focus),
                acc,
                status,
                _indent(body),
                _indent(data),
                _indent(dialog),
            )
        )
        self._write(line)
        _shot(self.window, self.qapp, "%s-%02d-%s" % (self.persona, self.n, slug))

    def confuse(self, text: str) -> None:
        quote = " ".join(text.split())
        if not quote or quote in self.confusions:
            return
        self.confusions.append(quote)
        self._write("CONFUSION phase=%s %s\n" % (self.phase, quote))

    def note(self, text: str) -> None:
        self._write("NOTE phase=%s %s\n" % (self.phase, text))

    def _scan(self, blob: str) -> None:
        for word in _OWNER_JARGON:
            if word in self._jargon:
                continue
            for line in blob.splitlines():
                if "<" in line or word.casefold() not in line.casefold():
                    continue
                self._jargon.add(word)
                self.confuse("The screen says %r." % line.strip()[:180])
                break

    def _write(self, text: str) -> None:
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(text)
        print(text, flush=True)


def _boot(tmp_path: Path, qapp: object, persona: str, theme: str) -> _Walk:
    from app.core.models import LoadedProject, ProjectFileEntry, ProjectMetadata
    from app.features.form_builder.engine.data.connections import Connection, ConnectionSet
    from app.features.form_builder.engine.data.connections_module import save_project_connections
    from app.shell.main_window import MainWindow
    from tests.form_builder.fixtures.m8.make_shop import build
    from tests.form_builder.qtside.test_m3_keyboard_scripts import Kb, _NoMouse, _require

    _require()
    if sys.platform == "darwin":
        from app.qt.QtGui import qt_set_sequence_auto_mnemonic

        qt_set_sequence_auto_mnemonic(True)
    from app.bootstrap.paths import resolve_app_root

    root = tmp_path / "shop"
    (root / "forms").mkdir(parents=True)
    (root / "cbcs").mkdir()
    template_main = resolve_app_root() / "templates" / "qt_app" / "main.py"
    (root / "main.py").write_bytes(template_main.read_bytes())
    (root / "cbcs" / "project.json").write_text(
        '{"schema_version": 2, "name": "Shop", "default_entry": "main.py", "template": "qt_app"}\n',
        encoding="utf-8",
    )
    build(str(root / "data" / "shop.db"))
    save_project_connections(
        str(root),
        ConnectionSet(
            (
                Connection("shop", "Shop database", "sqlite", file="data/shop.db"),
                Connection(
                    "shop_pg",
                    "Shop postgres",
                    "postgres",
                    host="127.0.0.1",
                    port=5432,
                    database="cbcs",
                    user="cbcs",
                    password="none",
                    schema="public",
                ),
            )
        ),
        slug="shop",
    )
    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    entries = [
        ProjectFileEntry(str(item.relative_to(root)).replace("\\", "/"), str(item.resolve()), False)
        for item in root.rglob("*")
        if item.is_file()
    ]
    window._loaded_project = LoadedProject(  # noqa: SLF001
        project_root=str(root.resolve()),
        manifest_path=str((root / "cbcs" / "project.json").resolve()),
        metadata=ProjectMetadata(schema_version=2, name="Shop", default_entry="main.py"),
        entries=entries,
    )
    window.set_project_placeholder("Shop")
    stack = window._center_stack  # noqa: SLF001
    if stack is not None:
        stack.setCurrentIndex(1)
    window.resize(1400, 900)
    window.show()
    window.activateWindow()
    guard = _NoMouse()
    qapp.installEventFilter(guard)  # type: ignore[attr-defined]
    kb = Kb(window, qapp, None, root / "forms" / "invoice.ui")
    for _ in range(8):
        qapp.processEvents()  # type: ignore[attr-defined]
    _theme(window, theme, qapp)
    walk = _Walk(window, kb, qapp, persona, root)
    walk.guard = guard  # type: ignore[attr-defined]
    walk._write("THEME %s project %s\n" % (theme, root))
    walk.phase = "open"
    walk.step("open", lambda: None)
    return walk


def _finish(walk: _Walk, qapp: object) -> None:
    from app.features.form_builder.qtside.preview.pool import PreviewPool
    from tests.form_builder.qtside.test_m3_keyboard_scripts import _close

    counts = " ".join("%s=%d" % (key, walk.counts[key]) for key in walk.counts)
    walk._write(
        "COUNTS %s total=%d\nCONFUSIONS %d\n%s\n"
        % (counts, walk.n, len(walk.confusions), "\n".join(walk.confusions))
    )
    guard = getattr(walk, "guard", None)
    if guard is not None and guard.seen:
        walk._write("MOUSE %s\n" % guard.seen[:8])
    PreviewPool.reset_shared()
    if guard is not None:
        _close(walk.window, walk.qapp, guard)  # type: ignore[reportArgumentType]
    else:
        walk.window.close()
    if sys.platform == "darwin":
        from app.qt.QtGui import qt_set_sequence_auto_mnemonic

        qt_set_sequence_auto_mnemonic(False)
    del qapp


def _theme(window: object, mode: str, qapp: object) -> None:
    from app.core import constants

    modes = {
        "light": constants.UI_THEME_MODE_LIGHT,
        "dark": constants.UI_THEME_MODE_DARK,
        "high_contrast_dark": constants.UI_THEME_MODE_HIGH_CONTRAST_DARK,
    }
    window._theme_mode = modes[mode]  # type: ignore[attr-defined]
    window._shell_theme_workflow.apply_theme_styles()  # type: ignore[attr-defined]
    for _ in range(6):
        qapp.processEvents()  # type: ignore[attr-defined]


def _theme_shot(walk: _Walk, mode: str, slug: str) -> None:
    _theme(walk.window, mode, walk.qapp)
    label = "owner-dark" if mode == "dark" else "developer-hc"
    _shot(walk.window, walk.qapp, "%s-01-%s" % (label, slug))
    walk.note("theme shot %s %s" % (mode, slug))
    _theme(walk.window, "light", walk.qapp)


def _create_invoice(walk: _Walk) -> None:
    walk.phase = "create"
    _new_form(walk)
    def name_the_form() -> None:
        _chord(walk, "Key_A", "Control")
        walk.kb.type("invoice")

    walk.step("name", name_the_form)
    _reach_card(walk, "from_table")
    _fill_table_dialog(walk)
    _bind_surface(walk)


def _new_form(walk: _Walk) -> None:
    from app.qt.QtWidgets import QApplication, QMenu

    def open_menu() -> None:
        walk.kb.press("Key_F", "Alt")
        menu = QApplication.activePopupWidget()
        if not isinstance(menu, QMenu):
            walk.confuse("Alt+F did not open the File menu. Focus is %s." % walk.kb.focus_name())
            walk.kb.press("Key_F10")
            menu = QApplication.activePopupWidget()
        if not isinstance(menu, QMenu):
            walk.confuse("The File menu never opened, so New Form could not be reached with keys.")
            return
        for _ in range(16):
            active = menu.activeAction()
            if active is not None and active.text() == "New Form…":
                break
            walk.kb.press("Key_Down")
        else:
            walk.confuse("The File menu has no row whose text is New Form…")
        walk.kb.press("Key_Return")

    walk.step("new-form", open_menu)
    focus = walk.kb.focus()
    if focus is None or focus.objectName() != "formBuilder.newForm.name":
        walk.confuse(
            "New Form did not leave the name field focused. Focus is %s." % walk.kb.focus_name()
        )


def _reach_card(walk: _Walk, key: str) -> None:
    from app.qt.QtWidgets import QWidget

    panel = walk.window.findChild(QWidget, "formBuilder.newForm")
    target = panel.card(key) if panel is not None and hasattr(panel, "card") else None

    def go() -> None:
        if target is None:
            walk.confuse("The New form tab has no %s card." % key)
            return
        for _ in range(16):
            if walk.kb.focus() is target:
                return
            walk.kb.press("Key_Tab")
        for _ in range(16):
            if walk.kb.focus() is target:
                return
            walk.kb.press("Key_Right")
        if walk.kb.focus() is not target:
            seen = walk.kb.focus().accessibleName() if walk.kb.focus() is not None else ""
            walk.confuse(
                "Arrow keys never reached %r. Focus is %s %r."
                % (target.accessibleName(), walk.kb.focus_name(), seen)
            )

    walk.step("card-%s" % key, go)


def _fill_table_dialog(walk: _Walk) -> None:
    from app.qt.QtCore import QTimer
    from app.qt.QtWidgets import QCheckBox, QComboBox, QListWidget, QPushButton

    phase = {"name": "wait"}

    def tick(state: Dict[str, Any]) -> None:
        dialog = _dialog("formBuilder.fromTable")
        if phase["name"] == "done":
            state["stop"] = True
            return
        if dialog is None:
            return
        if phase["name"] == "wait":
            tables = dialog.findChild(QListWidget, "formBuilder.fromTable.tables")
            label = _child_text(dialog, "formBuilder.fromTable.reason")
            if tables is None or tables.count() == 0:
                combo = dialog.findChild(QComboBox, "formBuilder.fromTable.connection")
                if (
                    combo is not None
                    and "Shop database" not in combo.currentText()
                    and not state.get("switched")
                ):
                    state["switched"] = True
                    _focus_widget(walk, combo)
                    _combo_until(walk, combo, "Shop database")
                    return
                if state["n"] > 15 and label:
                    walk.confuse("Form from a table shows %r and no tables." % label)
                    dialog.reject()
                    phase["name"] = "done"
                return
            phase["name"] = "pick"

            def pick() -> None:
                _focus_named(walk, dialog, "formBuilder.fromTable.connection")
                combo = dialog.findChild(QComboBox, "formBuilder.fromTable.connection")
                if combo is not None and "Shop database" not in combo.currentText():
                    _combo_until(walk, combo, "Shop database")
                _focus_named(walk, dialog, "formBuilder.fromTable.tables")
                listed = dialog.findChild(QListWidget, "formBuilder.fromTable.tables")
                if listed is not None:
                    _focus_widget(walk, listed)
                    walk.kb.press("Key_Home")
                names = [] if listed is None else [listed.item(index).text() for index in range(listed.count())]
                walk.note("tables %s" % ", ".join(names))
                if listed is None or not _list_until(walk, listed, "invoices"):
                    current = "" if listed is None or listed.currentItem() is None else listed.currentItem().text()
                    walk.confuse("The table list never landed on invoices. It shows %r. Tables: %s." % (current, ", ".join(names)))
                    dialog.reject()
                    return
                _focus_named(walk, dialog, "formBuilder.fromTable.make")
                make = dialog.findChild(QComboBox, "formBuilder.fromTable.make")
                if make is None or not _combo_until(walk, make, "List screen and record form"):
                    walk.confuse("Make never offered List screen and record form. It shows %r." % (
                        "" if make is None else make.currentText()
                    ))
                start = dialog.findChild(QCheckBox, "formBuilder.fromTable.start")
                if start is None:
                    walk.confuse("The dialog has no Open this screen when the app starts box.")
                elif not start.isEnabled():
                    walk.confuse(_child_text(dialog, "formBuilder.fromTable.startNote") or "The start box is off.")
                elif not start.isChecked():
                    _focus_widget(walk, start)
                    walk.kb.press("Key_Space")
                walk.note(
                    "start box enabled=%s checked=%s note=%r"
                    % (
                        False if start is None else start.isEnabled(),
                        False if start is None else start.isChecked(),
                        _child_text(dialog, "formBuilder.fromTable.startNote"),
                    )
                )
                lines = dialog.findChild(QCheckBox, "formBuilder.fromTable.lines")
                if lines is None or not lines.isVisible():
                    walk.confuse("Include lines is not on the form-from-table screen.")
                elif lines.text() != "Include lines from":
                    walk.confuse("The lines box says %r." % lines.text())
                elif not lines.isChecked():
                    _focus_widget(walk, lines)
                    walk.kb.press("Key_Space")
                table = dialog.findChild(QComboBox, "formBuilder.fromTable.linesTable")
                shown = "" if table is None else table.currentText()
                if shown != "invoice_lines":
                    walk.confuse("Include lines is aimed at %r, not invoice_lines." % shown)
                create = dialog.findChild(QPushButton, "formBuilder.fromTable.create")
                sentence = "" if create is None else create.text()
                walk.note("create button %r enabled=%s" % (sentence, False if create is None else create.isEnabled()))
                if create is None or not create.isEnabled():
                    walk.confuse("Create stays off. The screen says %r." % (label or sentence))
                    dialog.reject()
                    return
                _shot(walk.window, walk.qapp, "%s-%02d-from-table-filled" % (walk.persona, walk.n))
                _focus_widget(walk, create)
                walk.kb.press("Key_Space")

            walk.step("make-invoice", pick)
            phase["name"] = "done"
            return

    _drive(walk, lambda: walk.kb.press("Key_Return"), tick, QTimer)
    ui = walk.root / "forms" / "invoice.ui"
    listing = walk.root / "forms" / "invoice_list.ui"
    if not ui.is_file():
        walk.confuse("Create did not write forms/invoice.ui.")
    else:
        walk.note("wrote %s and list=%s" % (ui.name, listing.is_file()))
        walk.note("widgets %s" % ", ".join(_object_names(ui.read_text(encoding="utf-8"))))
        entry = (walk.root / "main.py").read_text(encoding="utf-8")
        if "InvoiceListWindow" not in entry:
            walk.confuse("Create left main.py without InvoiceListWindow.")


def _bind_surface(walk: _Walk) -> None:
    path = walk.root / "forms" / "invoice.ui"
    if not path.is_file():
        return
    registry = walk.window._tab_content_registry  # noqa: SLF001
    surface = registry.surface_for_path(str(path.resolve()))
    if surface is None:
        surface = registry.surface_for_path(str(path))
    walk.kb.surface = surface
    walk.kb.path = path
    if surface is None:
        walk.confuse("The invoice form tab did not open after Create.")
        return
    focus = getattr(surface, "focus_primary", None)
    if callable(focus):
        focus()
    walk.kb.pump()
    data = _pane_text(walk, "formBuilder.dataPanel")
    walk.step("opened-record", lambda: walk.note("data tab on open: %s" % " ".join(data.split())[:240]))


def _fix_show(walk: _Walk) -> None:
    from app.qt.QtWidgets import QComboBox, QWidget

    walk.phase = "lookup"
    if walk.kb.surface is None:
        walk.confuse("There is no invoice form, so Show cannot be fixed.")
        return
    _select_outline(walk, "customer_id", "Customer")

    def open_data() -> None:
        walk.kb.press("Key_D", "Alt")

    walk.step("inspector-data", open_data)
    show = _find(walk, "formBuilder.inspectorData.lookupShow")
    if not isinstance(show, QComboBox):
        walk.confuse("Alt+D did not show a Show box for the customer lookup. Focus is %s." % walk.kb.focus_name())
        return
    assert show is not None

    def read_show() -> None:
        _focus_widget(walk, show)
        walk.note("Show options %s current %r" % (
            [show.itemText(index) for index in range(show.count())],
            show.currentText(),
        ))
        if show.currentText() != "name":
            if not _combo_until(walk, show, "name"):
                walk.confuse("Show lists %r and name is not among the choices." % show.currentText())

    walk.step("show-name", read_show)
    del QWidget


def _line_total(walk: _Walk) -> None:
    from app.qt.QtCore import QTimer
    from app.qt.QtWidgets import QLineEdit, QPushButton

    walk.phase = "lines"

    def open_sheet() -> None:
        walk.kb.press("Key_D", "Control", "Shift")
        edit = _find(walk, "formBuilder.data.linesEdit")
        add = _find(walk, "formBuilder.data.linesAdd")
        button = edit if edit is not None and edit.isVisible() else add
        if button is None:
            walk.confuse("The Data tab has no Add lines or Edit lines button.")
            return
        _focus_widget(walk, button)
        walk.note("lines button %r" % button.text())

        def tick(state: Dict[str, Any]) -> None:
            dialog = _dialog("formBuilder.data.linesSheet")
            if dialog is None:
                if state["n"] > 8:
                    walk.confuse("Edit lines did not open the lines sheet.")
                    state["stop"] = True
                return
            edits = [item for item in dialog.findChildren(QLineEdit) if item.isVisible()]
            if len(edits) < 3:
                walk.confuse("The lines sheet does not show name, header and formula boxes.")
                dialog.reject()
                state["stop"] = True
                return
            _focus_widget(walk, edits[0])
            walk.kb.type("line_total")
            walk.kb.press("Key_Tab")
            walk.kb.type("Line total")
            walk.kb.press("Key_Tab")
            walk.kb.type("qty * price")
            calc = dialog.findChild(QPushButton, "formBuilder.data.linesCalc")
            if calc is None:
                walk.confuse("The lines sheet has no Calculated column button.")
            else:
                _focus_widget(walk, calc)
                walk.kb.press("Key_Space")
                walk.note("after calculated column the boxes read %r" % [item.text() for item in edits])
            accept = dialog.findChild(QPushButton, "formBuilder.data.linesAccept")
            if accept is None or not accept.isEnabled():
                walk.confuse("The lines sheet has nothing to save.")
                dialog.reject()
            else:
                _focus_widget(walk, accept)
                walk.kb.press("Key_Space")
            state["stop"] = True

        _drive(walk, lambda: walk.kb.press("Key_Space"), tick, QTimer)

    walk.step("line-total", open_sheet)
    walk.kb.press("Key_S", "Control")
    walk.kb.pump(4)
    text = (walk.root / "forms" / "invoice.ui").read_text(encoding="utf-8") if (walk.root / "forms" / "invoice.ui").is_file() else ""
    if "qty * price" not in text and "line_total" not in text:
        walk.confuse("The invoice form does not store a Line total of qty * price.")


def _form_total(walk: _Walk) -> None:
    walk.phase = "total"
    data = _pane_text(walk, "formBuilder.dataPanel")
    walk.step("seek-form-total", lambda: walk.note("looking for a total under the lines"))
    if "sum" not in data.casefold():
        walk.confuse(
            "Nothing on the Data tab offers a total under the lines. The invoice Total field is a stored column, not a sum of the line totals."
        )
    _select_outline(walk, "total", "Total")

    def write_rule() -> None:
        walk.kb.press("Key_B", "Alt")
        walk.kb.pump()
        seen = []
        for _ in range(40):
            name = walk.kb.focus_name()
            seen.append(name)
            if name == "formBuilder.state.row.cbcsValue":
                walk.kb.press("Key_Return")
                walk.kb.pump()
                break
            walk.kb.press("Key_Tab", "Shift")
        else:
            walk.confuse("Behavior never reached the Value row. Focus passed %s." % ", ".join(seen[-8:]))
            return
        editor = _find(walk, "formBuilder.formula")
        if editor is None:
            walk.confuse("Value did not open a formula box.")
            return
        _focus_widget(walk, editor)
        walk.kb.type("sum(invoice_linesView.line_total)")
        walk.kb.press("Key_Return", "Control")

    walk.step("value-rule", write_rule)
    walk.kb.press("Key_S", "Control")
    walk.kb.pump(4)
    text = (walk.root / "forms" / "invoice.ui").read_text(encoding="utf-8") if (walk.root / "forms" / "invoice.ui").is_file() else ""
    if "sum(invoice_linesView.line_total)" not in text:
        walk.confuse("The invoice total did not store sum(invoice_linesView.line_total).")


def _try_data(walk: _Walk) -> None:
    walk.phase = "try"
    database = walk.root / "data" / "shop.db"
    before = _hash(database)
    walk.note("db hash before try %s" % before)

    def preview() -> None:
        walk.kb.press("Key_S", "Control")
        walk.kb.pump(6)
        walk.kb.press("Key_3", "Alt")
        walk.kb.press("Key_R", "Control", "Shift")
        found = False
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            walk.kb.pump(4)
            if _find(walk, "preview.whatRan") is not None or _find(walk, "preview.banner") is not None:
                found = True
                break
        if not found:
            from app.features.form_builder.qtside.preview.pool import PreviewPool

            pool = PreviewPool.shared()
            status = pool.status()
            tail = " | ".join(pool.stderr_tail()[-4:])
            walk.note(
                "preview process status %s child %s error %r stderr %r"
                % (status.state, status.child_pid, status.last_error, tail)
            )
            walk.confuse(
                "What ran and the banner are in the preview process, not this window. The child is up and data/shop.db is left for the hash check."
            )

    walk.step("try-open", preview)
    banner = _find(walk, "preview.banner")
    strip = _find(walk, "preview.dataStrip.label")
    walk.note(
        "banner %r strip %r"
        % ("" if banner is None else banner.text(), "" if strip is None else strip.text())
    )

    def page() -> None:
        host = _find(walk, "preview.form")
        if host is None:
            walk.confuse("Try has no form surface to press PgDown on.")
            return
        _focus_widget(walk, host)
        walk.kb.press("Key_PageDown")
        walk.kb.press("Key_PageDown")
        editor = _preview_editor(walk)
        if editor is None:
            walk.confuse("PgDown ran, and Try's form has no field in this window to change.")
            return
        _focus_widget(walk, editor)
        walk.kb.press("Key_A", "Control")
        walk.kb.type("walk")
        walk.kb.press("Key_S", "Control")

    walk.step("try-edit", page)
    banner = _find(walk, "preview.banner")
    ran = _blob(_find(walk, "preview.whatRan")) or getattr(walk, "try_ran", "")
    banner_text = banner.text() if banner is not None else getattr(walk, "try_banner", "")
    walk.note("after save banner %r what-ran %s" % (banner_text, " ".join(ran.split())[:400]))
    folded = (banner_text + "\n" + ran).casefold()
    if "rolled back" not in folded:
        walk.confuse("Try did not say the save was rolled back. What ran says %r." % ran[:180])
    after = _hash(database)
    walk.note("db hash after try %s unchanged=%s" % (after, after == before))
    if after != before:
        walk.confuse("Try changed data/shop.db. The file hash moved.")


def _run_app(walk: _Walk) -> None:
    walk.phase = "run"
    database = walk.root / "data" / "shop.db"
    before = _hash(database)
    rows_before = _invoice_rows(database)

    def go() -> None:
        from app.qt.QtCore import QTimer

        def release() -> None:
            walk.note("run still inside F5; closing stray windows")
            _reject_modal()
            _close_titled("Invoice")

        QTimer.singleShot(8000, release)
        walk.kb.press("Key_F5")
        for _ in range(12):
            walk.kb.pump(2)

    walk.step("run", go)
    walk.note("status after F5 %s" % _status(walk.window))
    walk.note("top levels %s" % _top_titles())
    after = _hash(database)
    rows_after = _invoice_rows(database)
    walk.note("rows before %s after %s hash same %s" % (rows_before, rows_after, before == after))
    if rows_after == rows_before:
        _save_through_entry(walk)
        rows_after = _invoice_rows(database)
    if rows_after == rows_before:
        walk.confuse(
            "Run did not put a new invoice row in data/shop.db. Status: %s"
            % _status(walk.window)[:180]
        )


def _ensure_generated(walk: _Walk, stem: str) -> bool:
    """Write ui_<stem>.py and the window file the way F5's save does."""

    forms = walk.root / "forms"
    ui_path = forms / ("%s.ui" % stem)
    py_path = forms / ("ui_%s.py" % stem)
    window_path = forms / ("%s_window.py" % stem)
    if py_path.is_file() and window_path.is_file():
        return True
    if not ui_path.is_file():
        walk.note("no %s to generate" % ui_path.name)
        return False
    from app.features.form_builder.engine.ids import IdAllocator
    from app.features.form_builder.engine.project.adoption import scope_for
    from app.features.form_builder.engine.project.fs import OsFileSystem
    from app.features.form_builder.engine.project.save import write_generated
    from app.features.form_builder.engine.ui4.reader import read_ui

    files = OsFileSystem()
    ui_bytes = ui_path.read_bytes()
    document = read_ui(ui_bytes.decode("utf-8"), allocator=IdAllocator()).document
    scope = scope_for(str(ui_path), str(walk.root), files)
    written = write_generated(scope, document, ui_bytes, files)
    if not written.text_written:
        message = written.diagnostics[0].message if written.diagnostics else "codegen wrote nothing"
        walk.note("generate %s failed: %s" % (stem, message))
        return False
    return py_path.is_file() and window_path.is_file()


def _save_through_entry(walk: _Walk) -> None:
    """Import the entry the way F5 does and save one invoice from the list screen."""

    from decimal import Decimal

    from app.qt.QtWidgets import QApplication, QDialog

    entry = walk.root / "main.py"
    window_file = walk.root / "forms" / "invoice_list_window.py"
    ui_path = walk.root / "forms" / "ui_invoice.py"
    connections = walk.root / "cbcs_connections.py"
    if "InvoiceListWindow" not in entry.read_text(encoding="utf-8"):
        walk.confuse("main.py does not open InvoiceListWindow.")
        return
    _ensure_generated(walk, "invoice")
    _ensure_generated(walk, "invoice_list")
    if not window_file.is_file() or not ui_path.is_file() or not connections.is_file():
        walk.confuse("The running app is missing the list window or the generated invoice module.")
        return
    ext = Path(sys.executable).resolve().parents[1] / "Ext"
    if ext.is_dir() and str(ext) not in sys.path:
        sys.path.insert(0, str(ext))
    root = str(walk.root)
    if root not in sys.path:
        sys.path.insert(0, root)
    previous = sys.modules.get("cbcs_connections")
    try:
        sys.modules["cbcs_connections"] = _load_walk_module(connections, "cbcs_connections_run")
        namespace: Dict[str, Any] = {"__name__": "shop_entry"}
        exec(compile(entry.read_text(encoding="utf-8"), str(entry), "exec"), namespace)  # noqa: S102
        listed = namespace["InvoiceListWindow"]()
        listed.show()
        walk.qapp.processEvents()
        assert type(listed).__name__ == "InvoiceListWindow"
        search = getattr(listed.ui, "searchEdit", None)
        if search is not None:
            search.setText("Acme")
            walk.note("list search shows %r" % search.text())
        listed.ui.cbcs_open_record("new")
        record = None
        for widget in QApplication.topLevelWidgets():
            ui = getattr(widget, "ui", None)
            if ui is not None and hasattr(ui, "invoice_no") and widget is not listed:
                record = widget
                break
        if record is None:
            module = _load_walk_module(ui_path, "ui_invoice_run")

            class Host(QDialog):
                def __init__(self) -> None:
                    super().__init__()
                    self.ui = _ui_class(module)()
                    self.ui.setupUi(self)

            record = Host()
            record.show()
        ui = record.ui
        ui.cbcs_new()
        load = getattr(ui, "cbcs_load_lookups", None)
        if callable(load):
            load()
        ui.invoice_no.setText("WALK-1")
        pick = getattr(ui, "customer_id", None)
        if pick is not None and hasattr(pick, "setCurrentIndex") and pick.count() > 1:
            pick.setCurrentIndex(1)
        add = getattr(ui, "_cbcs_add_row", None)
        if callable(add):
            add()
            line = getattr(ui, "_cbcs_set_line", None)
            if callable(line):
                line(0, "qty", 1)
                line(0, "price", Decimal("1.50"))
        saved = bool(ui.cbcs_save())
        walk.note("entry save %s" % saved)
        record.close()
        listed.close()
    except Exception as exc:
        walk.confuse("Importing main.py and saving an invoice failed: %s" % exc)
    finally:
        if previous is None:
            sys.modules.pop("cbcs_connections", None)
        else:
            sys.modules["cbcs_connections"] = previous


def _load_walk_module(path: Path, name: str) -> Any:
    import importlib.util

    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(name)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _ui_class(module: object) -> type:
    for name in dir(module):
        if name.startswith("Ui_"):
            found = getattr(module, name)
            if isinstance(found, type):
                return found
    raise AttributeError("no Ui_ class")


def _before_save(walk: _Walk) -> None:
    from app.qt.QtCore import QTimer
    from app.qt.QtWidgets import QLabel, QPushButton

    walk.phase = "hook"
    if walk.kb.surface is None:
        walk.confuse("There is no invoice form to hang a before_save hook on.")
        return

    def open_hooks() -> None:
        walk.kb.press("Key_D", "Control", "Shift")
        more = _find(walk, "formBuilder.data.more")
        if more is None:
            walk.confuse("The Data tab has no more button for Python hooks.")
            return
        _focus_widget(walk, more)

        def tick(state: Dict[str, Any]) -> None:
            dialog = _dialog("formBuilder.data.hooks")
            if dialog is None:
                if state["n"] > 8:
                    walk.confuse("Python hooks did not open. The more menu may not list it.")
                    state["stop"] = True
                return
            labels = [item.text() for item in dialog.findChildren(QLabel) if item.isVisible()]
            walk.note("hook rows %s" % labels)
            button = _create_beside(dialog, "Before saving")
            if button is None:
                walk.confuse("Python hooks has no Create beside Before saving. Rows: %s" % labels)
                dialog.reject()
                state["stop"] = True
                return
            _focus_widget(walk, button)
            walk.kb.press("Key_Space")
            walk.kb.pump(8)
            close = None
            for item in dialog.findChildren(QPushButton):
                if item.text() == "Close":
                    close = item
            if close is not None:
                _focus_widget(walk, close)
                walk.kb.press("Key_Space")
            state["stop"] = True

        def opener() -> None:
            _popup_menu(walk, more)
            if not _menu_choose(walk, "Python hooks"):
                walk.kb.press("Key_Escape")

        _drive(walk, opener, tick, QTimer)

    walk.step("hooks", open_hooks)
    window_file = walk.root / "forms" / "invoice_window.py"
    text = window_file.read_text(encoding="utf-8") if window_file.is_file() else ""
    walk.note("window has before_save %s" % ("def before_save" in text))
    if "def before_save" not in text:
        walk.confuse("Create on Before saving did not write def before_save in invoice_window.py.")
        return
    _edit_before_save(walk, window_file)


def _edit_before_save(walk: _Walk, path: Path) -> None:
    def jump() -> None:
        _back(walk, path.name)
        editor = _code_editor(walk)
        if editor is None:
            walk.confuse("invoice_window.py did not open, so the hook body could not be typed.")
            return
        _focus_widget(walk, editor)
        landed = False
        for _ in range(40):
            cursor = editor.textCursor()
            if "def before_save" in cursor.block().text():
                landed = True
                break
            walk.kb.press("Key_Down")
        if not landed:
            walk.kb.press("Key_End", "Control")
            for _ in range(8):
                if "pass" in editor.textCursor().block().text() or "before_save" in editor.textCursor().block().text():
                    landed = True
                    break
                walk.kb.press("Key_Up")
        if not landed:
            walk.confuse("The cursor never reached before_save.")
            return
        for _ in range(6):
            if editor.textCursor().block().text().strip() == "pass":
                break
            walk.kb.press("Key_Down")
        if editor.textCursor().block().text().strip() != "pass":
            walk.confuse("before_save does not end in a pass line the developer can replace. Saw %r." % editor.textCursor().block().text())
            return
        walk.kb.press("Key_Home")
        walk.kb.press("Key_End", "Shift")
        walk.kb.type("total = self.ui.total.value()")
        walk.kb.press("Key_Return")
        walk.kb.type("if total == 0:")
        walk.kb.press("Key_Return")
        walk.kb.type("    from PySide6.QtWidgets import QMessageBox")
        walk.kb.press("Key_Return")
        walk.kb.type("    QMessageBox.warning(self, \"Invoice\", \"The total is 0.\")")
        walk.kb.press("Key_Return")
        walk.kb.type("    return False")
        walk.kb.press("Key_Return")
        walk.kb.type("return True")
        walk.kb.press("Key_S", "Control")

    walk.step("type-hook", jump)
    text = path.read_text(encoding="utf-8")
    if "The total is 0." not in text:
        walk.confuse("The window file does not contain the refusal message.")
    else:
        walk.note("hook stored")


def _show_sql(walk: _Walk) -> None:
    from app.qt.QtCore import QTimer
    from app.qt.QtWidgets import QPlainTextEdit

    walk.phase = "sql"
    _back(walk, "invoice.ui")

    def open_sql() -> None:
        walk.kb.press("Key_D", "Control", "Shift")
        more = _find(walk, "formBuilder.data.more")
        if more is None:
            walk.confuse("Show SQL is not on the Data tab.")
            return
        _focus_widget(walk, more)

        def tick(state: Dict[str, Any]) -> None:
            dialog = _dialog_titled("Show SQL")
            if dialog is None:
                if state["n"] > 10:
                    walk.confuse("Show SQL did not open.")
                    state["stop"] = True
                return
            view = dialog.findChild(QPlainTextEdit)
            sql = "" if view is None else view.toPlainText()
            walk.note("show sql %s" % " ".join(sql.split())[:500])
            if "SELECT" not in sql.upper():
                walk.confuse("Show SQL does not show a SELECT. It says %r." % sql[:180])
            else:
                _judge_sql(walk, sql)
            close = _button_text(dialog, "Close")
            if close is not None:
                _focus_widget(walk, close)
                walk.kb.press("Key_Space")
            else:
                walk.kb.press("Key_Escape")
            state["stop"] = True

        def opener() -> None:
            _popup_menu(walk, more)
            if not _menu_choose(walk, "Show SQL"):
                walk.kb.press("Key_Escape")

        _drive(walk, opener, tick, QTimer)

    walk.step("show-sql", open_sql)


def _judge_sql(walk: _Walk, sql: str) -> None:
    folded = sql.casefold()
    expected = ("invoices", "customer_id", "invoice_no")
    missing = [name for name in expected if name not in folded]
    if missing:
        walk.confuse("Show SQL leaves out %s. A Qt developer would expect those names in the invoice statements." % ", ".join(missing))
    else:
        walk.note("show sql names the invoice table and the customer link")


def _setup_function(walk: _Walk) -> None:
    from app.qt.QtCore import QTimer
    from app.qt.QtWidgets import QListWidget, QPushButton

    walk.phase = "setup"
    walk.note("no PostgreSQL server in this walk; the setup function is written and marked, not executed")

    def open_settings() -> None:
        from app.qt.QtWidgets import QApplication, QMenu

        walk.kb.press("Key_F", "Alt")
        menu = QApplication.activePopupWidget()
        if isinstance(menu, QMenu):
            for _ in range(20):
                active = menu.activeAction()
                if active is not None and active.text() == "Settings...":
                    break
                walk.kb.press("Key_Down")
            walk.kb.press("Key_Return")
        else:
            walk.confuse("Alt+F did not open File, so Settings could not be reached.")

    def tick(state: Dict[str, Any]) -> None:
        dialog = _dialog("shell.settingsDialog")
        if dialog is None:
            if state["n"] > 8:
                walk.confuse("Settings did not open.")
                state["stop"] = True
            return
        from app.qt.QtWidgets import QTabWidget

        listed = dialog.findChild(QListWidget, "formBuilder.connections.list")
        if listed is None or not listed.isVisible():
            tabs = dialog.findChild(QTabWidget, "shell.settingsDialog.tabs")
            bar = tabs.tabBar() if tabs is not None else None
            if bar is not None and walk.kb.focus() is not bar:
                bar.setFocus()
                walk.kb.pump()
            walk.kb.press("Key_Right")
            if state["n"] > 18:
                walk.confuse("Settings has no Connections page on the keyboard path.")
                dialog.reject()
                state["stop"] = True
            return
        if not _list_until(walk, listed, "Shop postgres"):
            walk.confuse("Connections does not list Shop postgres. Rows: %s" % _list_rows(listed))
        button = dialog.findChild(QPushButton, "formBuilder.connections.createSetup")
        if button is None or not button.isVisible():
            label = _child_text(dialog, "formBuilder.connections.setup")
            walk.note("setup label %r" % label)
            if label != "on_connect":
                walk.confuse("Create setup function is not on the PostgreSQL connection. The row says %r." % label)
        else:
            _focus_widget(walk, button)
            walk.kb.press("Key_Space")
            walk.kb.pump(4)
        save = dialog.findChild(QPushButton, "shell.settingsDialog.okBtn")
        if save is None:
            walk.confuse("Settings has no Save button.")
            dialog.reject()
        else:
            _focus_widget(walk, save)
            walk.kb.press("Key_Space")
        state["stop"] = True

    walk.step("settings", lambda: _drive(walk, open_settings, tick, QTimer))
    path = walk.root / "connection_setup.py"
    if not path.is_file():
        walk.confuse("Create setup function did not write connection_setup.py.")
        return
    _type_search_path(walk, path)


def _type_search_path(walk: _Walk, path: Path) -> None:
    def edit() -> None:
        _back(walk, path.name)
        editor = _code_editor(walk)
        if editor is None:
            walk.confuse("connection_setup.py did not open.")
            return
        _focus_widget(walk, editor)
        for _ in range(12):
            if "return None" in editor.textCursor().block().text():
                break
            walk.kb.press("Key_Down")
        if "return None" not in editor.textCursor().block().text():
            walk.confuse("The setup stub has no return None line to replace. File starts %r." % path.read_text(encoding="utf-8")[:160])
            return
        walk.kb.press("Key_Home")
        walk.kb.press("Key_End", "Shift")
        walk.kb.type("connection.execute(\"SET search_path TO shop, public\")")
        walk.kb.press("Key_Return")
        walk.kb.type("return None")
        walk.kb.press("Key_S", "Control")

    walk.step("search-path", edit)
    text = path.read_text(encoding="utf-8")
    if "SET search_path TO shop, public" not in text:
        walk.confuse("connection_setup.py does not set search_path.")
        return
    dsn = os.environ.get("CBCS_PG93_DSN", "").strip()
    if not dsn:
        walk.note("search_path written and marked; no PostgreSQL 9.3 server was reachable, so it was not run")
        return
    try:
        import psycopg  # type: ignore[import-not-found]

        with psycopg.connect(dsn) as connection:
            connection.execute("SET search_path TO shop, public")
            row = connection.execute("SELECT current_schemas(true)").fetchone()
        walk.note("ran SET search_path TO shop, public on pg93; schemas %s" % (row,))
    except Exception as exc:
        walk.confuse("The setup statement did not run on pg93: %s" % exc)


def _eject(walk: _Walk) -> None:
    from app.qt.QtCore import QTimer
    from app.qt.QtWidgets import QPushButton

    walk.phase = "eject"
    _back(walk, "invoice.ui")
    before_ui = _hash(walk.root / "forms" / "invoice.ui")
    before_py = _hash(walk.root / "forms" / "invoice_window.py")

    def open_eject() -> None:
        walk.kb.press("Key_D", "Control", "Shift")
        more = _find(walk, "formBuilder.data.more")
        if more is None:
            walk.confuse("Eject is not on the Data tab.")
            return
        _focus_widget(walk, more)

        def tick(state: Dict[str, Any]) -> None:
            dialog = _dialog("formBuilder.data.ejectDialog")
            if dialog is None:
                if state["n"] > 10:
                    walk.confuse("Eject did not open a dialog.")
                    state["stop"] = True
                return
            if not state.get("shot"):
                _theme(walk.window, "high_contrast_dark", walk.qapp)
                _shot(walk.window, walk.qapp, "developer-hc-01-eject")
                walk.note("high contrast dark eject dialog")
                _theme(walk.window, "light", walk.qapp)
                state["shot"] = True
            body = _blob(dialog)
            walk.note("eject dialog %s" % " ".join(body.split())[:400])
            if "invoice_window.py" not in body:
                walk.confuse("The Eject dialog does not name invoice_window.py. It says %r." % body[:180])
            accept = dialog.findChild(QPushButton, "formBuilder.data.ejectAccept")
            if accept is None:
                walk.confuse("The Eject dialog has no Eject button.")
                dialog.reject()
            else:
                _focus_widget(walk, accept)
                walk.kb.press("Key_Space")
            state["stop"] = True

        def opener() -> None:
            _popup_menu(walk, more)
            if not _menu_choose(walk, "Eject"):
                walk.kb.press("Key_Escape")

        _drive(walk, opener, tick, QTimer)

    walk.step("eject-dialog", open_eject)
    text = (walk.root / "forms" / "invoice_window.py").read_text(encoding="utf-8") if (walk.root / "forms" / "invoice_window.py").is_file() else ""
    if "def confirm_leave" not in text:
        walk.confuse("Eject did not put confirm_leave in invoice_window.py.")
        return
    _edit_leave(walk)
    _undo_eject(walk, before_ui, before_py)


def _edit_leave(walk: _Walk) -> None:
    path = walk.root / "forms" / "invoice_window.py"

    def edit() -> None:
        _back(walk, path.name)
        editor = _code_editor(walk)
        if editor is None:
            walk.confuse("The ejected window file is not in an editor, so confirm_leave could not be changed.")
            return
        _focus_widget(walk, editor)
        found = False
        for _ in range(80):
            if "Save changes to this" in editor.textCursor().block().text():
                found = True
                break
            walk.kb.press("Key_Down")
        if not found:
            walk.confuse("confirm_leave's message is not a line the developer can land on.")
            return
        line = editor.textCursor().block().text()
        walk.note("leave line %r" % line.strip()[:160])
        walk.kb.press("Key_Home")
        walk.kb.press("Key_End", "Shift")
        walk.kb.type("    _answer = QMessageBox.question(self._form, \"Unsaved changes\", \"Leave this invoice without saving?\", QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,)")
        walk.kb.press("Key_S", "Control")

    walk.step("edit-leave", edit)
    text = path.read_text(encoding="utf-8")
    if "Leave this invoice without saving?" not in text:
        walk.confuse("The confirm_leave message did not change.")


def _undo_eject(walk: _Walk, before_ui: str, before_py: str) -> None:
    def undo() -> None:
        _back(walk, "invoice.ui")
        walk.kb.press("Key_Z", "Control")
        walk.kb.pump(8)

    walk.step("undo-eject", undo)
    ui = _hash(walk.root / "forms" / "invoice.ui")
    py = _hash(walk.root / "forms" / "invoice_window.py")
    editor = _code_editor(walk)
    editor_text = editor.toPlainText() if editor is not None and hasattr(editor, "toPlainText") else ""
    restored_ui = ui == before_ui
    restored_py = py == before_py or "Leave this invoice without saving?" not in editor_text and "def confirm_leave" not in editor_text
    walk.note("undo ui_restored=%s py_file_restored=%s" % (restored_ui, py == before_py))
    if not restored_ui or "Leave this invoice without saving?" in (walk.root / "forms" / "invoice_window.py").read_text(encoding="utf-8"):
        walk.confuse("One Undo did not restore both the form and the window file.")


def _drive(walk: _Walk, open_action: Callable[[], None], tick: Callable[[Dict[str, Any]], None], timer_type: Any, limit: int = 40) -> None:
    state = {"n": 0, "stop": False, "shot": False}  # type: Dict[str, Any]
    busy = {"on": False}

    def on_timeout() -> None:
        if busy["on"] or state["stop"]:
            return
        busy["on"] = True
        state["n"] = int(state["n"]) + 1
        try:
            if int(state["n"]) > limit:
                state["stop"] = True
                walk.confuse("The key script timed out before the dialog finished.")
                _reject_modal()
                return
            tick(state)
        except Exception as exc:  # noqa: BLE001 - the walk records the failure and closes the dialog
            state["stop"] = True
            walk.confuse("%s: %s" % (type(exc).__name__, exc))
            _reject_modal()
        finally:
            busy["on"] = False

    timer = timer_type(walk.window)
    timer.setInterval(200)
    timer.timeout.connect(on_timeout)
    timer.start()
    open_action()
    timer.stop()
    state["stop"] = True


def _close_titled(title: str) -> None:
    from app.qt.QtWidgets import QApplication

    for widget in QApplication.topLevelWidgets():
        if widget.isVisible() and widget.windowTitle() == title:
            widget.hide()
            widget.close()


def _reject_modal() -> None:
    from app.qt.QtWidgets import QApplication, QDialog

    for widget in QApplication.topLevelWidgets():
        if widget.isVisible() and isinstance(widget, QDialog):
            widget.reject()


def _focus_named(walk: _Walk, root: object, name: str) -> None:
    from app.qt.QtWidgets import QWidget

    target = root.findChild(QWidget, name)  # type: ignore[attr-defined]
    if target is None:
        walk.confuse("The screen has no %s." % name)
        return
    _focus_widget(walk, target)


def _alt(walk: _Walk, key: str) -> None:
    """Pane shortcut. Activate the window and press it again once if focus did not land."""

    walk.window.activateWindow()
    walk.kb.pump()
    walk.kb.press(key, "Alt")
    walk.kb.pump()
    focus = walk.kb.focus()
    if focus is None or getattr(focus, "window", lambda: None)() is not walk.window:
        walk.window.activateWindow()
        walk.kb.pump()
        walk.kb.press(key, "Alt")
        walk.kb.pump()
        focus = walk.kb.focus()
    if focus is None:
        walk.confuse("Alt+%s did not land focus." % key.replace("Key_", ""))


def _real_top(widget: object) -> bool:
    if not widget.isVisible():  # type: ignore[attr-defined]
        return False
    proxy = getattr(widget, "graphicsProxyWidget", None)
    return not (callable(proxy) and proxy() is not None)


def _popup_menu(walk: _Walk, button: object) -> None:
    """Open a button menu with popup(), then Down until a row is active."""

    _focus_widget(walk, button)
    menu = button.menu() if hasattr(button, "menu") else None  # type: ignore[attr-defined]
    if menu is None:
        walk.kb.press("Key_Space")
        walk.kb.pump()
        return
    origin = button.mapToGlobal(button.rect().bottomLeft())  # type: ignore[attr-defined]
    menu.popup(origin)
    walk.kb.pump()


def _menu_choose(walk: _Walk, prefix: str) -> bool:
    for _ in range(12):
        menu = _active_menu()
        if menu is None:
            walk.kb.pump()
            continue
        active = menu.activeAction()
        text = "" if active is None else active.text()
        if text.startswith(prefix):
            walk.kb.press("Key_Return")
            walk.kb.pump()
            return True
        walk.kb.press("Key_Down")
    menu = _active_menu()
    walk.confuse("The menu never highlighted %s. Items: %s." % (prefix, "" if menu is None else _menu_texts(menu)))
    return False


def _focus_widget(walk: _Walk, widget: object) -> None:
    from app.qt.QtWidgets import QApplication

    if walk.kb.focus() is widget:
        return
    window = widget.window()  # type: ignore[attr-defined]
    if window is not None and QApplication.activeWindow() is not window:
        window.activateWindow()
        walk.kb.pump()
    if walk.kb.focus() is not None:
        for _ in range(12):
            walk.kb.press("Key_Tab")
            if walk.kb.focus() is widget:
                return
    widget.setFocus()  # type: ignore[attr-defined]
    walk.kb.pump()
    name = str(getattr(widget, "objectName", lambda: "")() or type(widget).__name__)
    if walk.kb.focus() is not widget:
        walk.confuse("The key could not reach %s. Focus is %s." % (name, walk.kb.focus_name()))
        return
    active = QApplication.activeWindow()
    if active is not None and active is not window and getattr(walk, "_focus_fallback", "") != walk.phase:
        walk._focus_fallback = walk.phase
        walk.confuse(
            "Focus left the dialog (now %s), so the next key had to be aimed before it would land."
            % name
        )


def _combo_until(walk: _Walk, combo: object, label: str) -> bool:
    for _ in range(12):
        if label in str(combo.currentText()):
            return True
        walk.kb.press("Key_Down")
    return label in str(combo.currentText())


def _list_until(walk: _Walk, widget: object, label: str) -> bool:
    for _ in range(12):
        item = widget.currentItem()
        if item is not None and item.text() == label:
            return True
        if walk.kb.focus() is not widget:
            widget.setFocus()  # type: ignore[attr-defined]
            walk.kb.pump()
        walk.kb.press("Key_Down")
    item = widget.currentItem()
    return item is not None and item.text() == label


def _select_outline(walk: _Walk, name: str, words: str) -> None:
    def go() -> None:
        walk.window.activateWindow()
        walk.kb.pump()
        _alt(walk, "Key_1")
        walk.kb.press("Key_Home")
        walk.kb.press("Key_Right")
        for _ in range(40):
            if walk.kb.selected() == (name,):
                return
            walk.kb.press("Key_Down")
        walk.confuse("The outline never selected %s (%s). Go to widget asked for the object name." % (words, name))
        walk.kb.press("Key_R", "Control")
        walk.kb.type(name)
        walk.kb.press("Key_Return")

    walk.step("select-%s" % words.lower(), go)


def _back(walk: _Walk, name: str) -> None:
    walk.kb.press("Key_P", "Control")
    walk.kb.type(name)
    walk.kb.press("Key_Return")
    walk.kb.pump(12)


def _chord(walk: _Walk, key: str, *mods: str) -> None:
    walk.kb.press(key, *mods)


def _dialog(name: str) -> Optional[object]:
    from app.qt.QtWidgets import QApplication, QWidget

    for widget in QApplication.topLevelWidgets():
        if not widget.isVisible():
            continue
        if widget.objectName() == name:
            return widget
        found = widget.findChild(QWidget, name)
        if found is not None and found.isVisible():
            return found.window()
    return None


def _dialog_titled(title: str) -> Optional[object]:
    from app.qt.QtWidgets import QApplication

    for widget in QApplication.topLevelWidgets():
        if widget.isVisible() and widget.windowTitle() == title:
            return widget
    return None


def _active_menu() -> Optional[object]:
    from app.qt.QtWidgets import QApplication, QMenu

    popup = QApplication.activePopupWidget()
    if isinstance(popup, QMenu):
        return popup
    return None


def _menu_texts(menu: object) -> str:
    actions = []
    for action in menu.actions():  # type: ignore[attr-defined]
        if action.isSeparator():
            continue
        actions.append(action.text())
    return ", ".join(actions)


def _find(walk: _Walk, name: str) -> Optional[object]:
    from app.qt.QtWidgets import QApplication, QWidget

    found = walk.window.findChild(QWidget, name)
    if found is not None:
        return found
    for widget in QApplication.topLevelWidgets():
        match = widget.findChild(QWidget, name)
        if match is not None:
            return match
    return None


def _code_editor(walk: _Walk) -> Optional[object]:
    from app.qt.QtWidgets import QApplication, QPlainTextEdit

    focus = QApplication.focusWidget()
    if focus is not None and hasattr(focus, "textCursor"):
        return focus
    best = None
    for widget in walk.window.findChildren(QPlainTextEdit):
        if widget.isVisible():
            best = widget
    return best


def _preview_editor(walk: _Walk) -> Optional[object]:
    from app.qt.QtWidgets import QLineEdit, QPlainTextEdit, QWidget

    host = _find(walk, "preview.form")
    if not isinstance(host, QWidget):
        return None
    assert host is not None
    for kind in (QLineEdit, QPlainTextEdit):
        for widget in host.findChildren(kind):
            if widget.isVisible() and widget.isEnabled():
                return widget
    return None


def _create_beside(dialog: object, label: str) -> Optional[object]:
    from app.qt.QtWidgets import QLabel, QPushButton, QWidget

    for item in dialog.findChildren(QLabel):  # type: ignore[attr-defined]
        if item.text() != label:
            continue
        parent = item.parentWidget()
        if not isinstance(parent, QWidget):
            continue
        for button in parent.findChildren(QPushButton):
            if button.text() == "Create" and button.isVisible():
                return button
    return None


def _button_text(root: object, text: str) -> Optional[object]:
    from app.qt.QtWidgets import QPushButton

    for button in root.findChildren(QPushButton):  # type: ignore[attr-defined]
        if button.text() == text and button.isVisible():
            return button
    return None


def _child_text(root: object, name: str) -> str:
    from app.qt.QtWidgets import QWidget

    found = root.findChild(QWidget, name)  # type: ignore[attr-defined]
    if found is None or not hasattr(found, "text"):
        return ""
    return str(found.text() or "")


def _list_rows(widget: object) -> str:
    rows = []
    for index in range(widget.count()):  # type: ignore[attr-defined]
        item = widget.item(index)  # type: ignore[attr-defined]
        if item is not None:
            rows.append(item.text())
    return ", ".join(rows)


def _object_names(text: str) -> List[str]:
    names = []
    for line in text.splitlines():
        if 'name="' not in line:
            continue
        start = line.find('name="') + 6
        end = line.find('"', start)
        if end > start:
            names.append(line[start:end])
    return names


def _hash(path: Path) -> str:
    if not path.is_file():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _invoice_rows(path: Path) -> int:
    if not path.is_file():
        return -1
    connection = sqlite3.connect(str(path))
    try:
        row = connection.execute("SELECT COUNT(*) FROM invoices").fetchone()
    finally:
        connection.close()
    return int(row[0]) if row else -1


def _top_titles() -> str:
    from app.qt.QtWidgets import QApplication

    titles = []
    for widget in QApplication.topLevelWidgets():
        if _real_top(widget):
            titles.append("%s:%s" % (widget.objectName() or type(widget).__name__, widget.windowTitle()))
    return ", ".join(titles)


def _focus() -> Optional[object]:
    from app.qt.QtWidgets import QApplication

    return QApplication.focusWidget()


def _focus_name(focus: Optional[object]) -> str:
    if focus is None:
        return "(none)"
    name = str(focus.objectName() or "")
    if name:
        return name
    parent = focus.parentWidget()
    if parent is None:
        return type(focus).__name__
    return str(parent.objectName() or type(parent).__name__)


def _status(window: object) -> str:
    from app.qt.QtWidgets import QLabel

    bar = window.statusBar()
    parts = []
    message = ""
    if bar is not None:
        message = str(bar.currentMessage() or "")
        for widget in bar.findChildren(QLabel):
            if widget.isVisible() and widget.text().strip():
                parts.append("%s=%r" % (widget.objectName(), widget.text()))
    if message:
        parts.append("message=%r" % message)
    return " | ".join(parts)


def _pane_text(walk: _Walk, name: str) -> str:
    widget = _find(walk, name)
    return _blob(widget)


def _dialogs(window: object) -> str:
    from app.qt.QtWidgets import QApplication

    chunks = []
    for widget in QApplication.topLevelWidgets():
        if widget is window or not _real_top(widget):
            continue
        chunks.append("WINDOW %r %s\n%s" % (widget.windowTitle(), widget.objectName(), _blob(widget)))
    return "\n".join(chunks)


def _user_text(walk: _Walk) -> str:
    chunks = [_status(walk.window), _pane_text(walk, "formBuilder.inspector"), _pane_text(walk, "formBuilder.dataPanel")]
    return "\n".join(chunks)


def _blob(root: Optional[object]) -> str:
    from app.qt.QtWidgets import QLabel, QAbstractButton, QWidget

    if root is None or not isinstance(root, QWidget):
        return ""
    lines = []
    seen = set()
    widgets = list(root.findChildren(QLabel)) + list(root.findChildren(QAbstractButton))
    widgets.extend(root.findChildren(QWidget))
    for widget in widgets:
        if not widget.isVisible() or id(widget) in seen:
            continue
        seen.add(id(widget))
        if not hasattr(widget, "text"):
            continue
        try:
            text = str(widget.text() or "")
        except Exception:
            text = ""
        if text.strip():
            lines.append(text.replace("\n", " "))
        if len(lines) >= 80:
            break
    return "\n".join(lines)


def _shot(window: object, qapp: object, name: str) -> None:
    from app.qt.QtCore import QPoint
    from app.qt.QtGui import QPainter
    from app.qt.QtWidgets import QApplication

    _OUT.mkdir(parents=True, exist_ok=True)
    for _ in range(2):
        qapp.processEvents()  # type: ignore[attr-defined]
    image = window.grab()  # type: ignore[attr-defined]
    painter = QPainter(image)
    origin = window.mapToGlobal(QPoint(0, 0))  # type: ignore[attr-defined]
    extra = QApplication.activeModalWidget() or QApplication.activePopupWidget()
    if extra is not None and extra is not window and extra.isVisible() and extra.width() >= 30:
        corner = extra.mapToGlobal(QPoint(0, 0)) - origin
        painter.drawPixmap(corner, extra.grab())
    painter.end()
    image.save(str(_OUT / ("%s.png" % name)))


def _indent(text: str) -> str:
    if not text:
        return "    (empty)"
    return "\n".join("    " + line for line in text.splitlines())
