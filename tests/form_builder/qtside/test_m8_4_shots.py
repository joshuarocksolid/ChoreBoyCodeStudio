# pyright: reportAttributeAccessIssue=false
"""M8.4 Try screenshots. Skips unless CBCS_FB_SCREENSHOT_DIR is set."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import pytest

from app.core import constants
from app.features.form_builder.engine.data.connections import Connection, ConnectionSet
from app.features.form_builder.engine.data.connections_module import save_project_connections
from app.features.form_builder.integration.chrome import chrome_for
from app.features.form_builder.integration.connection_paths import project_slug
from app.features.form_builder.integration.settings_ext.connections_page import ConnectionsPage
from app.features.form_builder.qtside.preview.try_log import TryEvent, fold
from app.features.form_builder.qtside.preview.what_ran import TryChrome
from app.qt.QtWidgets import QApplication, QMessageBox, QWidget
from app.shell.theme_tokens import tokens_from_palette
from tests.form_builder.fixtures.m8.make_shop import build
from tests.form_builder.qtside.test_m8_4_try_data import _open, _project

pytestmark = pytest.mark.unit

_MODES = (
    constants.UI_THEME_MODE_LIGHT,
    constants.UI_THEME_MODE_DARK,
    constants.UI_THEME_MODE_HIGH_CONTRAST_LIGHT,
    constants.UI_THEME_MODE_HIGH_CONTRAST_DARK,
)


def test_try_screenshots(tmp_path: Path, qapp: QApplication) -> None:
    raw = os.environ.get("CBCS_FB_SCREENSHOT_DIR") or ""
    if not raw:
        pytest.skip("CBCS_FB_SCREENSHOT_DIR is not set")
    folder = Path(raw)
    folder.mkdir(parents=True, exist_ok=True)
    root, db = _project(tmp_path)
    banner = (
        "Try: changes to Shop database are rolled back. "
        "While a save runs, other people using it may wait up to 2 seconds."
    )
    rolled = fold(
        (
            TryEvent(
                "sql",
                "",
                {"sentence": 'Ran: UPDATE "m84_invoices" SET "notes" = %s … (2 values)', "values": ["saved-note", 1]},
            ),
            TryEvent("sql", "", {"sentence": "Saved, then rolled back", "values": []}),
        ),
        {},
        {},
    )
    project = tmp_path / "settings"
    project.mkdir()
    build(str(project / "data" / "shop.db"))
    save_project_connections(
        str(project),
        ConnectionSet((Connection("shop", "Shop database", "sqlite", file="data/shop.db", try_show_sql_only=True),)),
        slug=project_slug(str(project)),
    )
    from app.features.form_builder.qtside.preview.child.try_connections import end_all

    for mode in _MODES:
        tokens = tokens_from_palette(qapp.palette(), force_mode=mode)
        chrome = chrome_for(tokens)
        window = TryChrome()
        window.apply_chrome(chrome)
        window.resize(1100, 720)
        form = QWidget()
        window.adopt(form)
        seen: list = []
        host, session = _open(root, db, "scratch", "view-shot-%s" % mode, seen, form)
        try:
            host.ui.notesEdit.setText("saved-note")
            assert host.ui.cbcs_save() is True
            window.set_try_data(session.strip_text(), "", session.show_reset())
            window.what_ran.add(_sql_lines(session.notes), int(time.time() * 1000))
            window.what_ran.expand_all()
            window.show()
            _pump(qapp)
            _grab(window, folder / ("try-sqlite-%s.png" % mode))
        finally:
            window.close()
            host.close()
            end_all()
        postgres = _chrome(
            "Data: Shop database. Changes are rolled back.",
            banner,
            False,
            rolled,
            chrome,
        )
        _grab(postgres, folder / ("try-postgres-%s.png" % mode))
        postgres.close()
        box = QMessageBox()
        box.setWindowTitle("")
        box.setText("Another user is editing this invoice. Try stopped waiting after 2 seconds.")
        icon = getattr(getattr(QMessageBox, "Icon", QMessageBox), "Warning", None)
        if icon is None:
            icon = getattr(QMessageBox, "Warning", None)
        if icon is not None:
            box.setIcon(icon)
        box.setStyleSheet(
            "QMessageBox { background: %s; color: %s; } QLabel { color: %s; }"
            % (tokens.panel_bg, tokens.text_primary, tokens.text_primary)
        )
        box.resize(640, 160)
        box.show()
        _pump(qapp)
        _grab(box, folder / ("try-lock-%s.png" % mode))
        box.close()
        page = ConnectionsPage(None, str(project))
        page.apply_theme(tokens)
        page.resize(960, 640)
        page.show()
        _pump(qapp)
        _grab(page, folder / ("try-setting-%s.png" % mode))
        page.close()


def _sql_lines(notes: Any) -> Any:
    events = tuple(
        TryEvent("sql", "", {"sentence": item.sentence, "values": [_shown(value) for value in item.values]})
        for item in notes
        if item.kind in ("ran", "would_run", "saved", "warning")
    )
    return fold(events, {}, {})


def _chrome(strip: str, banner: str, reset: bool, lines: Any, chrome: Any) -> TryChrome:
    window = TryChrome()
    window.set_try_data(strip, banner, reset)
    window.apply_chrome(chrome)
    window.what_ran.add(lines, int(time.time() * 1000))
    window.what_ran.expand_all()
    window.resize(1100, 720)
    window.show()
    _pump(QApplication.instance())
    return window


def _shown(value: object) -> str:
    if value is None:
        return "NULL"
    return str(value)


def _grab(widget: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    widget.grab().save(str(path))


def _pump(qapp: Any, times: int = 4) -> None:
    if qapp is None:
        return
    for _index in range(times):
        qapp.processEvents()
