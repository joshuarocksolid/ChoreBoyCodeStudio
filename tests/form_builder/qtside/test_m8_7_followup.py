# pyright: reportAttributeAccessIssue=false
"""M8.7 follow-up. Lines sheet, From table keys, start screen, and the narrow column row."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.bootstrap.paths import resolve_app_root
from app.features.form_builder.engine.data.connections import Connection, ConnectionSet, save_connections
from app.features.form_builder.engine.data.schema import Column, set_schema_reader, write_schema
from app.features.form_builder.engine.data.schema_cache import install_schema_reader
from app.features.form_builder.engine.data.source import CalcColumn, DataColumn, RecordSource, Rows
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.project.start_screen import apply_start_screen
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.integration.chrome import chrome_for
from app.features.form_builder.integration.new_form import report_status
from app.features.form_builder.qtside.data_panel.edits import connect_form
from app.features.form_builder.qtside.data_panel.lines_sheet import LinesSheet, lines_on
from app.features.form_builder.qtside.data_panel.sections_ext.columns import _Row
from app.features.form_builder.qtside.data_panel.sections_ext.source_line import _create
from app.features.form_builder.qtside.dialogs.from_table import FromTableDialog
from app.qt.QtCore import QEvent, Qt
from app.qt.qt_compat import enum_value, wrapper_is_valid
from app.qt.QtTest import QTest
from app.qt.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QLabel,
    QListWidget,
    QMainWindow,
    QPushButton,
    QWidget,
)
from app.shell.theme_tokens import tokens_from_palette
from tests.form_builder.engine.test_m8_2_scenario import _xml
from tests.form_builder.engine.test_m8_3b_lines import _invoice_schema, _prepare
from tests.form_builder.engine.test_m8_3d_from_table import _shop

pytestmark = pytest.mark.unit


def test_lines_sheet_adds_line_total_for_a_new_grid(tmp_path: Path, qapp: QApplication) -> None:
    host, session = _lines_host(tmp_path)
    try:
        sheet = LinesSheet(host, session, "")
        _add_line_total(sheet)
        sheet._accept()
        assert _line_total(session) == "qty * price"
    finally:
        session.dispose()
        set_schema_reader(None)


def test_lines_sheet_adds_line_total_when_editing(tmp_path: Path, qapp: QApplication) -> None:
    del qapp
    host, session = _lines_host(tmp_path)
    try:
        from app.features.form_builder.qtside.data_panel.lines_sheet import add_lines

        name = add_lines(
            session,
            Rows(
                "invoice_lines",
                "invoice_id",
                "id",
                (DataColumn("qty", "Qty", "whole", None, "1"),),
                "line_no",
                "line_no",
            ),
        )
        sheet = LinesSheet(host, session, name)
        _add_line_total(sheet)
        sheet._accept()
        assert _line_total(session) == "qty * price"
    finally:
        session.dispose()
        set_schema_reader(None)


def test_tab_reaches_create_and_arrows_move_between_cells(tmp_path: Path, qapp: QApplication) -> None:
    dialog = _dialog(tmp_path)
    try:
        dialog.resize(960, 560)
        dialog.show()
        qapp.processEvents()
        _select(dialog, "invoices")
        qapp.processEvents()
        tables = dialog.findChild(QListWidget, "formBuilder.fromTable.tables")
        grid = dialog.findChild(QWidget, "formBuilder.fromTable.mapping")
        make = dialog.findChild(QComboBox, "formBuilder.fromTable.make")
        lines = dialog.findChild(QCheckBox, "formBuilder.fromTable.lines")
        create = dialog.findChild(QPushButton, "formBuilder.fromTable.create")
        assert tables is not None and grid is not None and make is not None
        assert lines is not None and create is not None
        tables.setFocus()
        qapp.processEvents()
        QTest.keyClick(tables, Qt.Key_Tab)
        qapp.processEvents()
        assert qapp.focusWidget() is grid
        QTest.keyClick(grid, Qt.Key_Right)
        qapp.processEvents()
        assert grid.currentColumn() == 1
        column = grid.currentColumn()
        QTest.keyClick(grid, Qt.Key_Tab)
        qapp.processEvents()
        assert qapp.focusWidget() is make
        assert grid.currentColumn() == column
        QTest.keyClick(make, Qt.Key_Tab)
        qapp.processEvents()
        assert qapp.focusWidget() is lines
        QTest.keyClick(lines, Qt.Key_Tab)
        qapp.processEvents()
        link = dialog.findChild(QWidget, "formBuilder.fromTable.linesLink")
        if qapp.focusWidget() is link:
            QTest.keyClick(link, Qt.Key_Tab)
            qapp.processEvents()
        cancel = dialog.findChild(QPushButton, "formBuilder.fromTable.cancel")
        assert qapp.focusWidget() is cancel
        QTest.keyClick(cancel, Qt.Key_Tab)
        qapp.processEvents()
        assert qapp.focusWidget() is create
    finally:
        dialog.close()


@pytest.mark.parametrize(
    ("key", "mods"),
    (
        (Qt.Key_F2, Qt.NoModifier),
        (Qt.Key_Space, Qt.NoModifier),
        (Qt.Key_Down, Qt.AltModifier),
    ),
)
def test_shows_as_opens_from_the_keyboard(
    tmp_path: Path, qapp: QApplication, key: object, mods: object
) -> None:
    dialog = _dialog(tmp_path)
    try:
        dialog.resize(960, 560)
        dialog.show()
        qapp.processEvents()
        _select(dialog, "invoices")
        grid = dialog.findChild(QWidget, "formBuilder.fromTable.mapping")
        assert grid is not None and grid.rowCount() > 0
        grid.setCurrentCell(0, 3)
        grid.setFocus()
        qapp.processEvents()
        QTest.keyClick(grid, key, mods)
        qapp.processEvents()
        box = grid.cellWidget(0, 3)
        assert isinstance(box, QComboBox)
        assert box.view().isVisible()
        box.hidePopup()
    finally:
        dialog.close()


def test_add_connection_selects_the_new_one_and_first_open_keeps_the_first(
    tmp_path: Path, qapp: QApplication
) -> None:
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

    def add() -> None:
        save_connections(
            str(root),
            ConnectionSet(
                (
                    Connection("shop", "Shop database", "sqlite", file="data/shop.db"),
                    Connection("archive", "Archive", "sqlite", file="data/shop.db"),
                    Connection("fresh", "Fresh database", "sqlite", file="data/shop.db"),
                )
            ),
        )

    dialog = _dialog(tmp_path, root=root, add_connection=add)
    try:
        combo = dialog.findChild(QComboBox, "formBuilder.fromTable.connection")
        assert combo is not None
        assert combo.currentData() == "shop"
        button = dialog.findChild(QPushButton, "formBuilder.fromTable.addConnection")
        assert button is not None
        button.click()
        qapp.processEvents()
        assert combo.currentData() == "fresh"
    finally:
        dialog.close()


def test_template_main_opens_the_list_screen(tmp_path: Path, qapp: QApplication) -> None:
    root, _schema = _shop(tmp_path)
    template = (resolve_app_root() / "templates" / "qt_app" / "main.py").read_bytes()
    (root / "main.py").write_bytes(template)
    (root / "cbcs" / "project.json").write_text(
        '{"schema_version": 2, "name": "Shop", "default_entry": "main.py", "template": "qt_app"}\n',
        encoding="utf-8",
    )
    forms = root / "forms"
    forms.mkdir(exist_ok=True)
    (forms / "__init__.py").write_text("", encoding="utf-8")
    (forms / "invoice_list_window.py").write_text(
        "from app.qt.QtWidgets import QDialog\n"
        "\n"
        "class InvoiceListWindow(QDialog):\n"
        "    def __init__(self) -> None:\n"
        "        super().__init__()\n"
        "        self.setObjectName('invoiceList')\n"
        "        self.setWindowTitle('Invoices')\n",
        encoding="utf-8",
    )
    dialog = _dialog(tmp_path, root=root, stem="invoice")
    try:
        _choose_make(dialog, "both")
        box = dialog.findChild(QCheckBox, "formBuilder.fromTable.start")
        assert box is not None
        assert box.isEnabled()
        assert box.isChecked()
        assert dialog.start_sentence() == ""
        apply_start_screen(str(root), dialog)
    finally:
        dialog.close()
    source = (root / "main.py").read_text(encoding="utf-8")
    assert "InvoiceListWindow" in source
    ext = Path(sys.executable).resolve().parents[1] / "Ext"
    if ext.is_dir():
        sys.path.insert(0, str(ext))
    sys.path.insert(0, str(root))
    stale = [key for key in sys.modules if key == "forms" or key.startswith("forms.")]
    for key in stale:
        del sys.modules[key]
    try:
        namespace: Dict[str, Any] = {"__name__": "shop_entry"}
        exec(compile(source, str(root / "main.py"), "exec"), namespace)  # noqa: S102
        window = namespace["InvoiceListWindow"]()
        window.show()
        qapp.processEvents()
        visible = [
            item
            for item in qapp.topLevelWidgets()
            if item.isVisible() and type(item).__name__ == "InvoiceListWindow"
        ]
        assert visible, [type(item).__name__ for item in qapp.topLevelWidgets() if item.isVisible()]
    finally:
        if sys.path and sys.path[0] == str(root):
            sys.path.pop(0)


def test_user_main_stays_and_the_box_explains_why(tmp_path: Path, qapp: QApplication) -> None:
    del qapp
    root, _schema = _shop(tmp_path)
    original = "print('mine')\n"
    (root / "main.py").write_text(original, encoding="utf-8")
    (root / "cbcs" / "project.json").write_text(
        '{"schema_version": 2, "name": "Shop", "default_entry": "main.py", "template": "qt_app"}\n',
        encoding="utf-8",
    )
    dialog = _dialog(tmp_path, root=root, stem="invoice")
    try:
        _choose_make(dialog, "both")
        box = dialog.findChild(QCheckBox, "formBuilder.fromTable.start")
        assert box is not None
        assert not box.isEnabled()
        assert not box.isChecked()
        assert dialog.start_sentence() == (
            "main.py has your own code, so it stays as it is. "
            "To start on this screen, open InvoiceListWindow from forms/invoice_list_window.py in main.py."
        )
        apply_start_screen(str(root), dialog)
    finally:
        dialog.close()
    assert (root / "main.py").read_text(encoding="utf-8") == original


def test_a_closed_from_table_dialog_is_destroyed(tmp_path: Path, qapp: QApplication) -> None:
    window = QMainWindow()
    dialog = _dialog(tmp_path, parent=window)
    assert dialog.parent() is window
    dialog.deleteLater()
    qapp.sendPostedEvents(None, enum_value(QEvent.DeferredDelete))
    qapp.processEvents()
    assert wrapper_is_valid(dialog) is False


def test_a_refused_plan_uses_the_main_window_after_the_panel_is_gone(qapp: QApplication) -> None:
    window = QMainWindow()

    class Gone(QWidget):
        def show_status(self, text: str) -> None:
            raise RuntimeError(text)

    report_status(Gone(), window, "Choose another name.")
    qapp.processEvents()
    assert window.statusBar().currentMessage() == "Choose another name."


def test_more_data_actions_has_its_name(qapp: QApplication) -> None:
    del qapp
    host = QWidget()
    body = _create(host)
    more = body.findChild(QPushButton, "formBuilder.data.more")
    assert more is not None
    assert more.accessibleName() == "More data actions"


def test_connection_rows_carry_the_title(tmp_path: Path, qapp: QApplication) -> None:
    del qapp
    from app.features.form_builder.integration.settings_ext.connections_page import ConnectionsPage

    root, _schema = _shop(tmp_path)
    page = ConnectionsPage(None, str(root))
    listed = page.findChild(QListWidget)
    assert listed is not None
    assert listed.count() >= 1
    item = listed.item(0)
    assert item is not None
    assert item.text() == "Shop database"
    row = listed.itemWidget(item)
    assert row is not None
    assert row.accessibleName() == "Shop database"
    page.close()


def test_column_words_sit_under_the_name_in_a_narrow_pane(qapp: QApplication) -> None:
    host = QWidget()
    row = _Row(host, host, Column("integer", "INTEGER", True))
    host.resize(400, 120)
    host.show()
    for width in (184, 236):
        row.setFixedWidth(width)
        row.resize(width, 72)
        qapp.processEvents()
        name = row.findChild(QLabel, "formBuilder.data.columnName")
        words = row.findChild(QLabel, "formBuilder.data.columnWords")
        assert name is not None and words is not None
        assert name.text() == "integer"
        assert words.text() == "whole number"
        assert words.geometry().top() >= name.geometry().bottom() - 1
        assert not name.geometry().intersects(words.geometry())
    row.setFixedWidth(400)
    row.resize(400, 24)
    qapp.processEvents()
    name = row.findChild(QLabel, "formBuilder.data.columnName")
    words = row.findChild(QLabel, "formBuilder.data.columnWords")
    assert name is not None and words is not None
    assert not name.geometry().intersects(words.geometry())
    host.close()


def _lines_host(tmp_path: Path) -> tuple:
    project = tmp_path / "lines"
    _prepare(project)
    folder = project / "cbcs" / "schema"
    folder.mkdir(parents=True)
    (folder / "shop.json").write_text(write_schema(_invoice_schema()), encoding="utf-8")
    install_schema_reader(str(project))
    ui_path = project / "invoice.ui"
    session = FormSession.open(
        _xml(RecordSource("shop", "invoices", "id"), (("QLineEdit", "notesEdit", "notes", ""),)),
        path=str(ui_path),
        scope=FormScope(kind="external", ui_path=str(ui_path), project_root=str(project)),
    )
    host = QWidget()
    host.session = session  # type: ignore[attr-defined]
    connect_form(session, RecordSource("shop", "invoices", "id"))
    return host, session


def _add_line_total(sheet: LinesSheet) -> None:
    sheet._calc_name.setText("line_total")
    sheet._calc_header.setText("Line total")
    sheet._calc_formula.setText("qty * price")
    button = sheet.findChild(QPushButton, "formBuilder.data.linesCalc")
    assert button is not None
    button.click()


def _line_total(session: FormSession) -> str:
    found = dict(lines_on(session.document))
    formulas = []
    for rows in found.values():
        for column in rows.columns:
            if isinstance(column, CalcColumn) and column.name == "line_total":
                formulas.append(column.formula)
    assert formulas
    return formulas[0]


def _dialog(
    tmp_path: Path,
    *,
    root: Path | None = None,
    stem: str = "invoice",
    parent: QWidget | None = None,
    add_connection: object = None,
) -> FromTableDialog:
    project = root
    if project is None:
        project, _schema = _shop(tmp_path)
    tokens = tokens_from_palette(QApplication.instance().palette())  # type: ignore[union-attr]
    return FromTableDialog(
        project_root=str(project),
        stem=stem,
        chrome=chrome_for(tokens),
        date_format="yyyy-MM-dd",
        name_reason=lambda: None,
        parent=parent,
        add_connection=add_connection,  # type: ignore[arg-type]
    )


def _select(dialog: FromTableDialog, table: str) -> None:
    listed = dialog.findChild(QListWidget, "formBuilder.fromTable.tables")
    assert listed is not None
    for index in range(listed.count()):
        item = listed.item(index)
        if item is not None and item.text() == table:
            listed.setCurrentRow(index)
            return
    raise AssertionError(table)


def _choose_make(dialog: FromTableDialog, key: str) -> None:
    make = dialog.findChild(QComboBox, "formBuilder.fromTable.make")
    assert make is not None
    index = make.findData(key)
    assert index >= 0
    make.setCurrentIndex(index)
