"""An Enabled rule on Save follows form.isDirty, including a typed-back value."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.features.form_builder.engine.commands.catalog import SetLogic
from tests.form_builder.engine.test_m8_2_scenario import invoice_ui, record_window, shop_with_three
from tests.support.form_builder.command_fixtures import nid, open_log, saved

pytestmark = pytest.mark.unit


def test_save_enables_on_the_first_keystroke_and_disables_when_typed_back(tmp_path: Path) -> None:
    log = open_log(invoice_ui())
    log.execute(SetLogic(nid(log.document, "saveButton"), "cbcsEnabledWhen", "form.isDirty"))
    text = saved(log.document)
    with record_window(tmp_path, text, shop_with_three) as (host, _db):
        assert host.ui.saveButton.isEnabled() is False
        original = host.ui.notesEdit.text()
        host.ui.notesEdit.setText(original + "x")
        assert host.ui.saveButton.isEnabled() is True
        host.ui.notesEdit.setText(original)
        assert host.ui.saveButton.isEnabled() is False
        host.ui.cbcs_refresh()
        assert host.ui.saveButton.isEnabled() is False
