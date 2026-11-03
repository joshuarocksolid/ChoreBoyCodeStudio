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
from app.qt.QtWidgets import (
    QApplication,
    QFormLayout,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
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
        seen: list = []
        host, session = _open(root, db, "scratch", "view-shot-%s" % mode, seen)
        try:
            host.ui.notesEdit.setText("saved-note")
            assert host.ui.cbcs_save() is True
            window.adopt(_invoice_page(host.ui))
            window.set_try_data(session.strip_text(), "", session.show_reset())
            window.what_ran.add(_sql_lines(session.notes), int(time.time() * 1000))
            window.what_ran.expand_all()
            window.show()
            host.hide()
            _pump(qapp)
            _grab(window, folder / ("try-sqlite-%s.png" % mode))
        finally:
            window.close()
            host.close()
            end_all()
        pg_host, pg_session = _open(root, db, "rollback", "view-pg-%s" % mode, seen)
        postgres = None
        try:
            pg_host.ui.notesEdit.setText("saved-note")
            assert pg_host.ui.cbcs_save() is True
            postgres = TryChrome()
            postgres.apply_chrome(chrome)
            postgres.resize(1100, 720)
            postgres.adopt(_invoice_page(pg_host.ui))
            postgres.set_try_data("Data: Shop database. Changes are rolled back.", banner, False)
            postgres.what_ran.add(_sql_lines(pg_session.notes), int(time.time() * 1000))
            postgres.what_ran.expand_all()
            postgres.show()
            pg_host.hide()
            _pump(qapp)
            _grab(postgres, folder / ("try-postgres-%s.png" % mode))
        finally:
            if postgres is not None:
                postgres.close()
            pg_host.close()
            end_all()
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


def _invoice_page(ui: Any) -> QWidget:
    """The invoice fields in a form, with the record buttons under them."""

    page = QWidget()
    outer = QVBoxLayout(page)
    outer.setContentsMargins(16, 12, 16, 12)
    outer.setSpacing(8)
    form = QFormLayout()
    form.setContentsMargins(0, 0, 0, 0)
    form.setHorizontalSpacing(12)
    form.setVerticalSpacing(8)
    form.addRow("Invoice no", ui.invoiceNoEdit)
    form.addRow("Customer", ui.customerIdSpin)
    form.addRow("Date", ui.invoiceDateEdit)
    form.addRow("Notes", ui.notesEdit)
    outer.addLayout(form)
    buttons = QHBoxLayout()
    buttons.setSpacing(8)
    for label in ("First", "Previous", "Next", "Last", "Save", "New", "Delete"):
        buttons.addWidget(QPushButton(label))
    buttons.addStretch(1)
    outer.addLayout(buttons)
    outer.addStretch(1)
    return page


def _sql_lines(notes: Any) -> Any:
    events = tuple(
        TryEvent("sql", "", {"sentence": item.sentence, "values": list(item.values)})
        for item in notes
        if item.kind in ("ran", "would_run", "saved", "warning")
    )
    return fold(events, {}, {})


def _grab(widget: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    widget.grab().save(str(path))


def _pump(qapp: Any, times: int = 4) -> None:
    if qapp is None:
        return
    for _index in range(times):
        qapp.processEvents()
