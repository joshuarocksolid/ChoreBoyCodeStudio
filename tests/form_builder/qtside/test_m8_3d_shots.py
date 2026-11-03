# pyright: reportAttributeAccessIssue=false
"""M8.3d form-from-a-table shots. Skips unless CBCS_FB_SCREENSHOT_DIR is set."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.core import constants
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.integration.chrome import chrome_for
from app.features.form_builder.qtside.dialogs.from_table import FromTableDialog
from app.features.form_builder.qtside.inspector.pane import InspectorPane, TabId
from app.features.form_builder.qtside.realize import Realizer
from app.qt.QtCore import QDate
from app.qt.QtUiTools import QUiLoader
from app.qt.QtWidgets import QApplication, QHBoxLayout, QWidget
from app.shell.theme_tokens import tokens_from_palette
from tests.form_builder.engine.test_m8_3d_from_table import (
    _customer_request,
    _hosts,
    _invoice_request,
    _line,
    _pick,
    _shop,
    _texts,
    _write_generated,
)
from tests.form_builder.qtside.test_m8_2_shots import _shoot

pytestmark = pytest.mark.unit

_MODES = (
    constants.UI_THEME_MODE_LIGHT,
    constants.UI_THEME_MODE_DARK,
    constants.UI_THEME_MODE_HIGH_CONTRAST_LIGHT,
    constants.UI_THEME_MODE_HIGH_CONTRAST_DARK,
)

_MAKES = ("record", "list", "both")


def test_from_table_screenshots(tmp_path: Path, qapp) -> None:
    raw = os.environ.get("CBCS_FB_SCREENSHOT_DIR", "").strip()
    if not raw:
        pytest.skip("set CBCS_FB_SCREENSHOT_DIR to write form-from-a-table screenshots")
    folder = Path(raw)
    folder.mkdir(parents=True, exist_ok=True)
    root, schema = _shop(tmp_path)
    _dialogs(root, qapp, folder)
    texts = _texts(root, schema, _invoice_request()) + _texts(root, schema, _customer_request())
    _write_generated(root, texts)
    by_stem = dict(texts)
    _editor(root, by_stem["invoice"], qapp, folder, "invoice-editor")
    _editor(root, by_stem["customer_list"], qapp, folder, "customer-list-editor")
    _running(root, qapp, folder)


def _dialogs(root: Path, qapp, folder: Path) -> None:
    tokens = tokens_from_palette(qapp.palette(), force_mode=constants.UI_THEME_MODE_LIGHT)
    dialog = FromTableDialog(
        project_root=str(root),
        stem="invoice",
        chrome=chrome_for(tokens),
        date_format="yyyy-MM-dd",
        name_reason=lambda: None,
    )
    dialog.set_database(str(root / "data" / "shop.db"), "shop")
    _select(dialog, "invoices")
    assert dialog._lines.isChecked() is True
    for make in _MAKES:
        dialog._make.setCurrentIndex(dialog._make.findData(make))
        qapp.processEvents()
        if make == "record":
            assert "and lines" in dialog._create.text()
        _shoot_dialog(dialog, qapp, folder, "from-table-%s" % make)
    dialog.close()


def _editor(root: Path, text: str, qapp, folder: Path, name: str) -> None:
    ui_path = root / "forms" / ("%s.ui" % name)
    ui_path.parent.mkdir(parents=True, exist_ok=True)
    ui_path.write_text(text, encoding="utf-8")
    scope = FormScope(
        kind="project",
        ui_path=str(ui_path),
        project_root=str(root),
        generated_path=str(root / "forms" / "ui_shot.py"),
        window_path=str(root / "forms" / "shot_window.py"),
        module_name="forms.ui_shot",
    )
    session = FormSession.open(text, path=str(ui_path), scope=scope)
    session.selection.set((session.document.root.id,), source=SelectionSource.PROGRAM)
    realizer = Realizer(session)
    realizer.build()
    frame = QWidget()
    frame.session = session
    frame.project_root = str(root)
    pane = InspectorPane(session, realizer, data_tab=True, on_leave=lambda: None, parent=frame)
    canvas = QUiLoader().load(str(ui_path), frame)
    assert canvas is not None
    layout = QHBoxLayout(frame)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(pane, 1)
    layout.addWidget(canvas, 1)
    pane.focus_tab(TabId.DATA)
    frame.resize(1100, 720)
    frame.show()
    qapp.processEvents()
    pane.focus_tab(TabId.DATA)
    for mode in _MODES:
        tokens = tokens_from_palette(frame.palette(), force_mode=mode)
        pane.apply_chrome(chrome_for(tokens))
        frame.resize(1100, 720)
        frame.show()
        for _index in range(4):
            qapp.processEvents()
            time.sleep(0.01)
        frame.grab().save(str(folder / ("%s-%s.png" % (name, mode))))
    pane.dispose()
    session.dispose()


def _running(root: Path, qapp, folder: Path) -> None:
    with _hosts(root, "invoice") as (host, _db):
        host.ui.cbcs_new()
        host.ui.cbcs_load_lookups()
        host.ui.invoice_no.setText("INV-9")
        host.ui.invoice_date.setDate(QDate(2026, 5, 2))
        _pick(host.ui.customer_id, 2)
        host.ui._cbcs_add_row()
        host.ui._cbcs_add_row()
        _line(host.ui, 0, "description", "Widget")
        _line(host.ui, 0, "qty", 2)
        _line(host.ui, 0, "price", "1.50")
        _line(host.ui, 1, "description", "Gasket")
        _line(host.ui, 1, "qty", 1)
        _line(host.ui, 1, "price", "2.00")
        _named_line(host.ui, 0, "product_id", 1, "Widget")
        _named_line(host.ui, 1, "product_id", 2, "Gadget")
        host.ui._cbcs_recompute_lines()
        host.ui.cbcs_refresh()
        if hasattr(host.ui, "total"):
            host.ui.total.setValue(5.0)
        _named_line(host.ui, 0, "product_id", 1, "Widget")
        _named_line(host.ui, 1, "product_id", 2, "Gadget")
        host.resize(720, 640)
        qapp.processEvents()
        _shoot(host, qapp, folder, "invoice-running", 720, 640)
    with _hosts(root, "customer_list") as (host, _db):
        host.ui.cbcs_refresh_list()
        host.resize(720, 480)
        qapp.processEvents()
        _shoot(host, qapp, folder, "customer-list-running", 720, 480)


def _named_line(ui: object, row: int, name: str, value: object, shown: str) -> None:
    _line(ui, row, name, value)
    label = ""
    lookup = getattr(ui, "_cbcs_line_lookup_label", None)
    if callable(lookup):
        label = lookup(name, value) or ""
    column = ui._cbcs_line_names.index(name)
    ui.invoice_linesView.model().item(row, column).setText(label or shown)


def _select(dialog: FromTableDialog, table: str) -> None:
    for index in range(dialog._tables.count()):
        item = dialog._tables.item(index)
        if item is not None and item.text() == table:
            dialog._tables.setCurrentRow(index)
            return
    raise AssertionError(table)


def _shoot_dialog(dialog: FromTableDialog, qapp: QApplication, folder: Path, name: str) -> None:
    for mode in _MODES:
        tokens = tokens_from_palette(dialog.palette(), force_mode=mode)
        dialog._chrome = chrome_for(tokens)
        dialog._apply_chrome()
        dialog._refresh_preview()
        dialog.resize(1100, 680)
        dialog.show()
        for _index in range(4):
            qapp.processEvents()
            time.sleep(0.01)
        dialog.grab().save(str(folder / ("%s-%s.png" % (name, mode))))
