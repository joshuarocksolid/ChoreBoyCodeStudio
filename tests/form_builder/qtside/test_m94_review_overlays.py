# pyright: reportAttributeAccessIssue=false
"""Buddy links and bind chips redraw when their own properties change."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.features.form_builder.engine.commands.catalog import SetLogic
from app.features.form_builder.engine.query import tab_stops as q
from app.features.form_builder.qtside.canvas.core.frame import Chip
from app.qt.QtWidgets import QApplication
from tests.form_builder.qtside.test_m3_keyboard_scripts import Kb
from tests.form_builder.qtside.test_m5_6_modes import _close, _layer_items, _open

pytestmark = [pytest.mark.unit, pytest.mark.timeout(300)]


def _links(kb: Kb) -> list:
    return [item for item in _layer_items(kb, "buddies") if item.data[0] == "link"]


def test_buddy_link_appears_and_clears_on_undo(tmp_path: Path, qapp: QApplication) -> None:
    window, kb, guard = _open(tmp_path, qapp)
    try:
        modes = kb.surface.modes
        document = kb.session.document
        modes.open("buddies")
        kb.pump()
        before = _links(kb)
        modes.set_buddy(document.by_name("emailLabel")[0], "emailEdit")
        assert len(_links(kb)) == len(before) + 1
        kb.session.log.undo()
        kb.pump()
        assert q.buddy_of(document, document.by_name("emailLabel")[0]) is None
        assert len(_links(kb)) == len(before)
    finally:
        _close(window, qapp, guard)


def test_bind_chip_appears_when_the_column_is_set(tmp_path: Path, qapp: QApplication) -> None:
    window, kb, guard = _open(tmp_path, qapp)
    try:
        canvas = kb.surface.workbench.canvas
        document = kb.session.document
        canvas.show_layer("bind_chips", True)
        kb.pump()
        before = [item for item in canvas.overlay().items if isinstance(item, Chip) and item.text == "email"]
        kb.session.log.execute(SetLogic(document.by_name("emailEdit")[0], "cbcsBind", "email"))
        kb.pump()
        after = [item for item in canvas.overlay().items if isinstance(item, Chip) and item.text == "email"]
        assert len(after) == len(before) + 1
    finally:
        _close(window, qapp, guard)
