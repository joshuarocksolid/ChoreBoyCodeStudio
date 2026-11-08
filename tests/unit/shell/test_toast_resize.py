"""A dismissed toast must not crash the next resize of its anchor."""

from __future__ import annotations

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.qt.QtCore import QEvent  # noqa: E402
from app.qt.QtWidgets import QApplication, QWidget  # noqa: E402
from app.shell.toast import show_toast  # noqa: E402

pytestmark = pytest.mark.unit


def test_dismissed_toast_survives_an_anchor_resize(qapp) -> None:  # type: ignore[no-untyped-def]
    """deleteLater runs on the deferred-delete pass. The next resize must live.

    processEvents alone leaves that pass queued. The preview pump flushes it,
    and the anchor's resize filter then calls the deleted toast.
    """
    anchor = QWidget()
    anchor.resize(400, 300)
    anchor.show()
    qapp.processEvents()
    toast = show_toast(anchor, "Saved", timeout_ms=60000)
    qapp.processEvents()
    toast.dismiss()
    QApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    anchor.resize(480, 360)
    qapp.processEvents()
    assert anchor.isVisible()
    anchor.close()
