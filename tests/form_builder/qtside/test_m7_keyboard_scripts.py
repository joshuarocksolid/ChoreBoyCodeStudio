# pyright: reportAttributeAccessIssue=false
"""K27, K28, K29 and K30 back to back on one main window. Keys only."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.qt.QtWidgets import QApplication  # noqa: E402
from app.shell.main_window import MainWindow  # noqa: E402
from tests.form_builder.qtside.test_m3_keyboard_scripts import (  # noqa: E402
    Kb,
    _NoMouse,
    _close,
    _open,
    _project,
    _require,
)
from tests.form_builder.qtside.test_m7_2b1_k27 import _FORM, script_k27  # noqa: E402
from tests.form_builder.qtside.test_m7_3b_k28 import EMAIL_FORM, script_k28  # noqa: E402
from tests.form_builder.qtside.test_m7_4_k29 import _SALE, script_k29  # noqa: E402
from tests.form_builder.qtside.test_m7_5_k30 import (  # noqa: E402
    _INVOICE,
    script_k30_condition,
    script_k30_value,
)

pytestmark = [pytest.mark.unit, pytest.mark.timeout(300)]


def _on(window: MainWindow, qapp: QApplication, root: Path, name: str, text: str) -> Kb:
    path = root / "forms" / name
    surface = _open(window, qapp, path, text)
    kb = Kb(window, qapp, surface, path)
    surface.focus_primary()  # type: ignore[attr-defined]
    kb.pump()
    return kb


def _away(window: MainWindow, qapp: QApplication, path: Path) -> None:
    """Close that form and drop its widgets before the next script.

    K29 and K30 call ``window.findChild``. A closed tab stays reachable until
    Qt delivers DeferredDelete, so the next script would bind the previous form.
    """
    from app.qt.QtCore import QEvent
    from app.qt.QtWidgets import QWidget

    window._editor_tab_workflow.close_tab_discarding_edits(str(path))  # noqa: SLF001
    types = getattr(QEvent, "Type", QEvent)
    kind = int(getattr(types, "DeferredDelete"))
    for _ in range(8):
        QApplication.sendPostedEvents(None, kind)
        qapp.processEvents()
    assert window.findChildren(QWidget, "formBuilder.events") == []


def test_k27_k28_k29_k30_together(tmp_path: Path, qapp: QApplication) -> None:
    _require()
    if sys.platform == "darwin":
        from app.qt.QtGui import qt_set_sequence_auto_mnemonic

        qt_set_sequence_auto_mnemonic(True)
    root = tmp_path / "shop"
    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    _project(window, root)
    guard = _NoMouse()
    qapp.installEventFilter(guard)
    try:
        discount = _on(window, qapp, root, "discount.ui", _FORM)
        script_k27(discount)
        _away(window, qapp, discount.path)

        mail = _on(window, qapp, root, "mail.ui", EMAIL_FORM)
        script_k28(mail)
        _away(window, qapp, mail.path)

        sale = _on(window, qapp, root, "sale.ui", _SALE)
        script_k29(sale)
        _away(window, qapp, sale.path)

        discount = _on(window, qapp, root, "discount.ui", _FORM)
        script_k30_condition(discount)
        _away(window, qapp, discount.path)

        invoice = _on(window, qapp, root, "invoice.ui", _INVOICE)
        script_k30_value(invoice)
        assert guard.seen == []
    finally:
        _close(window, qapp, guard)
        if sys.platform == "darwin":
            from app.qt.QtGui import qt_set_sequence_auto_mnemonic

            qt_set_sequence_auto_mnemonic(False)
