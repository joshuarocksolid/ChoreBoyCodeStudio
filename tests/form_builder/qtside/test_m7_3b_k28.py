# pyright: reportAttributeAccessIssue=false
"""K28: keys only, from emailEdit to the message under the field."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import cast

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.features.form_builder.engine.ipc.protocol import Appearance, TryStart, encode_frame  # noqa: E402
from app.features.form_builder.engine.logic.checks import Preset, Required, read_checks  # noqa: E402
from app.features.form_builder.engine.ui4.nodes import WidgetNode  # noqa: E402
from app.features.form_builder.engine.ui4.values import StringValue  # noqa: E402
from app.features.form_builder.integration.preview_notice import preview_request  # noqa: E402
from app.features.form_builder.qtside.preview.child.session import ChildSession  # noqa: E402
from app.features.form_builder.qtside.preview.child.stdio import FrameWriter  # noqa: E402
from app.qt.QtTest import QTest  # noqa: E402
from app.qt.QtWidgets import QApplication, QLabel, QLineEdit, QMenu, QWidget  # noqa: E402
from tests.form_builder.qtside.test_m3_keyboard_scripts import (  # noqa: E402
    Kb,
    _NoMouse,
    _close,
    _key,
    _open,
    _project,
    _require,
)
from tests.form_builder.qtside.test_m7_3b_checks import EMAIL_FORM  # noqa: E402

pytestmark = [pytest.mark.unit, pytest.mark.timeout(300)]

_REQUIRED = "Email is required"
_EMAIL = "Enter an email address like name@example.com"


class _Writer:
    def __init__(self) -> None:
        self.sent = []

    def send(self, message: object) -> None:
        self.sent.append(message)


def _session(tmp_path: Path, qapp: QApplication) -> tuple:
    from app.shell.main_window import MainWindow

    _require()
    if sys.platform == "darwin":
        from app.qt.QtGui import qt_set_sequence_auto_mnemonic

        qt_set_sequence_auto_mnemonic(True)
    root = tmp_path / "shop"
    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    _project(window, root)
    path = root / "forms" / "mail.ui"
    surface = _open(window, qapp, path, EMAIL_FORM)
    guard = _NoMouse()
    qapp.installEventFilter(guard)
    kb = Kb(window, qapp, surface, path)
    surface.focus_primary()  # type: ignore[attr-defined]
    kb.pump()
    return window, kb, guard, path


def _land(kb: Kb, name: str) -> None:
    if kb.focus_name() == name:
        return
    seen = [kb.focus_name()]
    # Checks sits above Events, so Alt+B's row is after the add button.
    back = 0
    for _ in range(12):
        kb.press("Key_Tab", "Shift")
        back += 1
        seen.append(kb.focus_name())
        if kb.focus_name() == name:
            return
    for _ in range(back):
        kb.press("Key_Tab")
    for _ in range(24):
        kb.press("Key_Tab")
        seen.append(kb.focus_name())
        if kb.focus_name() == name:
            return
    kb.check(False, "wanted %s, saw %s" % (name, seen))


def _choose(kb: Kb, words: str) -> None:
    kb.press("Key_Down")
    kb.pump()
    menu = QApplication.activePopupWidget()
    kb.check(
        isinstance(menu, QMenu) and menu.objectName() == "formBuilder.checks.menu",
        "the add menu is open (focus %s)" % kb.focus_name(),
    )
    seen = []
    for _ in range(12):
        active = menu.activeAction()
        text = active.text() if active is not None else ""
        seen.append(text)
        if text == words:
            kb.press("Key_Return")
            kb.pump()
            return
        kb.press("Key_Down")
    kb.check(False, "%s not in %s" % (words, seen))


def _checks(kb: Kb) -> tuple:
    session = kb.session
    found = session.document.by_name("emailEdit")  # type: ignore[attr-defined]
    node = session.document.node(found[0])  # type: ignore[attr-defined]
    assert isinstance(node, WidgetNode)
    value = node.value("cbcsValidate")
    assert isinstance(value, StringValue)
    read = read_checks(value.text)
    assert read.error is None
    return read.checks


def _preview(kb: Kb, qapp: QApplication, path: Path) -> None:
    message = preview_request(
        kb.session,
        str(path),
        "v1",
        run_behavior=True,
        appearance=Appearance(title="Preview"),
    )
    assert isinstance(message, TryStart), message
    writer = _Writer()
    child = ChildSession(cast(FrameWriter, writer), qapp)
    before_path = list(sys.path)
    before_modules = dict(sys.modules)
    try:
        child._handle_line(encode_frame(message))  # noqa: SLF001
        qapp.processEvents()
        shell = child._views["v1"].widget  # noqa: SLF001
        field = shell.findChild(QLineEdit, "emailEdit")
        label = shell.findChild(QLabel, "emailEditError")
        assert isinstance(field, QLineEdit)
        assert isinstance(label, QLabel)
        # A blank line edit that was never edited is not a failure. Type, then
        # erase, so the field is empty and the check runs on Tab.
        field.setFocus()
        QTest.keyClick(field, _key("Key_A"))  # type: ignore[arg-type]
        QTest.keyClick(field, _key("Key_Backspace"))  # type: ignore[arg-type]
        qapp.processEvents()
        QTest.keyClick(field, _key("Key_Tab"))  # type: ignore[arg-type]
        qapp.processEvents()
        assert label.text() == _REQUIRED
        field.setFocus()
        QTest.keyClicks(field, "not-an-email")
        qapp.processEvents()
        QTest.keyClick(field, _key("Key_Tab"))  # type: ignore[arg-type]
        qapp.processEvents()
        assert label.text() == _EMAIL
    finally:
        for view_id in list(child._views):  # noqa: SLF001
            widget = child._views.pop(view_id).widget  # noqa: SLF001
            widget.hide()
            widget.deleteLater()
        qapp.processEvents()
        qapp.removeEventFilter(child._user_close)  # noqa: SLF001
        sys.path[:] = before_path
        for name in list(sys.modules):
            if name not in before_modules:
                sys.modules.pop(name, None)
        for name, module in before_modules.items():
            sys.modules[name] = module


def test_k28_required_then_email_shows_under_the_field(tmp_path: Path, qapp: QApplication) -> None:
    window, kb, guard, path = _session(tmp_path, qapp)
    try:
        kb.press("Key_R", "Control")
        kb.type("emailEdit")
        kb.press("Key_Return")
        kb.pump()
        kb.check(kb.selected() == ("emailEdit",), "emailEdit is selected")
        kb.press("Key_B", "Alt")
        kb.pump()
        _land(kb, "formBuilder.checks.add")
        _choose(kb, "Required")
        page = kb.pane("formBuilder.checks.page")
        kb.check(page.isVisible(), "the Required page is open")
        kb.press("Key_Return", "Control")
        kb.pump()
        offer = kb.pane("formBuilder.checks.offer")
        kb.check(offer.isVisible(), "the label offer is open")
        _land(kb, "formBuilder.checks.addLabel")
        kb.press("Key_Return")
        kb.pump()
        kb.check(not offer.isVisible(), "Add label closed the offer")
        _land(kb, "formBuilder.checks.add")
        _choose(kb, "Email address")
        kb.check(kb.pane("formBuilder.checks.page").isVisible(), "the Email page is open")
        kb.press("Key_Return", "Control")
        kb.pump()
        kb.check(_checks(kb) == (Required(None), Preset("email", None)), "both checks are stored")
        kb.press("Key_R", "Control", "Shift")
        kb.pump()
        _preview(kb, qapp, path)
        kb.check(guard.seen == [], "no mouse event reached the window")
    finally:
        _close(window, qapp, guard)
