# pyright: reportAttributeAccessIssue=false
"""M8.3d form-from-a-table shots. Skips unless CBCS_FB_SCREENSHOT_DIR is set."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.core import constants
from app.features.form_builder.integration.chrome import chrome_for
from app.features.form_builder.integration.provider import FormTabProvider
from app.features.form_builder.qtside.dialogs.from_table import FromTableDialog
from app.qt.QtCore import QDate
from app.qt.QtWidgets import QApplication, QComboBox, QPlainTextEdit, QWidget
from app.shell.tab_content_providers import TabSurfaceRequest
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


def test_from_table_opens_the_first_saved_connection(tmp_path: Path, qapp) -> None:
    from app.features.form_builder.engine.data.connections import Connection, ConnectionSet, save_connections

    root, _schema = _shop(tmp_path)
    save_connections(
        str(root),
        ConnectionSet(
            (
                Connection("shop", "Shop database", "sqlite", file="data/shop.db"),
                Connection("archive", "Archive", "sqlite", file="data/shop.db"),
            )
        ),
    )
    tokens = tokens_from_palette(qapp.palette(), force_mode=constants.UI_THEME_MODE_LIGHT)
    dialog = FromTableDialog(
        project_root=str(root),
        stem="invoice",
        chrome=chrome_for(tokens),
        date_format="yyyy-MM-dd",
        name_reason=lambda: None,
    )
    try:
        combo = dialog.findChild(QComboBox, "formBuilder.fromTable.connection")
        assert combo is not None
        assert combo.currentText() == "Shop database"
        assert combo.currentData() == "shop"
    finally:
        dialog.close()


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
    _editor(root, "invoice", qapp, folder, "invoice-editor")
    _editor(root, "customer_list", qapp, folder, "customer-list-editor")
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


def _editor(root: Path, stem: str, qapp, folder: Path, name: str) -> None:
    path = root / "forms" / ("%s.ui" % stem)
    parent = QWidget()

    def create_source_editor() -> QPlainTextEdit:
        editor = QPlainTextEdit(parent)
        editor.setObjectName("shell.editorTabs.textEditor")
        return editor

    surface = FormTabProvider().create_surface(
        TabSurfaceRequest(
            file_path=str(path),
            initial_text=path.read_text(encoding="utf-8"),
            parent=parent,
            theme=tokens_from_palette(qapp.palette(), force_mode=constants.UI_THEME_MODE_LIGHT),
            create_source_editor=create_source_editor,
            open_linked_file=lambda _linked: None,
            project_root=str(root),
        )
    )
    surface.resize(1200, 800)
    surface.show()
    qapp.processEvents()
    surface.workbench.focus_section("data")
    panel = surface.workbench.section_widget("data")
    assert panel is not None
    panel.setParent(None)
    _shoot(panel, qapp, folder, name, 640, 760)
    panel.close()
    surface.close()


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
