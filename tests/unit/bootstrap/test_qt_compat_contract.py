"""Contract checks against the one Qt binding this process selected."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


def test_active_binding_contract() -> None:
    from app.qt.qt_compat import QtCore, QtGui, QtWidgets, enum_value, exec_qt

    assert QtWidgets.QAction is QtGui.QAction
    assert isinstance(enum_value(QtCore.Qt.ControlModifier), int)

    if QtWidgets.QApplication.instance() is None:
        QtWidgets.QApplication([])
    dialog = QtWidgets.QDialog()
    timer = QtCore.QTimer(dialog)
    timer.setSingleShot(True)
    timer.timeout.connect(dialog.accept)
    timer.start(0)
    returned = exec_qt(dialog)
    assert returned == dialog.result()
