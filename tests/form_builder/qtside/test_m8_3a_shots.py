# pyright: reportAttributeAccessIssue=false
"""M8.3a lookup shots. Skips unless CBCS_FB_SCREENSHOT_DIR is set."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.core import constants
from app.features.form_builder.engine.data.schema import Column, Schema, Table, set_schema_reader
from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.qtside.inspector.data_page import DataPage
from app.qt.QtWidgets import QApplication, QWidget
from app.shell.theme_tokens import tokens_from_palette
from tests.form_builder.engine.test_m8_2_scenario import record_window, shop_with_three
from tests.form_builder.engine.test_m8_3a_lookup import _story_ui
from tests.form_builder.qtside.test_m8_3a_lookup_section import _combo_form, _open

pytestmark = pytest.mark.unit

_MODES = (
    constants.UI_THEME_MODE_LIGHT,
    constants.UI_THEME_MODE_DARK,
    constants.UI_THEME_MODE_HIGH_CONTRAST_LIGHT,
    constants.UI_THEME_MODE_HIGH_CONTRAST_DARK,
)


def test_lookup_shots(qapp, tmp_path: Path) -> None:
    directory = os.environ.get("CBCS_FB_SCREENSHOT_DIR", "").strip()
    if not directory:
        pytest.skip("set CBCS_FB_SCREENSHOT_DIR to grab form-builder screenshots")
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    schema = Schema(
        "office",
        "sqlite",
        "SQLite",
        "2026-11-02T12:00:00",
        "sqlite3",
        (
            Table("invoices", (Column("id", "integer", False), Column("customer_id", "integer", True)), key="id"),
            Table(
                "customers",
                (Column("id", "integer", False), Column("name", "text", True), Column("email", "text", True)),
                key="id",
                rows=12480,
            ),
        ),
    )
    set_schema_reader(lambda _doc, _name: schema)
    try:
        session, host = _open(_combo_form(("email",)), tmp_path)
        try:
            combo_id = session.document.by_name("customerCombo")[0]
            session.selection.set((combo_id,), source=SelectionSource.PROGRAM)
            host.show()
            page = DataPage(host)
            page.show()
            qapp.processEvents()
            page.paint("QComboBox")
            _shoot(page, qapp, root, "lookup-section", 420, 560)
        finally:
            session.dispose()
        with record_window(tmp_path / "run", _story_ui(), shop_with_three, choose=lambda text: "Close") as (host, _db):
            window = host
            window.resize(720, 280)
            ui = host.ui
            for mode in _MODES:
                _paint(window, mode)
                window.show()
                for _cycle in range(4):
                    qapp.processEvents()
                    time.sleep(0.01)
                ui.customerCombo.showPopup()
                qapp.processEvents()
                window.grab().save(str(root / ("lookup-also-%s.png" % mode)))
                view = ui.customerCombo.view()
                popup = view.window() if view is not None else None
                if popup is not None and popup.isVisible() and popup is not window:
                    popup.grab().save(str(root / ("lookup-open-%s.png" % mode)))
                else:
                    window.grab().save(str(root / ("lookup-open-%s.png" % mode)))
                    print("lookup popup did not paint for", mode)
                ui.customerCombo.hidePopup()
    finally:
        set_schema_reader(None)


def _shoot(widget: QWidget, qapp: QApplication, root: Path, name: str, width: int, height: int) -> None:
    for mode in _MODES:
        _paint(widget, mode)
        widget.resize(width, height)
        widget.show()
        for _cycle in range(4):
            qapp.processEvents()
            time.sleep(0.01)
        widget.grab().save(str(root / ("%s-%s.png" % (name, mode))))


def _paint(widget: QWidget, mode: str) -> None:
    tokens = tokens_from_palette(widget.palette(), force_mode=mode)
    if hasattr(widget, "apply_colors"):
        widget.apply_colors(
            tokens.panel_bg,
            tokens.text_primary,
            tokens.text_muted,
            tokens.diag_warning_color,
            tokens.diag_error_color,
            tokens.accent,
            tokens.input_bg,
            tokens.border,
            int(tokens.focus_border_width or 1),
        )
    from app.qt.QtGui import QColor, QPalette

    palette = widget.palette()
    palette.setColor(QPalette.ColorRole.Window, QColor(tokens.panel_bg))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(tokens.text_primary))
    palette.setColor(QPalette.ColorRole.Base, QColor(tokens.input_bg))
    palette.setColor(QPalette.ColorRole.Text, QColor(tokens.text_primary))
    widget.setPalette(palette)
