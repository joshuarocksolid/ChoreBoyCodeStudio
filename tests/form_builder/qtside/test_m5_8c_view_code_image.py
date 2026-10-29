# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportOptionalMemberAccess=false
"""M5.8c: View code is readable at 1366 px (screenshots), and Save image writes the page at its logical size on a 200% screen."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.core import constants  # noqa: E402
from app.features.form_builder.integration import image_export  # noqa: E402
from app.features.form_builder.integration.chrome import chrome_for  # noqa: E402
from app.qt.QtGui import QImage, QPalette  # noqa: E402
from app.qt.QtWidgets import QApplication  # noqa: E402
from app.shell.theme_tokens import tokens_from_palette  # noqa: E402
from tests.form_builder.qtside.test_m3_keyboard_scripts import _close, _session  # noqa: E402
from tests.form_builder.qtside.test_m5_5a_k20 import _long_form  # noqa: E402

pytestmark = [pytest.mark.unit, pytest.mark.timeout(300)]

_MODES = {
    "light": constants.UI_THEME_MODE_LIGHT,
    "high_contrast_dark": constants.UI_THEME_MODE_HIGH_CONTRAST_DARK,
}


def test_view_code_shots_at_1366(tmp_path: Path, qapp: QApplication) -> None:
    """Skips unless CBCS_FB_SCREENSHOT_DIR is set: the code split at 1366 x 768 in light and high contrast dark."""
    raw = os.environ.get("CBCS_FB_SCREENSHOT_DIR") or ""
    if not raw:
        pytest.skip("CBCS_FB_SCREENSHOT_DIR is not set")
    folder = Path(raw)
    folder.mkdir(parents=True, exist_ok=True)
    for label, mode in _MODES.items():
        window, kb, guard = _session(tmp_path / label, qapp, _long_form())
        try:
            tokens = tokens_from_palette(QPalette(), force_mode=mode)
            window.show()
            kb.surface.apply_theme(tokens)
            window.resize(1366, 768)
            kb.pump()
            assert kb.surface._workbench.code_view.open()
            kb.pump()
            editor = kb.surface._workbench.code_view.panel.editor
            shown = editor.viewport().width() // editor.fontMetrics().horizontalAdvance("M")
            (folder / ("m58c_view_code_1366_%s.txt" % label)).write_text("characters across: %d\n" % shown)
            qapp.processEvents()
            window.grab().save(str(folder / ("m58c_view_code_1366_%s.png" % label)))
        finally:
            _close(window, qapp, guard)


def test_save_image_is_the_page_at_its_logical_size_on_a_200_percent_screen(tmp_path: Path, qapp: QApplication) -> None:
    if os.environ.get("CBCS_FB_SCALE_CHILD") != "1":
        env = os.environ.copy()
        env["QT_SCALE_FACTOR"] = "2"
        env["CBCS_FB_SCALE_CHILD"] = "1"
        env.setdefault("QT_QPA_PLATFORM", "offscreen")
        env.setdefault("CBCS_DISABLE_BACKGROUND_RUNTIME", "1")
        done = subprocess.run(
            [sys.executable, "-s", "-m", "pytest", "-p", "no:cacheprovider", "--import-mode=importlib", "--timeout", "300", "-q",
             str(Path(__file__).resolve()), "-k", "logical_size"],
            cwd=str(Path(__file__).resolve().parents[3]),
            env=env,
            capture_output=True,
            text=True,
        )
        assert done.returncode == 0, done.stdout + "\n" + done.stderr
        return
    window, kb, guard = _session(tmp_path, qapp, _long_form())
    try:
        page = kb.surface.page_widget()
        assert page.devicePixelRatioF() == 2.0, "the child runs on a 200% screen"
        assert page.grab().width() == page.width() * 2, "QWidget.grab gives device pixels there"
        target = tmp_path / "customer.png"
        image_export.write_image(kb.surface, str(target))
        deadline_ok = target.exists()
        assert deadline_ok
        picture = QImage(str(target))
        assert (picture.width(), picture.height()) == (page.width(), page.height())
    finally:
        _close(window, qapp, guard)
