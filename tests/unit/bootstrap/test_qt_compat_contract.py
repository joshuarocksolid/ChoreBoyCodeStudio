"""Contract checks against the one Qt binding this process selected."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[3]


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

    # Sibling tests may already have imported the other binding in this process.
    # A fresh interpreter shows what importing qt_compat itself loads.
    vendor = _REPO_ROOT / "vendor"
    env = os.environ.copy()
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    entries = [str(_REPO_ROOT), str(vendor)]
    inherited = env.get("PYTHONPATH", "")
    if inherited:
        entries.append(inherited)
    env["PYTHONPATH"] = os.pathsep.join(entries)
    code = (
        "import sys\n"
        "from app.qt.qt_compat import QT_API\n"
        "other = 'PySide2' if QT_API == 'PySide6' else 'PySide6'\n"
        "loaded = [name for name in sys.modules if name == other or name.startswith(other + '.')]\n"
        "assert not loaded, (QT_API, loaded)\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(_REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + "\n" + completed.stderr
