# pyright: reportAttributeAccessIssue=false
"""Check frames in the run log open the field's Checks row."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.features.form_builder.engine.commands.catalog_ext.checks import SetChecks  # noqa: E402
from app.features.form_builder.engine.logic.checks import Required  # noqa: E402
from app.features.form_builder.integration.run_links_ext.rules import activate, match  # noqa: E402
from app.qt.QtWidgets import QApplication, QWidget  # noqa: E402
from tests.form_builder.qtside.test_m7_3b_k28 import _session  # noqa: E402
from tests.form_builder.qtside.test_m3_keyboard_scripts import _close  # noqa: E402

pytestmark = [pytest.mark.unit, pytest.mark.timeout(300)]


@pytest.mark.parametrize(
    ("line", "target"),
    (
        (
            '  File "forms/ui_mail.py", line 40, in _cbcs_check_emailEdit',
            "widget:emailEdit",
        ),
        (
            '  File "/tmp/forms/ui_customer.py", line 12, in _cbcs_touch_nameEdit',
            "widget:nameEdit",
        ),
        (
            '  File "ui_invoice.py", line 8, in _cbcs_recheck_qtySpin',
            "widget:qtySpin",
        ),
        ("        # emailEdit:cbcsValidate", "widget:emailEdit"),
        ("        # phoneEdit: ", "widget:phoneEdit"),
        ('  File "forms/sale_window.py", line 14, in _cbcs_check_emailEdit', None),
        ("print('emailEdit')", None),
        ("", None),
    ),
)
def test_match_names_the_widget(line: str, target: object) -> None:
    assert match(line) == target


def test_activate_selects_the_widget_and_focuses_its_check(tmp_path: Path, qapp: QApplication) -> None:
    window, kb, guard, _path = _session(tmp_path, qapp)
    try:
        session = kb.session
        owner = session.document.by_name("emailEdit")[0]  # type: ignore[attr-defined]
        session.log.execute(SetChecks(owner, (Required(None),)))  # type: ignore[attr-defined]
        activate("widget:emailEdit")
        kb.pump()
        assert kb.selected() == ("emailEdit",)
        focus = QApplication.focusWidget()
        assert isinstance(focus, QWidget)
        assert focus.objectName() == "formBuilder.checks.row.0"
        assert "Required" in focus.accessibleName()
    finally:
        _close(window, qapp, guard)
