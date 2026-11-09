# pyright: reportAttributeAccessIssue=false
"""Prove a form-builder lane can build a widget on the active runtime."""
from __future__ import annotations

import os


def test_pyside6_offscreen_app_boots(qapp):  # type: ignore[no-untyped-def]
    from app.qt.QtWidgets import QLabel
    from app.qt.qt_compat import IS_QT6

    assert os.environ.get("QT_QPA_PLATFORM") == "offscreen"
    assert IS_QT6
    assert qapp is not None
    label = QLabel("form-builder lane")
    assert label.text() == "form-builder lane"
