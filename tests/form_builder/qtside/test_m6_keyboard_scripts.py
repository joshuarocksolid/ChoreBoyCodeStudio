# pyright: reportAttributeAccessIssue=false
"""K24, K25 and K26 back to back on one sale.ui session. Keys only."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.qt.QtWidgets import QApplication  # noqa: E402
from tests.form_builder.qtside.m6_keyboard import script_k24, script_k25, script_k26  # noqa: E402
from tests.form_builder.qtside.test_m6_2b_k26 import _close, _session  # noqa: E402

pytestmark = [pytest.mark.unit, pytest.mark.timeout(300)]


def test_k24_k25_k26_together(tmp_path: Path, qapp: QApplication) -> None:
    window, kb, guard, path = _session(tmp_path, qapp)
    try:
        script_k24(kb)
        script_k25(kb)
        script_k26(window, kb, qapp, path)
        kb.done(guard)
    finally:
        _close(window, qapp, guard)
        if sys.platform == "darwin":
            from app.qt.QtGui import qt_set_sequence_auto_mnemonic

            qt_set_sequence_auto_mnemonic(False)
