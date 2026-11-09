# pyright: reportAttributeAccessIssue=false
"""Picture editor shots. Skips unless CBCS_FB_SCREENSHOT_DIR is set."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.core import constants
from app.features.form_builder.integration.chrome import chrome_for
from app.qt.QtGui import QPalette
from app.qt.QtWidgets import QApplication, QLabel, QWidget
from app.shell.theme_tokens import tokens_from_palette
from app.features.form_builder.qtside.inspector.editors._picture_picker import PicturePicker
from tests.form_builder.inspector.test_m43c_pictures import (
    _close,
    _fit_row,
    _form,
    _open_row,
    _pane,
    _png_bytes,
    _search,
    _seed,
    _select,
)

pytestmark = pytest.mark.unit

_MODES = (
    constants.UI_THEME_MODE_LIGHT,
    constants.UI_THEME_MODE_DARK,
    constants.UI_THEME_MODE_HIGH_CONTRAST_LIGHT,
    constants.UI_THEME_MODE_HIGH_CONTRAST_DARK,
)


def _grab(qapp: QApplication, widget: QWidget, folder: Path, stem: str) -> None:
    qapp.processEvents()
    widget.grab().save(str(folder / (stem + ".png")))


def _popover(window: QWidget) -> QWidget:
    visible = [
        item
        for item in window.findChildren(QWidget, "formBuilder.rowPopover")
        if item.isVisible()
    ]
    assert visible, "no open row popover"
    return visible[-1]


@pytest.mark.timeout(300)
def test_m43c_shots(qapp: QApplication, tmp_path: Path) -> None:
    raw = os.environ.get("CBCS_FB_SCREENSHOT_DIR") or ""
    if not raw:
        pytest.skip("CBCS_FB_SCREENSHOT_DIR is not set")
    folder = Path(raw)
    folder.mkdir(parents=True, exist_ok=True)
    if os.environ.get("CBCS_FB_SHOT_CHILD") == "1":
        _shoot(qapp, folder, tmp_path, "200")
        return
    _shoot(qapp, folder, tmp_path, "100")
    env = os.environ.copy()
    env["QT_SCALE_FACTOR"] = "2"
    env["CBCS_FB_SHOT_CHILD"] = "1"
    env["CBCS_FB_SCREENSHOT_DIR"] = str(folder)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    env.setdefault("CBCS_DISABLE_BACKGROUND_RUNTIME", "1")
    completed = subprocess.run(
        [
            sys.executable,
            "-s",
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            "--import-mode=importlib",
            "--timeout",
            "300",
            "-q",
            str(Path(__file__).resolve()),
            "-k",
            "test_m43c_shots",
        ],
        cwd=str(Path(__file__).resolve().parents[3]),
        env=env,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + "\n" + completed.stderr


def _shoot(qapp: QApplication, folder: Path, tmp_path: Path, suffix: str) -> None:
    names = tuple("img%02d.png" % index for index in range(30))
    _seed(tmp_path, names + ("gone.png",))
    outside = tmp_path / "side.png"
    outside.write_bytes(_png_bytes())
    pictured = _form(photo=":/icons/img00.png")
    missing = _form(photo=":/icons/gone.png")
    plain = _form(resources=False)
    path = str(tmp_path / "form.ui")
    for mode in _MODES:
        tokens = tokens_from_palette(QPalette(), force_mode=mode)
        chrome = chrome_for(tokens)
        for width in (236, 300):
            window, pane, session, realizer = _pane(qapp, pictured, path, chrome=chrome)
            try:
                _select(session, "photo")
                pane.flush()
                _fit_row(qapp, window, pane, width)
                _open_row(pane, "formBuilder.row.pixmap", qapp)
                _grab(qapp, _popover(window), folder, "picture-picker-%s-%s-%d" % (mode, suffix, width))
            finally:
                _close(window, pane, realizer, session, qapp)
            window, pane, session, realizer = _pane(qapp, _form(), path, chrome=chrome)
            try:
                _select(session, "ok")
                pane.flush()
                _fit_row(qapp, window, pane, width)
                _open_row(pane, "formBuilder.row.icon", qapp)
                other = _search(qapp).window().findChild(QWidget, "formBuilder.iconOtherStates")
                assert other is not None
                other.click()
                qapp.processEvents()
                _grab(qapp, _popover(window), folder, "icon-states-%s-%s-%d" % (mode, suffix, width))
            finally:
                _close(window, pane, realizer, session, qapp)
            window, pane, session, realizer = _pane(qapp, missing, path, chrome=chrome)
            try:
                _select(session, "photo")
                pane.flush()
                _fit_row(qapp, window, pane, width)
                row = pane.findChild(QWidget, "formBuilder.row.pixmap")
                assert row is not None
                _grab(qapp, row, folder, "picture-missing-%s-%s-%d" % (mode, suffix, width))
            finally:
                _close(window, pane, realizer, session, qapp)
            window, pane, session, realizer = _pane(qapp, plain, path, chrome=chrome)
            try:
                _select(session, "photo")
                pane.flush()
                _fit_row(qapp, window, pane, width)
                _open_row(pane, "formBuilder.row.pixmap", qapp)
                caption = _popover(window).findChild(QLabel, "formBuilder.pictureNoResource")
                assert caption is not None and caption.isVisible()
                _grab(qapp, _popover(window), folder, "no-resource-%s-%s-%d" % (mode, suffix, width))
            finally:
                _close(window, pane, realizer, session, qapp)
            window, pane, session, realizer = _pane(qapp, _form(resources=False), path, chrome=chrome)
            try:
                _select(session, "photo")
                pane.flush()
                _fit_row(qapp, window, pane, width)
                _open_row(pane, "formBuilder.row.pixmap", qapp)
                opened = _popover(window)
                picker = opened.findChild(PicturePicker)
                assert isinstance(picker, PicturePicker)
                picker.choose(str(outside))
                qapp.processEvents()
                done = opened.findChild(QWidget, "formBuilder.popoverDone")
                assert done is not None
                done.click()
                qapp.processEvents()
                row = pane.findChild(QWidget, "formBuilder.row.pixmap")
                assert row is not None
                scroll = pane.findChild(QWidget, "formBuilder.inspectorScroll")
                if scroll is not None and hasattr(scroll, "ensureWidgetVisible"):
                    scroll.ensureWidgetVisible(row)
                qapp.processEvents()
                _grab(qapp, row, folder, "file-path-warning-%s-%s-%d" % (mode, suffix, width))
            finally:
                _close(window, pane, realizer, session, qapp)
            brushed = _form(
                photo=":/icons/img00.png",
                brush='<brush brushstyle="TexturePattern"><texture><pixmap>:/icons/img01.png</pixmap></texture></brush>',
            )
            window, pane, session, realizer = _pane(qapp, brushed, path, chrome=chrome)
            try:
                _select(session, "title")
                pane.flush()
                _fit_row(qapp, window, pane, width)
                _open_row(pane, "formBuilder.row.brush", qapp)
                _grab(qapp, _popover(window), folder, "brush-picture-%s-%s-%d" % (mode, suffix, width))
            finally:
                _close(window, pane, realizer, session, qapp)
