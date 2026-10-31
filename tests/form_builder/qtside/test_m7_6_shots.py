# pyright: reportAttributeAccessIssue=false
"""Preview with What ran and Window values, four themes at 100% and 200%.

Skips unless CBCS_FB_SCREENSHOT_DIR is set (UX §13.4.9).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.core import constants
from app.features.form_builder.engine.ipc.protocol import SourceRef
from app.features.form_builder.integration.chrome import chrome_for
from app.features.form_builder.qtside.preview.try_log import TryLine
from app.features.form_builder.qtside.preview.what_ran import TryChrome
from app.qt.QtWidgets import QApplication, QLabel, QWidget
from app.shell.theme_tokens import tokens_from_palette

pytestmark = pytest.mark.unit

_MODES = (
    constants.UI_THEME_MODE_LIGHT,
    constants.UI_THEME_MODE_DARK,
    constants.UI_THEME_MODE_HIGH_CONTRAST_LIGHT,
    constants.UI_THEME_MODE_HIGH_CONTRAST_DARK,
)


def _shell(qapp: QApplication) -> QWidget:
    shell = TryChrome()
    label = QLabel("Invoice", shell)
    label.setObjectName("preview.sample")
    shell.adopt(label)
    shell.values.set_methods((("note", "str"), ("ready", "bool")), {"ready": True})
    shell.what_ran.add(
        (
            TryLine(
                "Rules ran (2)",
                "discountEdit:cbcsEnabledWhen",
                SourceRef(object_name="discountEdit", rule_path=("cbcsEnabledWhen",)),
                "rule",
            ),
            TryLine(
                "Would call save_invoice()",
                "saveButton: When clicked",
                SourceRef(object_name="saveButton", rule_path=("cbcsOnClicked", 1)),
                "would_call",
                "save_invoice",
            ),
        ),
        1_700_000_000_000,
    )
    shell.resize(780, 480)
    shell.show()
    qapp.processEvents()
    return shell


def _shoot(qapp: QApplication, folder: Path, scale: str) -> None:
    shell = _shell(qapp)
    try:
        for mode in _MODES:
            tokens = tokens_from_palette(qapp.palette(), force_mode=mode)
            shell.apply_chrome(chrome_for(tokens))
            qapp.processEvents()
            path = folder / ("preview-what-ran-%s-%s.png" % (mode, scale))
            path.parent.mkdir(parents=True, exist_ok=True)
            shell.grab().save(str(path))
    finally:
        shell.hide()
        shell.deleteLater()
        qapp.processEvents()


@pytest.mark.timeout(120)
def test_m7_6_preview_shots(qapp: QApplication) -> None:
    raw = os.environ.get("CBCS_FB_SCREENSHOT_DIR") or ""
    if not raw:
        pytest.skip("CBCS_FB_SCREENSHOT_DIR is not set")
    folder = Path(raw)
    folder.mkdir(parents=True, exist_ok=True)
    if os.environ.get("CBCS_FB_SHOT_CHILD") == "1":
        _shoot(qapp, folder, "200")
        return
    _shoot(qapp, folder, "100")
    env = os.environ.copy()
    env["QT_SCALE_FACTOR"] = "2"
    env["CBCS_FB_SHOT_CHILD"] = "1"
    env["CBCS_FB_SCREENSHOT_DIR"] = str(folder)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    env["PYTHONNOUSERSITE"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    env["CBCS_DISABLE_BACKGROUND_RUNTIME"] = "1"
    done = subprocess.run(
        [
            sys.executable,
            "-s",
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            "--import-mode=importlib",
            "-q",
            str(Path(__file__).resolve()),
            "-k",
            "test_m7_6_preview_shots",
        ],
        cwd=str(Path(__file__).resolve().parents[3]),
        env=env,
        capture_output=True,
        text=True,
    )
    text = done.stdout + "\n" + done.stderr
    passed = "passed" in text and "failed" not in text
    assert done.returncode == 0 or (done.returncode in (-11, 139) and passed), text
