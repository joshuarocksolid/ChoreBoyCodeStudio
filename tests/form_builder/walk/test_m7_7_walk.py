# pyright: reportAttributeAccessIssue=false
"""M7.7 persona walks. Skipped unless CBCS_FB_WALK=1. Not a unit-lane test.

Keys only, on a real MainWindow, over a fresh copy of the M7 invoice project.
Each step writes a screenshot and a log line under scratchpad/walk77/.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Any, Callable, List, Optional, cast

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("CBCS_FB_WALK") != "1",
    reason="persona walk; set CBCS_FB_WALK=1",
)

_ROOT = Path(__file__).resolve().parents[3]
_FIX = Path(__file__).resolve().parents[1] / "fixtures" / "m7"
_OUT = _ROOT / "scratchpad" / "walk77"
_OWNER_JARGON = (
    "cbcs",
    "self.",
    "expression",
    "validator",
    "QLineEdit",
    "QSpinBox",
    "QLabel",
    "QPushButton",
    "QCheckBox",
    "QDialog",
    "discountEdit",
    "discountCheck",
    "qtySpin",
    "priceSpin",
    "lineTotalLabel",
    "emailEdit",
    "saveButton",
    "save_invoice",
)


def test_shop_owner_walk(tmp_path: Path, qapp: object, theme: str = "light") -> None:
    _owner(tmp_path, qapp, theme)


def test_shop_owner_walk_dark(tmp_path: Path, qapp: object) -> None:
    _owner(tmp_path, qapp, "dark")


def test_qt_developer_walk(tmp_path: Path, qapp: object) -> None:
    _developer(tmp_path, qapp, "light")


def test_qt_developer_walk_hc_dark(tmp_path: Path, qapp: object) -> None:
    _developer(tmp_path, qapp, "high_contrast_dark")


def _owner(tmp_path: Path, qapp: object, theme: str) -> None:
    persona = "owner" if theme == "light" else "owner-dark"
    walk = _boot(tmp_path, qapp, persona, theme)
    try:
        walk.phase = "open"
        walk.step("open", lambda: None)
        _w1(walk)
        _w2(walk)
        _email(walk)
        _save_checks_first(walk, create_call=True)
        _try_mode(walk)
        _read_as_text(walk)
        _assert_owner(walk)
    finally:
        _finish(walk, qapp)


def _developer(tmp_path: Path, qapp: object, theme: str) -> None:
    persona = "developer" if theme == "light" else "developer-hc"
    walk = _boot(tmp_path, qapp, persona, theme)
    try:
        walk.phase = "open"
        walk.step("open", lambda: None)
        _w3(walk)
        _write_is_manager(walk)
        _visible_when_manager(walk)
        _uses(walk, "saveButton")
        _uses_method(walk, "save_invoice")
        _rename(walk)
        _open_generated(walk)
        _assert_developer(walk)
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
        self.counts = {}  # type: dict
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
        focus = _focus(self.qapp)
        acc = focus.accessibleName() if focus is not None else ""
        status = _status(self.window)
        body = _inspector(self.kb)
        dialog = _dialogs(self.window)
        if self.persona.startswith("owner"):
            self._scan(slug, _user_text(self))
        line = (
            "STEP %02d %s phase=%s\n  keys: %s\n  focus: %s acc=%r\n  status: %s\n  inspector:\n%s\n  dialogs:\n%s\n"
            % (self.n, slug, self.phase, keys, _focus_name(focus), acc, status, _indent(body), _indent(dialog))
        )
        self._write(line)
        _shot(self.window, self.qapp, "%s-%02d-%s" % (self.persona, self.n, slug))

    def confuse(self, text: str) -> None:
        quote = text.strip()
        if not quote or quote in self.confusions:
            return
        self.confusions.append(quote)
        self._write("CONFUSION phase=%s %s\n" % (self.phase, quote))

    def _scan(self, slug: str, blob: str) -> None:
        del slug
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
    from app.shell.main_window import MainWindow
    from tests.form_builder.qtside.test_m3_keyboard_scripts import Kb, _NoMouse, _open, _project, _require

    _require()
    if sys.platform == "darwin":
        from app.qt.QtGui import qt_set_sequence_auto_mnemonic

        qt_set_sequence_auto_mnemonic(True)
    root = tmp_path / "shop"
    shutil.copytree(_FIX, root)
    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    _project(window, root)
    path = root / "forms" / "invoice.ui"
    text = path.read_text(encoding="utf-8")
    surface = _open(window, qapp, path, text)
    entries = [
        ProjectFileEntry(str(item.relative_to(root)).replace("\\", "/"), str(item.resolve()), False)
        for item in root.rglob("*")
        if item.is_file() and item.suffix in (".py", ".ui", ".json")
    ]
    project = window._loaded_project  # noqa: SLF001
    window._loaded_project = LoadedProject(  # noqa: SLF001
        project_root=project.project_root,
        manifest_path=project.manifest_path,
        metadata=ProjectMetadata(schema_version=2, name="Shop", default_entry="main.py"),
        entries=entries,
    )
    window.set_project_placeholder("Shop")
    guard = _NoMouse()
    qapp.installEventFilter(guard)  # type: ignore[attr-defined]
    kb = Kb(window, qapp, surface, path)
    surface.focus_primary()
    kb.pump()
    _theme(window, theme, qapp)
    walk = _Walk(window, kb, qapp, persona, root)
    walk.guard = guard  # type: ignore[attr-defined]
    walk._write("THEME %s project %s\n" % (theme, root))
    return walk


def _finish(walk: _Walk, qapp: object) -> None:
    from app.features.form_builder.qtside.preview.pool import PreviewPool
    from tests.form_builder.qtside.test_m3_keyboard_scripts import _close

    counts = " ".join("%s=%d" % (key, walk.counts[key]) for key in walk.counts)
    walk._write("COUNTS %s\nCONFUSIONS %d\n%s\n" % (counts, len(walk.confusions), "\n".join(walk.confusions)))
    guard = getattr(walk, "guard", None)
    if guard is not None and guard.seen:
        walk._write("MOUSE %s\n" % guard.seen)
    PreviewPool.reset_shared()
    if guard is not None:
        _close(cast(Any, walk.window), cast(Any, qapp), guard)
    else:
        walk.window.close()
    if sys.platform == "darwin":
        from app.qt.QtGui import qt_set_sequence_auto_mnemonic

        qt_set_sequence_auto_mnemonic(False)


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


def _w1(walk: _Walk) -> None:
    walk.phase = "W1"
    walk.step("select-discount-rate", lambda: _select(walk, "discountEdit"))
    walk.step("open-enabled-when", lambda: _open_row(walk, "formBuilder.state.row.cbcsEnabledWhen"))
    walk.step("pick-discount", lambda: _type_tab(walk, "disc"))
    walk.step("commit-enabled", lambda: walk.kb.press("Key_Return", "Control"))


def _w2(walk: _Walk) -> None:
    walk.phase = "W2"
    walk.step("select-line-total", lambda: _select(walk, "lineTotalLabel"))
    walk.step("open-value", lambda: _open_row(walk, "formBuilder.state.row.cbcsValue"))

    def shape() -> None:
        walk.kb.press("Key_Down")

    walk.step("shape-times", shape)

    def qty() -> None:
        _tab_until(walk, {"formBuilder.builder.term.0.field"})
        _type_tab(walk, "qty")

    walk.step("pick-qty", qty)

    def operator() -> None:
        _tab_until(walk, {"formBuilder.builder.op.1"})
        walk.kb.press("Key_Down")
        walk.kb.press("Key_Down")

    walk.step("pick-times", operator)

    def price() -> None:
        _tab_until(walk, {"formBuilder.builder.term.1.field"})
        _type_tab(walk, "price")

    walk.step("pick-price", price)
    walk.step("commit-value", lambda: walk.kb.press("Key_Return", "Control"))

    def money() -> None:
        if not _tab_until(walk, {"formBuilder.state.format"}, limit=14, required=False):
            walk.confuse("After the value is saved, Tab never lands on Format. The list is not in the row.")
            return
        walk.kb.press("Key_Down")

    walk.step("format-money", money)


def _email(walk: _Walk) -> None:
    walk.phase = "email"
    walk.step("select-email", lambda: _select(walk, "emailEdit"))
    walk.step("behavior", lambda: walk.kb.press("Key_B", "Alt"))
    walk.step("add-required", lambda: _add_check(walk, "Required"))
    walk.step("commit-required", lambda: walk.kb.press("Key_Return", "Control"))

    def label() -> None:
        offer = _child(walk, "formBuilder.checks.offer")
        if offer is None or not offer.isVisible():
            walk.confuse("Required did not offer a message label.")
            return
        _land(walk, "formBuilder.checks.addLabel")
        walk.kb.press("Key_Return")

    walk.step("add-label", label)
    walk.step("add-email", lambda: _add_check(walk, "Email address"))
    walk.step("commit-email", lambda: walk.kb.press("Key_Return", "Control"))


def _save_checks_first(walk: _Walk, create_call: bool) -> None:
    walk.phase = "save"
    walk.step("select-save", lambda: _select(walk, "saveButton"))
    if create_call:
        walk.step("call-save-invoice", lambda: _add_call(walk))
    walk.step("add-check-all", lambda: _add_then(walk, "check all", "Check all fields"))
    walk.step("check-all-first", lambda: walk.kb.press("Key_Up", "Alt"))


def _w3(walk: _Walk) -> None:
    walk.phase = "W3"
    walk.step("select-save", lambda: _select(walk, "saveButton"))
    walk.step("call-save-invoice", lambda: _add_call(walk))
    _email(walk)
    walk.phase = "W3"
    walk.step("select-save-again", lambda: _select(walk, "saveButton"))
    walk.step("add-check-all", lambda: _add_then(walk, "check all", "Check all fields"))

    def first() -> None:
        for _ in range(4):
            if _save_steps(walk)[:1] == ["validate"]:
                return
            walk.kb.press("Key_Up", "Alt")
            walk.kb.pump()
        if _save_steps(walk)[:1] != ["validate"]:
            walk.confuse("Alt+Up did not put Check all fields first. Steps are %s." % _save_steps(walk))

    walk.step("check-all-first", first)


def _write_is_manager(walk: _Walk) -> None:
    walk.phase = "method"
    _back(walk, "invoice_window.py")

    def typed() -> None:
        walk.kb.press("Key_End", "Control")
        walk.kb.press("Key_Return")
        walk.kb.press("Key_Return")
        walk.kb.press("Key_Home")
        walk.kb.type("    def is_manager(self) -> bool:")
        walk.kb.press("Key_Return")
        walk.kb.type("return False")
        walk.kb.press("Key_S", "Control")

    walk.step("type-is-manager", typed)
    _back(walk, "invoice.ui")
    walk.step("back-to-form", lambda: None)


def _visible_when_manager(walk: _Walk) -> None:
    walk.phase = "visible"
    walk.step("select-discount", lambda: _select(walk, "discountCheck"))
    walk.step("open-visible-when", lambda: _open_row(walk, "formBuilder.state.row.cbcsVisibleWhen"))

    def formula() -> None:
        found = False
        for _ in range(8):
            if _focus_name(_focus(walk.qapp)) == "formBuilder.formula.switch":
                found = True
                break
            walk.kb.press("Key_Tab", "Shift")
        if not found:
            walk.confuse(
                "Visible when did not show Formula. Focus is %s." % _focus_name(_focus(walk.qapp))
            )
            return
        walk.kb.press("Key_Space")
        walk.kb.pump()
        _tab_until(walk, {"formBuilder.formula"}, limit=6, required=False)
        walk.kb.type("window.is_manager()")
        walk.kb.press("Key_Return", "Control")

    walk.step("formula-is-manager", formula)


def _uses(walk: _Walk, name: str) -> None:
    walk.phase = "uses"
    walk.step("select-%s" % name, lambda: _select(walk, name))

    def opened() -> None:
        walk.kb.press("Key_F12", "Shift")
        walk.kb.pump(8)
        dialog = _child(walk, "formBuilder.logic.uses")
        if dialog is None or not dialog.isVisible():
            walk.confuse("Shift+F12 on %s did not open Uses." % name)
            return
        blob = _blob(dialog)
        walk._write("USES %s\n%s\n" % (name, blob))
        if "save_invoice" not in blob and "clicked" not in blob.casefold():
            walk.confuse("Uses of %s does not list its events. Saw %r" % (name, blob[:300]))

    walk.step("uses-of-%s" % name, opened)
    _dismiss_uses(walk)


def _dismiss_uses(walk: _Walk) -> None:
    from app.qt.QtCore import Qt
    from app.qt.QtTest import QTest

    dialog = _child(walk, "formBuilder.logic.uses")
    if dialog is None or not dialog.isVisible():
        return
    focused = _focus(walk.qapp)
    if focused is None or not (focused is dialog or dialog.isAncestorOf(focused)):
        walk.confuse(
            "Uses opened with no keyboard focus. Title %r. Escape had to go to the dialog itself."
            % dialog.windowTitle()
        )
        QTest.keyClick(dialog, Qt.Key.Key_Escape)
        walk.kb.pump()
        return
    walk.kb.press("Key_Escape")
    walk.kb.pump()


def _from_events(walk: _Walk, needle: str) -> bool:
    from app.qt.QtWidgets import QWidget

    methods = walk.window.findChild(QWidget, "formBuilder.yourMethods")
    link = getattr(methods, "_link_tab", None)
    if callable(link):
        link()
    events = walk.window.findChild(QWidget, "formBuilder.events")
    first = events.first_focus() if events is not None and hasattr(events, "first_focus") else None
    if first is not None:
        first.setFocus()
        walk.kb.pump()
    return _tab_until_acc(walk, needle, limit=40)


def _uses_method(walk: _Walk, method: str) -> None:
    walk.phase = "uses"
    walk.step("select-form", lambda: _select_form(walk))
    walk.step("behavior", lambda: walk.kb.press("Key_B", "Alt"))

    def row() -> None:
        if not _from_events(walk, method):
            walk.confuse("Your methods did not focus %s." % method)
            return
        walk.kb.press("Key_F12", "Shift")
        walk.kb.pump(8)
        dialog = _child(walk, "formBuilder.logic.uses")
        if dialog is None or not dialog.isVisible():
            walk.confuse("Shift+F12 on %s did not open Uses." % method)
            return
        title = dialog.windowTitle()
        if method not in title and method not in _blob(dialog):
            walk.confuse("Uses title is %r, not %s." % (title, method))
        _dismiss_uses(walk)

    walk.step("uses-of-%s" % method, row)


def _rename(walk: _Walk) -> None:
    walk.phase = "rename"
    walk.step("select-form", lambda: _select_form(walk))
    walk.step("behavior", lambda: walk.kb.press("Key_B", "Alt"))

    def menu() -> None:
        if not _from_events(walk, "save_invoice"):
            walk.confuse("Could not focus save_invoice to rename it.")
            return
        walk.kb.press("Key_F10", "Shift")
        walk.kb.pump()
        if not _menu_arm(walk, "Rename"):
            walk.confuse("Shift+F10 on Your methods did not offer Rename. The row has no keyboard rename.")
            return
        note = _drive_rename(walk)
        if note:
            walk.confuse(note)

    walk.step("rename-preview-accept", menu)
    before_form = _prop(walk, "saveButton", "cbcsOnClicked")
    before_py = (walk.root / "forms" / "invoice_window.py").read_text(encoding="utf-8")

    def undo() -> None:
        if "def save_and_close" not in before_py and "save_and_close" not in before_form:
            walk.confuse("Rename never started, so there was no undo to try.")
            return
        _back(walk, "invoice.ui")
        walk.kb.press("Key_Z", "Control")

    walk.step("one-undo", undo)
    after_form = _prop(walk, "saveButton", "cbcsOnClicked") + _native_slots(walk)
    after_py = (walk.root / "forms" / "invoice_window.py").read_text(encoding="utf-8")
    renamed = "def save_and_close" in before_py or "save_and_close" in (before_form or "")
    if not renamed:
        walk.kb.pump()
        del before_py
        return
    form_back = "save_and_close" not in after_form and "save_invoice" in (after_form or before_form or _native_slots(walk))
    editor_py = _window_editor(walk)
    file_still = "def save_and_close" in after_py or "def save_and_close" in editor_py
    if not form_back:
        walk.confuse("The form undo did not restore the steps. Form is %r." % after_form[:180])
    if file_still:
        _back(walk, "invoice_window.py")
        walk.kb.press("Key_Z", "Control")
        walk.kb.pump()
        after_py = (walk.root / "forms" / "invoice_window.py").read_text(encoding="utf-8")
        editor_py = _window_editor(walk)
        restored = "def save_and_close" not in after_py and "def save_and_close" not in editor_py and (
            "def save_invoice" in after_py or "def save_invoice" in editor_py
        )
        if not restored:
            walk.confuse("The window-tab undo did not restore save_invoice.")
        else:
            walk._write("UNDO one form undo restored the steps. One window-tab undo restored the method.\n")
    elif "def save_invoice" in after_py or "def save_invoice" in editor_py:
        walk._write("UNDO the form undo also restored the window file.\n")
    walk.kb.pump()
    del before_py


def _open_generated(walk: _Walk) -> None:
    walk.phase = "generated"
    walk.step("save-form", lambda: _save_current(walk))
    _back(walk, "ui_invoice.py")

    def look() -> None:
        path = walk.root / "forms" / "ui_invoice.py"
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
        walk._write("GENERATED exists=%s bytes=%d\n" % (path.is_file(), len(text)))
        for needle in ("cbcs_validate", "save_invoice", "save_and_close", "Email", "email"):
            walk._write("  has %s: %s\n" % (needle, needle in text))
        if "def cbcs_validate" not in text:
            walk.confuse("ui_invoice.py has no cbcs_validate. A blank email's stop is not in the generated file.")
        if "save_invoice" not in text and "save_and_close" not in text:
            walk.confuse("ui_invoice.py does not name the save method.")
        editor = _editor(walk.qapp)
        if editor is None:
            from app.qt.QtWidgets import QPlainTextEdit

            for widget in walk.window.findChildren(QPlainTextEdit):
                if "cbcs_validate" in widget.toPlainText():
                    editor = widget
                    break
        if editor is None:
            walk.confuse("ui_invoice.py did not open in the editor.")
            return
        shown = editor.toPlainText()
        if "cbcs_validate" not in shown:
            walk.confuse("The open ui_invoice.py tab does not show cbcs_validate.")

    walk.step("read-ui-invoice", look)


def _try_mode(walk: _Walk) -> None:
    walk.phase = "try"
    walk.step("select-save", lambda: _select(walk, "saveButton"))

    def opened() -> None:
        walk.kb.press("Key_R", "Control", "Shift")
        found = False
        for _ in range(40):
            walk.kb.pump(2)
            if _child(walk, "preview.whatRan") is not None:
                found = True
                break
        if not found:
            from app.features.form_builder.qtside.preview.pool import PreviewPool

            status = PreviewPool.shared().status()
            walk.confuse(
                "Ctrl+Shift+R did not show What ran in this window. Preview status is %s, child %s, error %r."
                % (status.state, status.child_pid, status.last_error)
            )

    walk.step("preview", opened)
    pane = _child(walk, "preview.whatRan")
    if pane is None:
        return

    def discount() -> None:
        _key_widget(walk, "discountCheck", "Key_Space")

    walk.step("tick-discount", discount)

    def email_blank() -> None:
        _key_widget(walk, "emailEdit", "Key_A")
        walk.kb.press("Key_Backspace")
        walk.kb.press("Key_Tab")

    walk.step("blank-email", email_blank)

    def save() -> None:
        _key_widget(walk, "saveButton", "Key_Space")

    walk.step("try-save", save)


def _read_as_text(walk: _Walk) -> None:
    walk.phase = "read"

    def opened() -> None:
        _back(walk, "invoice.ui")
        walk.kb.press("Key_1", "Alt")
        walk.kb.pump()
        walk.kb.press("Key_L", "Alt")
        walk.kb.pump()
        if _focus_name(_focus(walk.qapp)) == "formBuilder.logic.filter":
            walk.kb.press("Key_Tab", "Shift")
            walk.kb.pump()
        if _focus_name(_focus(walk.qapp)) != "formBuilder.logic.readAsText":
            walk.confuse("Alt+L did not put Read as text on a key. Focus is %s." % _focus_name(_focus(walk.qapp)))
            return
        walk.kb.press("Key_Space")
        walk.kb.pump(8)

    walk.step("read-as-text", opened)
    page = _child(walk, "formBuilder.readAsText")
    text = _blob(page) if page is not None else ""
    walk._write("READ AS TEXT\n%s\n" % text)
    if "enabled only when" not in text.casefold() and "Discount" not in text:
        walk.confuse("Read as text does not say the discount rule. Saw %r" % text[:300])
    if "Qty" not in text and "qty" not in text.casefold():
        walk.confuse("Read as text does not say the line total. Saw %r" % text[:300])


def _assert_owner(walk: _Walk) -> None:
    enabled = _prop(walk, "discountEdit", "cbcsEnabledWhen")
    value = _prop(walk, "lineTotalLabel", "cbcsValue")
    checks = _prop(walk, "emailEdit", "cbcsValidate")
    steps = _save_steps(walk)
    walk._write("OWNER enabled=%r value=%r checks=%r steps=%s\n" % (enabled, value, checks, steps))
    assert enabled.strip() == "discountCheck", enabled
    assert "qtySpin" in value and "priceSpin" in value, value
    assert "required" in checks and "email" in checks, checks
    assert steps and steps[0] == "validate", steps
    assert any(item == "call:save_invoice" for item in steps), steps
    assert walk.counts.get("W1", 99) <= 12, walk.counts
    assert walk.counts.get("W2", 99) <= 12, walk.counts


def _assert_developer(walk: _Walk) -> None:
    window_file = (walk.root / "forms" / "invoice_window.py").read_text(encoding="utf-8")
    visible = _prop(walk, "discountCheck", "cbcsVisibleWhen")
    steps = _save_steps(walk)
    walk._write("DEV steps=%s visible=%r\n%s\n" % (steps, visible, window_file))
    assert "def is_manager(self) -> bool:" in window_file, window_file
    assert "is_manager" in visible, visible
    assert steps and steps[0] == "validate", steps
    generated = walk.root / "forms" / "ui_invoice.py"
    assert generated.is_file(), "ui_invoice.py was not written"
    text = generated.read_text(encoding="utf-8")
    assert "def cbcs_validate" in text, text[:500]
    assert "save_invoice" in text or "save_and_close" in text


def _select(walk: _Walk, name: str) -> None:
    _ensure_form(walk)
    walk.kb.press("Key_1", "Alt")
    walk.kb.pump()
    if _focus_name(_focus(walk.qapp)) != "formBuilder.structure":
        walk.confuse(
            "Alt+1 left focus on %s, so the next field had to be chosen by typing its object name."
            % _focus_name(_focus(walk.qapp))
        )
        walk.kb.press("Key_R", "Control")
        walk.kb.type(name)
        walk.kb.press("Key_Return")
        walk.kb.pump()
        return
    walk.kb.press("Key_Home")
    walk.kb.press("Key_Right")
    shown = ""
    for _ in range(40):
        shown = _outline(walk)
        if walk.kb.selected() == (name,):
            if shown == name:
                walk.confuse("The outline names this field %r, not a label a shop owner would recognise." % shown)
            return
        walk.kb.press("Key_Down")
    walk.confuse("Arrow keys never selected %s. Go to widget asked for the object name. Last outline row was %r." % (name, shown))
    walk.kb.press("Key_R", "Control")
    walk.kb.type(name)
    walk.kb.press("Key_Return")
    walk.kb.pump()


def _select_form(walk: _Walk) -> None:
    walk.kb.press("Key_1", "Alt")
    walk.kb.press("Key_Home")
    walk.kb.pump()


def _open_row(walk: _Walk, row_name: str) -> None:
    walk.kb.press("Key_B", "Alt")
    walk.kb.pump()
    seen = []
    for _ in range(40):
        name = _focus_name(_focus(walk.qapp))
        seen.append(name)
        if name == row_name:
            walk.kb.press("Key_Return")
            walk.kb.pump()
            return
        walk.kb.press("Key_Tab", "Shift")
    raise AssertionError("row %s not reached: %s" % (row_name, seen))


def _type_tab(walk: _Walk, text: str) -> None:
    walk.kb.type(text)
    walk.kb.press("Key_Tab")
    walk.kb.pump()


def _tab_until(walk: _Walk, names: set, limit: int = 8, required: bool = True) -> bool:
    seen = []
    for _ in range(limit):
        name = _focus_name(_focus(walk.qapp))
        seen.append(name)
        if name in names:
            return True
        walk.kb.press("Key_Tab")
    if required:
        raise AssertionError("wanted %s, saw %s" % (names, seen))
    return False


def _tab_until_acc(walk: _Walk, needle: str, limit: int = 24) -> bool:
    for _ in range(limit):
        focus = _focus(walk.qapp)
        acc = focus.accessibleName() if focus is not None else ""
        if needle in acc or needle in _focus_name(focus):
            return True
        walk.kb.press("Key_Tab")
    return False


def _land(walk: _Walk, name: str) -> None:
    if _focus_name(_focus(walk.qapp)) == name:
        return
    for _ in range(16):
        walk.kb.press("Key_Tab", "Shift")
        if _focus_name(_focus(walk.qapp)) == name:
            return
    for _ in range(24):
        walk.kb.press("Key_Tab")
        if _focus_name(_focus(walk.qapp)) == name:
            return
    raise AssertionError("wanted %s, focus %s" % (name, _focus_name(_focus(walk.qapp))))


def _add_check(walk: _Walk, words: str) -> None:
    from app.qt.QtWidgets import QApplication, QMenu

    _land(walk, "formBuilder.checks.add")
    walk.kb.press("Key_Down")
    walk.kb.pump()
    menu = QApplication.activePopupWidget()
    if not isinstance(menu, QMenu):
        raise AssertionError("add-check menu did not open, focus %s" % _focus_name(_focus(walk.qapp)))
    for _ in range(12):
        active = menu.activeAction()
        text = active.text() if active is not None else ""
        if text == words:
            walk.kb.press("Key_Return")
            walk.kb.pump()
            return
        walk.kb.press("Key_Down")
        menu = QApplication.activePopupWidget()
        if not isinstance(menu, QMenu):
            break
    raise AssertionError("check %s not in the menu" % words)


def _add_call(walk: _Walk) -> None:
    if _has_call(walk, "save_invoice"):
        return
    _ensure_form(walk)
    _open_clicked(walk)
    _pick_row(walk, "save", "Call save_invoice")


def _add_then(walk: _Walk, typed: str, wanted: str) -> None:
    _ensure_form(walk)
    if not _event_open(walk):
        _open_clicked(walk)
    else:
        walk.kb.press("Key_B", "Alt")
        walk.kb.pump()
        if not _focus_then(walk):
            walk.confuse("Alt+B did not reach + Then…. Focus is %s." % _focus_name(_focus(walk.qapp)))
            return
    _pick_row(walk, typed, wanted)
    page = _child(walk, "formBuilder.checks.page")
    verb = _child(walk, "formBuilder.eventPicker")
    if verb is not None and verb.isVisible():
        walk.kb.press("Key_Return")
        walk.kb.pump()
    del page


def _open_clicked(walk: _Walk) -> None:
    walk.kb.press("Key_E", "Control", "Shift")
    walk.kb.pump()
    walk.kb.press("Key_Return")
    walk.kb.pump()


def _focus_then(walk: _Walk) -> bool:
    for _ in range(16):
        focus = _focus(walk.qapp)
        text = ""
        if focus is not None and hasattr(focus, "text"):
            try:
                text = str(focus.text())
            except Exception:
                text = ""
        acc = focus.accessibleName() if focus is not None else ""
        if "Then" in text or "Then" in acc:
            walk.kb.press("Key_Return")
            walk.kb.pump()
            return True
        walk.kb.press("Key_Down")
    return False


def _event_open(walk: _Walk) -> bool:
    return _has_call(walk, "save_invoice") or bool(_save_steps(walk))


def _pick_row(walk: _Walk, typed: str, wanted: str) -> None:
    walk.kb.type(typed)
    walk.kb.pump()
    for _ in range(12):
        current = _picker_current(walk)
        if wanted in current:
            walk.kb.press("Key_Return")
            walk.kb.pump()
            if _picker_current(walk) and wanted not in _picker_current(walk):
                return
            if _child_visible(walk, "formBuilder.eventPicker") is False:
                return
            walk.kb.press("Key_Return")
            walk.kb.pump()
            return
        walk.kb.press("Key_Down")
    walk.confuse("The step list has no %r. The highlighted row was %r." % (wanted, _picker_current(walk)))
    walk.kb.press("Key_Escape")


def _ensure_form(walk: _Walk) -> None:
    name = _focus_name(_focus(walk.qapp))
    if not name.startswith("shell.editor"):
        return
    status = _status(walk.window)
    walk.confuse("That key opened the code editor. The screen says %r." % status[:220])
    _back(walk, "invoice.ui")
    walk.kb.pump()


def _write_code(walk: _Walk) -> None:
    from app.qt.QtWidgets import QApplication, QMenu

    walk.kb.press("Key_F10", "Shift")
    walk.kb.pump()
    menu = QApplication.activePopupWidget()
    if not isinstance(menu, QMenu):
        walk.confuse("Shift+F10 on Save did not open a menu. Focus %s." % _focus_name(_focus(walk.qapp)))
        _add_call(walk)
        return
    chosen = False
    for _ in range(16):
        current = menu.activeAction()
        text = current.text() if current is not None else ""
        if text.startswith("Write code"):
            chosen = True
            break
        walk.kb.press("Key_Down")
        menu = QApplication.activePopupWidget()
        if not isinstance(menu, QMenu):
            break
    if not chosen:
        walk.confuse("Save's menu has no Write code. The developer would not find the stub from the keyboard.")
        walk.kb.press("Key_Escape")
        _add_call(walk)
        return
    walk.kb.press("Key_Return")
    walk.kb.pump(8)
    if _focus_name(_focus(walk.qapp)) == "formBuilder.eventPickerMethod":
        walk.kb.press("Key_Return")
        walk.kb.pump(8)


def _menu_choose(walk: _Walk, prefix: str) -> bool:
    if not _menu_arm(walk, prefix):
        return False
    walk.kb.press("Key_Return")
    walk.kb.pump()
    return True


def _menu_arm(walk: _Walk, prefix: str) -> bool:
    from app.qt.QtWidgets import QApplication, QMenu

    menu = QApplication.activePopupWidget()
    if not isinstance(menu, QMenu):
        return False
    for _ in range(8):
        current = menu.activeAction()
        text = current.text() if current is not None else ""
        if text.startswith(prefix):
            return True
        walk.kb.press("Key_Down")
        menu = QApplication.activePopupWidget()
        if not isinstance(menu, QMenu):
            return False
    return False


def _drive_rename(walk: _Walk) -> str:
    """Rename Symbol is QInputDialog.getText, so it runs a nested event loop.

    The walk script is inside that loop until every box closes. A timer fills
    the name and animateClick()s each box, which returns before the next box opens.
    """
    from app.qt.QtCore import QTimer
    from app.qt.QtTest import QTest
    from app.qt.QtWidgets import QApplication, QLineEdit, QMessageBox, QPushButton

    state = {"phase": "name", "note": "", "idle": 0, "shot": False, "finished": False}
    seen: set = set()
    trace = _OUT / "rename_trace.txt"

    def _trace(line: str) -> None:
        _OUT.mkdir(parents=True, exist_ok=True)
        with trace.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def _press(button: object) -> None:
        button.animateClick()  # type: ignore[attr-defined]

    def _ok(dialog: object):
        for button in dialog.findChildren(QPushButton):  # type: ignore[attr-defined]
            label = button.text().replace("&", "")
            if label in ("OK", "Ok"):
                return button
        return None

    def tick() -> None:
        try:
            _tick()
        except Exception as exc:
            _trace("tick %s: %s" % (type(exc).__name__, exc))
            state["note"] = "Rename driver failed: %s" % exc
            state["phase"] = "done"
            modal = QApplication.activeModalWidget()
            if modal is not None:
                modal.reject()

    def _tick() -> None:
        if state["phase"] == "done":
            return
        modal = QApplication.activeModalWidget()
        edit = modal.findChild(QLineEdit) if modal is not None else None
        if state["phase"] == "name":
            if edit is None:
                state["idle"] += 1
                if state["idle"] > 50:
                    state["note"] = "Rename did not ask for the new name."
                    state["phase"] = "done"
                return
            edit.setText("save_and_close")
            button = _ok(modal)
            if button is None:
                state["note"] = "Rename Symbol has no OK button."
                state["phase"] = "done"
                return
            state["phase"] = "preview"
            state["idle"] = 0
            _trace("typed save_and_close, button %r" % button.text())
            _press(button)
            return
        extras = [
            widget
            for widget in QApplication.allWidgets()
            if widget is not walk.window and widget.isVisible() and widget.isWindow()
        ]
        if state["idle"] in (25, 100):
            _trace(
                "waiting idle=%s extras=%s"
                % (state["idle"], ["%s %r" % (type(widget).__name__, widget.windowTitle()) for widget in extras])
            )
        box = modal if isinstance(modal, QMessageBox) else None
        if box is None:
            for widget in extras:
                if isinstance(widget, QMessageBox):
                    box = widget
                    break
        if box is None:
            state["idle"] += 1
            if state["finished"] and state["idle"] > 15:
                state["phase"] = "done"
            elif state["shot"] and state["idle"] > 40:
                state["phase"] = "done"
            elif state["idle"] > 800:
                state["note"] = state["note"] or "No rename preview appeared."
                state["phase"] = "done"
            return
        if id(box) in seen:
            state["idle"] += 1
            if state["idle"] > 40:
                box.done(0)
                state["note"] = state["note"] or ("Rename left %r open." % box.windowTitle())
                state["phase"] = "done"
            return
        seen.add(id(box))
        state["idle"] = 0
        title = str(box.windowTitle())
        blob = _blob(box)
        _trace("box %r %s" % (title, blob[:300].replace("\n", " | ")))
        preview = "Preview" in title or "Occurrences:" in blob
        if preview and not state["shot"]:
            if "save_and_close" not in blob:
                state["note"] = "After the name, the dialog is %r: %s" % (title, blob[:240])
            _grab(walk.window, "%s-rename-preview" % walk.persona)
            state["shot"] = True
        elif "Renamed " in blob:
            state["shot"] = state["shot"] or False
            state["finished"] = True
        elif not state["shot"]:
            state["note"] = "No rename preview. %s: %s" % (title, blob[:240])
        button = box.defaultButton() if hasattr(box, "defaultButton") else None
        if button is None and hasattr(box, "buttons") and box.buttons():
            button = box.buttons()[0]
        if button is not None:
            _press(button)

    timer = QTimer(walk.window)
    timer.timeout.connect(tick)
    timer.start(40)
    walk.window._rename_timer = timer  # type: ignore[attr-defined]
    walk.kb.press("Key_Return")
    waited = 0
    while state["phase"] != "done" and waited < 800:
        QTest.qWait(50)
        waited += 1
    timer.stop()
    if state["phase"] != "done":
        return "Rename dialogs did not finish (%s)." % state["phase"]
    return str(state["note"])


def _back(walk: _Walk, name: str) -> None:
    walk.kb.press("Key_P", "Control")
    walk.kb.type(name)
    walk.kb.press("Key_Return")
    walk.kb.pump(12)


def _save_current(walk: _Walk) -> None:
    _back(walk, "invoice.ui")
    walk.kb.press("Key_S", "Control")
    walk.kb.pump(12)
    tree = getattr(walk.window, "_project_tree_ui_workflow", None)
    refresh = getattr(tree, "refresh_project_tree_from_disk", None)
    if callable(refresh):
        refresh()
    walk.kb.pump(4)


def _key_widget(walk: _Walk, name: str, key: str) -> None:
    from app.qt.QtWidgets import QApplication, QWidget

    host = None
    for widget in QApplication.topLevelWidgets():
        if widget is walk.window or not widget.isVisible():
            continue
        found = widget.findChild(QWidget, name)
        if found is not None and found.isVisible():
            host = found
            break
    if host is None:
        walk.confuse("Try mode has no %s to press." % name)
        return
    host.setFocus()
    walk.kb.press(key)


def _has_call(walk: _Walk, method: str) -> bool:
    return any(item == "call:%s" % method for item in _save_steps(walk))


def _save_steps(walk: _Walk) -> List[str]:
    from app.features.form_builder.engine.logic.events import read_events

    found = []
    for state in read_events(walk.kb.session.document):
        if state.sender != "saveButton":
            continue
        for step in state.steps:
            if step.verb == "call":
                found.append("call:%s" % step.method)
            else:
                found.append(step.verb)
    return found


def _prop(walk: _Walk, name: str, key: str) -> str:
    from app.features.form_builder.engine.ui4.nodes import WidgetNode
    from app.features.form_builder.engine.ui4.values import StringValue

    session = walk.kb.session
    found = session.document.by_name(name)
    if not found:
        return ""
    node = session.document.node(found[0])
    if not isinstance(node, WidgetNode):
        return ""
    value = node.value(key)
    if isinstance(value, StringValue):
        return value.text
    return ""


def _native_slots(walk: _Walk) -> str:
    return walk.kb.text()


def _picker_current(walk: _Walk) -> str:
    picker = _named_any(walk, "formBuilder.eventPicker")
    page = getattr(picker, "_page", None) if picker is not None else None
    rows = getattr(page, "rows", None) if page is not None else None
    current = getattr(page, "current", None) if page is not None else None
    if not rows or current is None or current < 0 or current >= len(rows):
        return ""
    return str(rows[current].text)


def _child_visible(walk: _Walk, name: str) -> bool:
    widget = _child(walk, name)
    return bool(widget is not None and widget.isVisible())


def _wait_title(walk: _Walk, prefix: str, rounds: int = 30) -> bool:
    for _ in range(rounds):
        title = _modal_title(walk.qapp)
        if title.startswith(prefix):
            return True
        walk.kb.pump(2)
    return False


def _modal_title(qapp: object) -> str:
    from app.qt.QtWidgets import QApplication

    modal = QApplication.activeModalWidget()
    if modal is None:
        return ""
    return str(modal.windowTitle())


def _modal_text(qapp: object) -> str:
    from app.qt.QtWidgets import QApplication

    modal = QApplication.activeModalWidget()
    return _blob(modal) if modal is not None else ""


def _outline(walk: _Walk) -> str:
    tree = walk.kb.surface.workbench.outline.tree
    index = tree.currentIndex()
    data = index.data() if index.isValid() else ""
    return str(data or "")


def _window_editor(walk: _Walk) -> str:
    from app.qt.QtWidgets import QPlainTextEdit

    for widget in walk.window.findChildren(QPlainTextEdit):
        text = widget.toPlainText()
        if "def save_invoice" in text or "def save_and_close" in text:
            return text
    return ""


def _editor(qapp: object) -> Optional[object]:
    from app.qt.QtWidgets import QApplication

    focus = QApplication.focusWidget()
    if focus is not None and hasattr(focus, "toPlainText"):
        return focus
    return None


def _focus(qapp: object) -> Optional[object]:
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
    return str(parent.objectName() or type(focus).__name__)


def _status(window: object) -> str:
    from app.qt.QtWidgets import QLabel, QWidget

    bar = window.statusBar()
    parts = []
    if bar is not None:
        for widget in bar.findChildren(QLabel):
            if widget.isVisible() and widget.text().strip():
                parts.append("%s=%r" % (widget.objectName(), widget.text()))
    sentence = str(getattr(window, "_gesture_sentence", "") or "")
    surface = getattr(window, "_form_undo_surface", None)
    del surface
    return " | ".join(parts) + (" gesture=%r" % sentence if sentence else "")


def _inspector(kb: object) -> str:
    from app.qt.QtWidgets import QLabel, QWidget

    try:
        pane = kb.pane("formBuilder.inspector")
    except AssertionError:
        return ""
    lines = []
    for widget in pane.findChildren(QWidget):
        if not widget.isVisible():
            continue
        text = widget.text() if isinstance(widget, QLabel) else ""
        acc = widget.accessibleName()
        if text or acc:
            lines.append("%s[%s] %r acc=%r" % (type(widget).__name__, widget.objectName(), text, acc))
        if len(lines) >= 60:
            break
    return "\n".join(lines)


def _dialogs(window: object) -> str:
    from app.qt.QtWidgets import QApplication

    chunks = []
    for widget in QApplication.topLevelWidgets():
        if widget is window or not widget.isVisible():
            continue
        chunks.append("WINDOW %r %s\n%s" % (widget.windowTitle(), widget.objectName(), _blob(widget)))
    return "\n".join(chunks)


def _user_text(walk: _Walk) -> str:
    from app.qt.QtWidgets import QAbstractButton, QLabel, QWidget

    chunks = [_status(walk.window)]
    try:
        pane = walk.kb.pane("formBuilder.inspector")
    except AssertionError:
        pane = None
    roots = []  # type: List[QWidget]
    if isinstance(pane, QWidget):
        roots.append(pane)
    from app.qt.QtWidgets import QApplication

    for widget in QApplication.topLevelWidgets():
        if widget is not walk.window and widget.isVisible():
            roots.append(widget)
    for root in roots:
        for widget in list(root.findChildren(QLabel)) + list(root.findChildren(QAbstractButton)):
            if widget.isVisible() and widget.text().strip():
                chunks.append(widget.text())
    return "\n".join(chunks)


def _blob(root: Optional[object]) -> str:
    from app.qt.QtWidgets import QLabel, QAbstractButton

    if root is None:
        return ""
    lines = []
    from app.qt.QtWidgets import QWidget

    widgets = list(root.findChildren(QLabel)) + list(root.findChildren(QAbstractButton))  # type: ignore[attr-defined]
    widgets.extend(root.findChildren(QWidget))  # type: ignore[attr-defined]
    seen = set()
    for widget in widgets:
        if not widget.isVisible() or id(widget) in seen:
            continue
        seen.add(id(widget))
        text = widget.text() if hasattr(widget, "text") else ""
        try:
            text = str(text or "")
        except Exception:
            text = ""
        if text.strip():
            lines.append(text.replace("\n", " "))
    return "\n".join(lines)


def _child(walk: _Walk, name: str) -> Optional[object]:
    from app.qt.QtWidgets import QApplication, QWidget

    found = walk.window.findChild(QWidget, name)
    if found is not None:
        return found
    for widget in QApplication.topLevelWidgets():
        match = widget.findChild(QWidget, name)
        if match is not None:
            return match
    return None


def _named_any(walk: _Walk, name: str) -> Optional[object]:
    return _child(walk, name)


def _grab(window: object, name: str) -> None:
    """Grab without processEvents. Safe from a timer inside a modal event loop."""
    from app.qt.QtCore import QPoint
    from app.qt.QtGui import QPainter
    from app.qt.QtWidgets import QApplication

    _OUT.mkdir(parents=True, exist_ok=True)
    image = window.grab()  # type: ignore[attr-defined]
    painter = QPainter(image)
    origin = window.mapToGlobal(QPoint(0, 0))  # type: ignore[attr-defined]
    extra = QApplication.activeModalWidget() or QApplication.activePopupWidget()
    if extra is not None and extra is not window and extra.isVisible() and extra.width() >= 30:
        corner = extra.mapToGlobal(QPoint(0, 0)) - origin
        painter.drawPixmap(corner, extra.grab())
    painter.end()
    image.save(str(_OUT / ("%s.png" % name)))


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
    if (
        extra is not None
        and extra is not window
        and extra.isVisible()
        and extra.width() >= 30
    ):
        corner = extra.mapToGlobal(QPoint(0, 0)) - origin
        painter.drawPixmap(corner, extra.grab())
    painter.end()
    image.save(str(_OUT / ("%s.png" % name)))


def _indent(text: str) -> str:
    if not text:
        return "    (empty)"
    return "\n".join("    " + line for line in text.splitlines())
