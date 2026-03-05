"""Runtime-parity smoke for QUiLoader loading `.ui` fixtures via AppRun."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess

import pytest

from app.core import constants

pytestmark = pytest.mark.runtime_parity


def _require_apprun() -> str:
    app_run = Path(constants.APP_RUN_PATH)
    if not app_run.exists():
        pytest.skip(f"AppRun not available at {app_run}; skipping QUiLoader runtime parity smoke.")
    if not os.access(str(app_run), os.X_OK):
        pytest.skip(f"AppRun exists but is not executable at {app_run}; skipping QUiLoader runtime parity smoke.")
    return str(app_run.resolve())


def test_apprun_quiloader_loads_designer_fixture() -> None:
    """AppRun runtime should load Designer fixture through QtUiTools.QUiLoader."""
    app_run = _require_apprun()
    fixture_path = (Path(__file__).resolve().parents[1] / "fixtures" / "designer" / "layout_form.ui").resolve()
    payload = (
        "from PySide2.QtCore import QFile,QIODevice;"
        "from PySide2.QtUiTools import QUiLoader;"
        "from PySide2.QtWidgets import QApplication,QTabWidget;"
        "app=QApplication.instance() or QApplication([]);"
        "loader=QUiLoader();"
        f"f=QFile({str(fixture_path)!r});"
        "assert f.open(QIODevice.ReadOnly), 'fixture-open-failed';"
        "w=loader.load(f,None);"
        "f.close();"
        "assert w is not None, 'loader-returned-none';"
        "assert w.objectName()=='LayoutForm', 'unexpected-root';"
        "tab=w.findChild(QTabWidget, 'tabWidget');"
        "assert tab is not None, 'missing-tab-widget';"
        "print('DESIGNER_RUNTIME_PARITY_OK')"
    )
    env = os.environ.copy()
    env.setdefault("QT_QPA_PLATFORM", "offscreen")

    completed = subprocess.run(
        [app_run, "-c", payload],
        capture_output=True,
        text=True,
        timeout=25,
        check=False,
        env=env,
    )

    if completed.returncode != 0:
        pytest.fail(
            "QUiLoader runtime parity probe failed:\n"
            f"exit={completed.returncode}\n"
            f"stdout={completed.stdout}\n"
            f"stderr={completed.stderr}"
        )

    assert "DESIGNER_RUNTIME_PARITY_OK" in completed.stdout
