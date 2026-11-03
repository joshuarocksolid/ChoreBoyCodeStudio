# pyright: reportAttributeAccessIssue=false
"""M8.3b shots. Skips unless CBCS_FB_SCREENSHOT_DIR is set. Not part of the gate."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.core import constants
from app.features.form_builder.engine.data.connections import Connection, ConnectionSet, save_connections
from app.features.form_builder.engine.data.connections_module import render_connections_module
from app.features.form_builder.engine.data.schema import set_schema_reader, write_schema
from app.features.form_builder.engine.data.schema_cache import install_schema_reader
from app.features.form_builder.engine.data.source import DataColumn, RecordSource, Rows
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.qtside.data_panel.edits import connect_form
from app.features.form_builder.qtside.data_panel.lines_sheet import add_lines
from app.features.form_builder.qtside.data_panel.panel import DataPanel
from app.qt.QtCore import QTimer
from app.qt.QtWidgets import QApplication, QDialog, QLabel, QPushButton, QWidget
from app.shell.theme_tokens import tokens_from_palette
from tests.form_builder.engine.test_m8_2_scenario import _generate, _load_module, _ui_class, _xml
from tests.form_builder.engine.test_m8_3b_lines import _index, _invoice_schema, _prepare, _set, _ui

pytestmark = pytest.mark.unit

_MODES = (
    constants.UI_THEME_MODE_LIGHT,
    constants.UI_THEME_MODE_DARK,
    constants.UI_THEME_MODE_HIGH_CONTRAST_LIGHT,
    constants.UI_THEME_MODE_HIGH_CONTRAST_DARK,
)


def test_lines_shots(tmp_path: Path, qapp: QApplication) -> None:
    raw = os.environ.get("CBCS_FB_SCREENSHOT_DIR", "").strip()
    if not raw:
        pytest.skip("set CBCS_FB_SCREENSHOT_DIR to write the lines shots")
    root = Path(raw)
    root.mkdir(parents=True, exist_ok=True)
    _section(tmp_path, qapp, root)
    _running(tmp_path, qapp, root)


def _section(tmp_path: Path, qapp: QApplication, root: Path) -> None:
    project = tmp_path / "section"
    _prepare(project)
    try:
        save_connections(str(project), ConnectionSet((Connection("shop", "Shop", "sqlite", file="data/shop.db"),)))
        session = FormSession.open(
            _xml(RecordSource("shop", "invoices", "id"), (("QLineEdit", "notesEdit", "notes", ""),)),
            path=str(project / "invoice.ui"),
            scope=FormScope(kind="external", ui_path=str(project / "invoice.ui"), project_root=str(project)),
        )
        host = QWidget()
        host.session = session
        host.project_root = str(project)
        connect_form(session, RecordSource("shop", "invoices", "id"))
        add_lines(
            session,
            Rows("invoice_lines", "invoice_id", "id", (DataColumn("qty", "Qty", "whole", None, "1"),), "line_no", "line_no"),
        )
        panel = DataPanel(host)
        panel.reload()
        refresh = panel.findChild(QPushButton, "formBuilder.data.schemaRefresh")
        assert refresh is not None
        refresh.click()
        sentence = panel.findChild(QLabel, "formBuilder.data.schemaSentence")
        for _ in range(40):
            qapp.processEvents()
            time.sleep(0.05)
            if sentence is not None and "haven't" not in sentence.text():
                break
        panel.reload()
        for mode in _MODES:
            panel.apply_theme(tokens_from_palette(panel.palette(), force_mode=mode))
            panel.resize(520, 420)
            panel.show()
            _settle(qapp)
            panel.grab().save(str(root / ("lines-section-%s.png" % mode)))
        session.dispose()
    finally:
        set_schema_reader(None)


def _running(tmp_path: Path, qapp: QApplication, root: Path) -> None:
    project = tmp_path / "proj"
    forms = project / "forms"
    forms.mkdir(parents=True)
    ui_text = _ui()
    ui_path = forms / "invoice.ui"
    ui_path.write_text(ui_text, encoding="utf-8")
    _prepare(project)
    value = ConnectionSet((Connection("shop", "Shop", "sqlite", file="data/shop.db"),))
    save_connections(str(project), value)
    (project / "cbcs_connections.py").write_text(render_connections_module(value, project_slug="m83b"), encoding="utf-8")
    folder = project / "cbcs" / "schema"
    folder.mkdir(parents=True)
    (folder / "shop.json").write_text(write_schema(_invoice_schema()), encoding="utf-8")
    install_schema_reader(str(project))
    try:
        source = _generate(project, ui_path, ui_text)
        generated = forms / "ui_invoice.py"
        generated.write_text(source, encoding="utf-8")
        module = _load_module(generated, "ui_invoice_shots")
        import sys

        previous = sys.modules.get("cbcs_connections")
        sys.modules["cbcs_connections"] = _load_module(project / "cbcs_connections.py", "cbcs_connections_shots")
        sys.path.insert(0, str(project))
        try:

            class Host(QDialog):
                def __init__(self) -> None:
                    super().__init__()
                    self.ui = _ui_class(module)()
                    self.ui.setupUi(self)

            host = Host()
            host.resize(760, 520)
            for mode in _MODES:
                _paint(host, mode)
                host.show()
                _settle(qapp)
                host.grab().save(str(root / ("invoice-lines-%s.png" % mode)))
                _set(host.ui, 0, "qty", 4)
                column = _index(host.ui, "qty")
                index = host.ui.linesView.model().index(0, column)
                host.ui.linesView.edit(index)
                _settle(qapp)
                host.grab().save(str(root / ("invoice-edit-%s.png" % mode)))
                host.ui.linesView.closePersistentEditor(index)
                _set(host.ui, 0, "qty", 1)
                host.ui.cbcs_revert()
            _set(host.ui, 0, "qty", 4)
            grabbed = []

            def grab_prompt() -> None:
                box = qapp.activeModalWidget()
                if box is None:
                    return
                grabbed.append(box.windowTitle())
                for mode in _MODES:
                    _paint(box, mode)
                    box.grab().save(str(root / ("unsaved-line-%s.png" % mode)))
                cancel = None
                buttons = getattr(box, "buttons", None)
                found = buttons() if callable(buttons) else ()
                if isinstance(found, (list, tuple)):
                    for button in found:
                        if button.text() in ("Cancel", "Discard"):
                            cancel = button
                            break
                if cancel is not None:
                    cancel.click()

            QTimer.singleShot(0, grab_prompt)
            host.close()
            _settle(qapp)
            assert grabbed
        finally:
            if previous is None:
                sys.modules.pop("cbcs_connections", None)
            else:
                sys.modules["cbcs_connections"] = previous
            if sys.path and sys.path[0] == str(project):
                sys.path.pop(0)
    finally:
        set_schema_reader(None)


def _paint(widget: QWidget, mode: str) -> None:
    tokens = tokens_from_palette(widget.palette(), force_mode=mode)
    widget.setStyleSheet(
        "QDialog, QWidget { background: %s; color: %s; } "
        "QLabel, QTableView, QHeaderView, QLineEdit, QSpinBox, QDateEdit { color: %s; background: %s; } "
        "QPushButton { color: %s; background: %s; }"
        % (tokens.window_bg, tokens.text_primary, tokens.text_primary, tokens.editor_bg, tokens.text_primary, tokens.window_bg)
    )


def _settle(qapp: QApplication) -> None:
    for _ in range(4):
        qapp.processEvents()
        time.sleep(0.01)
