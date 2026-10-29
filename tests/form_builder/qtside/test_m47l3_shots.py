# pyright: reportAttributeAccessIssue=false
"""M4.7-L3 shots: the label's Picture row in Content, and its popover. Skips unless CBCS_FB_SCREENSHOT_DIR is set."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.core import constants
from app.features.form_builder.integration.chrome import chrome_for
from app.features.form_builder.qtside.inspector.api import GroupId
from app.qt.QtGui import QPalette
from app.qt.QtWidgets import QApplication, QWidget
from app.shell.theme_tokens import tokens_from_palette
from tests.form_builder.inspector.test_m43c_pictures import (
    _close,
    _fit_row,
    _form,
    _open_row,
    _pane,
    _seed,
    _select,
)

pytestmark = pytest.mark.unit

_MODES = (
    ("light", constants.UI_THEME_MODE_LIGHT),
    ("hc-dark", constants.UI_THEME_MODE_HIGH_CONTRAST_DARK),
)


@pytest.mark.timeout(300)
def test_m47l3_picture_row_shots(qapp: QApplication, tmp_path: Path) -> None:
    raw = os.environ.get("CBCS_FB_SCREENSHOT_DIR") or ""
    if not raw:
        pytest.skip("CBCS_FB_SCREENSHOT_DIR is not set")
    folder = Path(raw)
    folder.mkdir(parents=True, exist_ok=True)
    _seed(tmp_path, tuple("img%02d.png" % index for index in range(12)))
    path = str(tmp_path / "form.ui")
    for name, mode in _MODES:
        chrome = chrome_for(tokens_from_palette(QPalette(), force_mode=mode))
        window, pane, session, realizer = _pane(qapp, _form(photo=":/icons/img00.png"), path, chrome=chrome)
        try:
            _select(session, "photo")
            pane.set_group_expanded(GroupId.CONTENT, True)
            pane.flush()
            _fit_row(qapp, window, pane, 300)
            qapp.processEvents()
            window.grab().save(str(folder / ("label-content-group-%s.png" % name)))
            _open_row(pane, "formBuilder.row.pixmap", qapp)
            popovers = [w for w in window.findChildren(QWidget, "formBuilder.rowPopover") if w.isVisible()]
            assert popovers
            popovers[-1].grab().save(str(folder / ("picture-popover-%s.png" % name)))
        finally:
            _close(window, pane, realizer, session, qapp)
