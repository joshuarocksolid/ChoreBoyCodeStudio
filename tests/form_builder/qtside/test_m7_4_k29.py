# pyright: reportAttributeAccessIssue=false
"""K29 (UX_SPEC 13.4) and light verb-page screenshots."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.core import constants  # noqa: E402
from app.features.form_builder.integration.chrome import chrome_for  # noqa: E402
from app.features.form_builder.qtside.pickers.popover import EventPicker  # noqa: E402
from app.qt.QtCore import QTimer  # noqa: E402
from app.qt.QtWidgets import QApplication, QWidget  # noqa: E402
from app.shell.theme_tokens import tokens_from_palette  # noqa: E402
from tests.form_builder.qtside.test_m3_keyboard_scripts import Kb, _close, _session  # noqa: E402
from tests.form_builder.qtside.test_m7_0s_picker import _sale_context  # noqa: E402

pytestmark = [pytest.mark.unit, pytest.mark.timeout(300)]

_SALE = (Path(__file__).resolve().parents[1] / "fixtures" / "m6" / "forms" / "sale.ui").read_text(encoding="utf-8")
_VERBS = (
    "validate",
    "set",
    "clear",
    "focus",
    "enable",
    "disable",
    "show",
    "hide",
    "message",
    "ask",
    "stop",
    "page",
    "openForm",
    "close",
)


def test_k29_save_checks_then_shows_a_message_only_if(tmp_path: Path, qapp: QApplication) -> None:
    window, kb, guard = _session(tmp_path, qapp, _SALE)
    try:
        script_k29(kb)
    finally:
        qapp.removeEventFilter(guard)
        _close(window, qapp, guard)


def _spoken(kb: Kb) -> str:
    focus = kb.focus()
    assert focus is not None
    return focus.accessibleName() or ""


def script_k29(kb: Kb) -> None:
    """K29 on an open sale form. Keys only."""
    kb.press("Key_R", "Control")
    kb.type("saveButton")
    kb.press("Key_Return")
    kb.check(kb.selected() == ("saveButton",), "selected saveButton, have %s" % (kb.selected(),))
    kb.press("Key_E", "Control", "Shift")
    kb.press("Key_Return")
    kb.type("accept")
    kb.press("Key_Return")
    kb.check("Accept" in _spoken(kb), "accept is focused, have %s" % kb.focus_name())
    kb.press("Key_Down")
    kb.press("Key_Return")
    kb.type("check all")
    kb.press("Key_Return")
    kb.press("Key_Return")
    kb.check("Check all fields" in _spoken(kb), "check all is focused")
    kb.press("Key_Up", "Alt")
    spoken = _spoken(kb)
    kb.check("step 1 of 2" in spoken and "Check all fields" in spoken, "check all is first, have %s" % spoken)
    kb.press("Key_Down")
    kb.press("Key_Down")
    kb.press("Key_Return")
    kb.type("show a message")
    kb.press("Key_Return")
    kb.type("Saved.")
    kb.press("Key_Return")
    kb.check("Show a message" in _spoken(kb), "message is focused")

    tries = {"fill": 0, "menu": 0}

    def fill() -> None:
        from app.qt.QtWidgets import QLineEdit

        edit = QApplication.focusWidget()
        if edit is None or edit.objectName() != "formBuilder.onlyIf":
            edit = None
            for widget in QApplication.topLevelWidgets():
                found = widget.findChild(QLineEdit, "formBuilder.onlyIf")
                if found is not None:
                    edit = found
                    break
        if edit is None:
            tries["fill"] += 1
            if tries["fill"] < 40:
                QTimer.singleShot(0, fill)
            return
        edit.setText("discountCheck")
        edit.returnPressed.emit()

    def open_only_if() -> None:
        from app.qt.QtWidgets import QMenu

        popup = QApplication.activePopupWidget()
        if not isinstance(popup, QMenu) or not popup.actions():
            tries["menu"] += 1
            if tries["menu"] < 40:
                QTimer.singleShot(0, open_only_if)
            return
        popup.actions()[0].trigger()

    QTimer.singleShot(0, fill)
    QTimer.singleShot(0, open_only_if)
    kb.press("Key_F10", "Shift")
    text = kb.text()
    kb.check("cbcsOnClicked" in text and "validate" in text and "message" in text, "the list is on the button")
    kb.check(text.find("validate") < text.find("message"), "check all is before the message")
    kb.check("discountCheck" in text, "the only-if condition is stored")


def test_verb_pages_screenshot_light_100(qapp: QApplication) -> None:
    folder = os.environ.get("CBCS_FB_SCREENSHOT_DIR", "").strip()
    if not folder:
        pytest.skip("CBCS_FB_SCREENSHOT_DIR is unset")
    from app.features.form_builder.qtside.pickers.flow import _step_page
    from app.features.form_builder.qtside.pickers.verb_pages import page_for

    app = QApplication.instance()
    assert app is not None
    tokens = tokens_from_palette(app.palette(), force_mode=constants.UI_THEME_MODE_LIGHT)
    chrome = chrome_for(tokens)
    host = QWidget()
    host.resize(480, 360)
    host.show()
    dest = Path(folder)
    dest.mkdir(parents=True, exist_ok=True)
    back = _step_page(_sale_context(), "clicked", False, -1, "")
    for verb in _VERBS:
        picker = EventPicker(host, chrome, lambda gesture: None)
        picker._apply(page_for(back, verb))
        app.processEvents()
        picker.adjustSize()
        app.processEvents()
        picker.grab().save(str(dest / ("verb-%s-light-100.png" % verb)))
        picker.release()
        app.processEvents()
