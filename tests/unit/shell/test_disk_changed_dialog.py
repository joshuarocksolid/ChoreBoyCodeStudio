"""The poll-time prompt for a dirty buffer must not lose the user's text by accident."""

from __future__ import annotations

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.qt.QtCore import Qt  # noqa: E402
from app.qt.QtTest import QTest  # noqa: E402

from app.shell.disk_conflict_dialogs import DiskChangedChoice, DiskChangedDialog  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("key", [Qt.Key_Return, Qt.Key_Escape])
def test_enter_or_escape_keeps_my_version(qapp, key) -> None:  # type: ignore[no-untyped-def]
    dialog = DiskChangedDialog("/tmp/project/report.py", disk_changed_text="changed today 2:41 PM")
    dialog.show()
    qapp.processEvents()

    QTest.keyClick(dialog, key)
    qapp.processEvents()

    assert not dialog.isVisible()
    assert dialog.choice() is DiskChangedChoice.KEEP_MY_VERSION
    dialog.deleteLater()
