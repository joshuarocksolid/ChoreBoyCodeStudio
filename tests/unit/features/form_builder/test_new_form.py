"""New form tab, from-table dialog, and the menu entries that open them."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.qt.QtCore import QPoint, Qt  # noqa: E402
from app.qt.QtGui import QFont  # noqa: E402
from app.qt.QtTest import QTest  # noqa: E402
from app.qt.QtWidgets import (  # noqa: E402
    QApplication,
    QComboBox,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QTableWidget,
    QTreeWidget,
    QWidget,
)

from app.features.form_builder.engine.project.fs import OsFileSystem  # noqa: E402
from app.features.form_builder.integration.new_form import (  # noqa: E402
    NEW_FORM_PROVIDER_ID,
    new_form_tab_path,
    perform_create,
)
from app.features.form_builder.integration.new_form import NewFormTabProvider  # noqa: E402
from app.features.form_builder.qtside.dialogs.from_table import FromTableDialog  # noqa: E402
from app.features.form_builder.qtside.start.panel import NewFormPanel  # noqa: E402
from app.features.form_builder.qtside.theme.chrome import chrome_from_values  # noqa: E402
from app.qt.qt_compat import enum_value  # noqa: E402
from app.shell.menus import MenuCallbacks, build_menu_stubs  # noqa: E402
from app.shell.project_tree_context_menu import show_single_item_tree_context_menu  # noqa: E402
from app.shell.tab_content_providers import TabMatchContext  # noqa: E402
from app.shell.theme_tokens import tokens_from_palette  # noqa: E402
from app.shell.tree_item_roles import TREE_ROLE_RELATIVE_PATH  # noqa: E402

pytestmark = pytest.mark.unit


def _chrome():
    tokens = tokens_from_palette(QApplication.instance().palette(), force_mode="light")
    return chrome_from_values(
        window=tokens.window_bg,
        panel=tokens.panel_bg,
        text=tokens.text_primary,
        muted=tokens.text_muted,
        faint=tokens.gutter_text,
        border=tokens.border,
        accent=tokens.accent,
        row_hover=tokens.tree_hover_bg,
        input_bg=tokens.input_bg,
        error=tokens.diag_error_color,
        focus_width=tokens.focus_border_width,
    )


def _panel(root: Path, qapp: object) -> NewFormPanel:
    del qapp
    forms = root / "forms"
    forms.mkdir(parents=True, exist_ok=True)
    panel = NewFormPanel(
        project_root=str(root),
        directory=str(forms),
        fs=OsFileSystem(),
        chrome=_chrome(),
    )
    panel.resize(1000, 700)
    panel.show()
    panel.activateWindow()
    QApplication.setActiveWindow(panel)
    QApplication.processEvents()
    return panel


def test_new_form_provider_matches_only_the_virtual_tab() -> None:
    provider = NewFormTabProvider(object())
    context = TabMatchContext(project_root="/proj")
    assert provider.provider_id == NEW_FORM_PROVIDER_ID
    assert provider.matches("/proj/cbcs/new-form.cbcs-tab", context)
    assert not provider.matches("/proj/forms/invoice.ui", context)


def test_arrow_keys_move_between_cards(tmp_path: Path, qapp: object) -> None:
    panel = _panel(tmp_path, qapp)
    app = QApplication.instance()
    assert app is not None
    QTest.keyClick(panel.card("data_entry"), Qt.Key_Right)
    assert app.focusWidget() is panel.card("list_detail")
    assert panel.columns() == 4
    QTest.keyClick(panel.card("data_entry"), Qt.Key_Down)
    assert app.focusWidget() is panel.card("widget")
    panel.close()
    del qapp


def test_arrow_keys_follow_each_groups_grid(tmp_path: Path, qapp: object) -> None:
    panel = _panel(tmp_path, qapp)
    app = QApplication.instance()
    assert app is not None
    QTest.keyClick(panel.card("widget"), Qt.Key_Down)
    assert app.focusWidget() is panel.card("from_table")
    panel.card("dialog").setFocus()
    QTest.keyClick(panel.card("dialog"), Qt.Key_Right)
    assert app.focusWidget() is panel.card("dialog")
    QTest.keyClick(panel.card("main_window"), Qt.Key_Down)
    assert app.focusWidget() is panel.card("adopt")
    panel.close()
    del qapp


def test_enter_on_a_card_asks_to_create(tmp_path: Path, qapp: object) -> None:
    panel = _panel(tmp_path, qapp)
    created: list[str] = []
    panel.create_requested.connect(created.append)
    QTest.keyClick(panel.card("data_entry"), Qt.Key_Return)
    assert created == ["data_entry"]
    panel.close()


def test_the_default_name_is_unique_in_the_folder(tmp_path: Path, qapp: object) -> None:
    forms = tmp_path / "forms"
    forms.mkdir()
    (forms / "new_form.ui").write_text("<ui/>\n", encoding="utf-8")
    panel = _panel(tmp_path, qapp)
    assert panel.stem() == "new_form_2"
    caption = panel.findChild(QLabel, "formBuilder.newForm.caption")
    assert caption is not None
    assert caption.text() == (
        "Creates forms/new_form_2.ui, ui_new_form_2.py and new_form_2_window.py."
    )
    empty = panel.findChild(QLabel, "formBuilder.newForm.recentEmpty")
    assert empty is not None
    assert empty.text() == "Forms you open show up here."
    panel.close()


def test_an_invalid_name_disables_creation(tmp_path: Path, qapp: object) -> None:
    panel = _panel(tmp_path, qapp)
    panel.set_stem("9invoice")
    error = panel.findChild(QLabel, "formBuilder.newForm.nameError")
    assert error is not None
    assert error.text() == "Use letters, digits and _, starting with a letter."
    assert not panel.card("data_entry").isEnabled()
    assert panel.card("adopt").isEnabled()
    created: list[str] = []
    panel.create_requested.connect(created.append)
    QTest.keyClick(panel.card("data_entry"), Qt.Key_Return)
    assert created == []
    panel.close()


class _Project:
    def __init__(self, root: str) -> None:
        self.project_root = root


class _Factory:
    def __init__(self) -> None:
        self.opened: list[str] = []

    def open_file_in_editor(self, path: str) -> None:
        self.opened.append(path)


class _Workflow:
    def __init__(self) -> None:
        self.closed: list[str] = []

    def close_tab_discarding_edits(self, path: str, *, skip_close_blockers: bool = False) -> None:
        del skip_close_blockers
        self.closed.append(path)


class _Surface:
    def __init__(self) -> None:
        self.selected: str | None = None

    def select_object(self, name: str) -> None:
        self.selected = name


class _Registry:
    def __init__(self, surface: _Surface) -> None:
        self._surface = surface

    def surface_for_path(self, path: str) -> _Surface:
        del path
        return self._surface


def test_create_writes_the_form_and_opens_it(tmp_path: Path, qapp: object) -> None:
    root = tmp_path / "proj"
    (root / "forms").mkdir(parents=True)
    factory = _Factory()
    workflow = _Workflow()
    surface = _Surface()
    window = type("Window", (), {})()
    window._loaded_project = _Project(str(root))
    window._editor_tab_factory = factory
    window._editor_tab_workflow = workflow
    window._tab_content_registry = _Registry(surface)
    result = perform_create(
        window,
        template="data_entry",
        stem="invoice",
        directory=str(root / "forms"),
    )
    assert result.refused is None
    names = {os.path.basename(path) for path in result.files}
    assert {"invoice.ui", "ui_invoice.py", "invoice_window.py"} <= names
    assert factory.opened == [os.path.abspath(str(root / "forms" / "invoice.ui"))]
    assert surface.selected == "nameEdit"
    QApplication.processEvents()
    assert workflow.closed == [new_form_tab_path(str(root))]
    del qapp


def test_the_name_label_is_the_fields_buddy(tmp_path: Path, qapp: object) -> None:
    panel = _panel(tmp_path, qapp)
    name = panel.findChild(QLineEdit, "formBuilder.newForm.name")
    assert name is not None
    labels = [label for label in panel.findChildren(QLabel) if label.text() == "Name"]
    assert labels
    assert labels[0].buddy() is name
    hero = panel.findChild(QLabel, "formBuilder.newForm.hero")
    assert hero is not None
    assert enum_value(hero.font().weight()) == enum_value(QFont.DemiBold)
    panel.close()


def test_the_project_root_caption_has_no_folder(tmp_path: Path, qapp: object) -> None:
    panel = _panel(tmp_path, qapp)
    panel.set_directory(str(tmp_path))
    folder = panel.findChild(QComboBox, "formBuilder.newForm.folder")
    assert folder is not None
    assert folder.currentText() == "(project root)"
    caption = panel.findChild(QLabel, "formBuilder.newForm.caption")
    assert caption is not None
    assert caption.text() == "Creates new_form.ui, ui_new_form.py and new_form_window.py."
    panel.close()


def test_a_recent_form_row_opens_on_enter(tmp_path: Path, qapp: object) -> None:
    panel = _panel(tmp_path, qapp)
    opened: list[str] = []
    panel.open_recent_requested.connect(opened.append)
    panel.set_recents((("invoice.ui", "forms/", "forms/invoice.ui"),))
    QApplication.processEvents()
    row = panel.findChild(QWidget, "formBuilder.newForm.recentRow")
    assert row is not None
    row.setFocus()
    QApplication.processEvents()
    app = QApplication.instance()
    assert app is not None
    assert app.focusWidget() is row
    QTest.keyClick(row, Qt.Key_Return)
    assert opened == ["forms/invoice.ui"]
    panel.close()


def test_create_on_a_real_window_refreshes_the_tree(tmp_path: Path, qapp: object) -> None:
    import json

    from app.project.project_service import open_project
    from app.shell.main_window import MainWindow
    from testing.main_window_shutdown import shutdown_main_window_for_test

    root = tmp_path / "proj"
    (root / "forms").mkdir(parents=True)
    (root / "main.py").write_text("print(1)\n", encoding="utf-8")
    meta = root / "cbcs"
    meta.mkdir()
    manifest = meta / "project.json"
    manifest.write_text(
        json.dumps({"schema_version": 2, "name": "Shop", "default_entry": "main.py"}) + "\n",
        encoding="utf-8",
    )
    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    try:
        loaded = open_project(str(root))
        before = manifest.read_text(encoding="utf-8")
        window._loaded_project = loaded  # noqa: SLF001
        window._project_tree_ui_workflow.populate_project_tree(loaded)  # noqa: SLF001
        result = perform_create(
            window,
            template="data_entry",
            stem="invoice",
            directory=str(root / "forms"),
        )
        assert result.refused is None
        QApplication.processEvents()
        presenter = window._project_tree_presenter  # noqa: SLF001
        for item in window._project_tree_ui_workflow.iter_project_tree_items():  # noqa: SLF001
            if str(item.data(0, TREE_ROLE_RELATIVE_PATH) or "") == "forms":
                presenter.ensure_children_loaded(item)
        found = []
        for item in window._project_tree_ui_workflow.iter_project_tree_items():  # noqa: SLF001
            found.append(str(item.data(0, TREE_ROLE_RELATIVE_PATH) or ""))
        assert "forms/invoice.ui" in found
        assert manifest.read_text(encoding="utf-8") == before
        assert (meta / "recent_forms.json").is_file()
    finally:
        shutdown_main_window_for_test(window, qapp)


def _database(root: Path) -> Path:
    folder = root / "data"
    folder.mkdir()
    path = folder / "shop.sqlite"
    connection = sqlite3.connect(path)
    connection.execute(
        "create table customer (customer_id integer, first_name text, joined date)"
    )
    connection.commit()
    connection.close()
    return path


def _customer_dialog(tmp_path: Path) -> FromTableDialog:
    path = _database(tmp_path)
    dialog = FromTableDialog(
        project_root=str(tmp_path),
        stem="customer",
        chrome=_chrome(),
        date_format="M/d/yy",
        name_reason=lambda: None,
    )
    dialog.set_database(str(path))
    return dialog


def test_from_table_maps_columns_to_widgets(tmp_path: Path, qapp: object) -> None:
    del qapp
    dialog = _customer_dialog(tmp_path)
    assert dialog.database_label() == "data/shop.sqlite"
    assert dialog.database_tooltip() == os.path.abspath(str(tmp_path / "data" / "shop.sqlite"))
    table = dialog.findChild(QTableWidget, "formBuilder.fromTable.mapping")
    assert table is not None
    labels = {}
    shows = {}
    for row in range(table.rowCount()):
        name_item = table.item(row, 1)
        label_item = table.item(row, 4)
        widget = table.cellWidget(row, 3)
        assert name_item is not None
        assert label_item is not None
        assert widget is not None
        labels[name_item.text()] = label_item.text()
        shows[name_item.text()] = widget.currentText()  # type: ignore[attr-defined]
    assert labels["customer_id"] == "Customer"
    assert labels["first_name"] == "First Name"
    assert shows["customer_id"] == "Whole number"
    assert shows["joined"] == "Date"
    id_row = next(
        row
        for row in range(table.rowCount())
        if table.item(row, 1) is not None and table.item(row, 1).text() == "customer_id"
    )
    shows_as = table.cellWidget(id_row, 3)
    assert shows_as is not None
    assert shows_as.toolTip() == "QSpinBox"
    built = dialog.built_form()
    assert 'name="customer_id"' in built.text
    assert "yyyy" in built.text
    dialog.resize(960, 560)
    dialog.show()
    QApplication.processEvents()
    header = table.horizontalHeader()
    label_right = header.sectionViewportPosition(4) + header.sectionSize(4)
    assert label_right <= table.viewport().width()
    assert header.sectionSize(4) >= 48
    dialog.close()


def test_from_table_button_names_the_field_count(tmp_path: Path, qapp: object) -> None:
    del qapp
    dialog = _customer_dialog(tmp_path)
    assert dialog.create_button().text() == "Create form with 3 fields"
    assert dialog.create_button().isEnabled()
    dialog.set_included("customer_id", False)
    dialog.set_included("first_name", False)
    dialog.set_included("joined", False)
    assert dialog.create_button().text() == "Create form with 0 fields"
    assert not dialog.create_button().isEnabled()
    assert dialog.disabled_reason() == "Include at least one column"
    dialog.close()


def test_from_table_uses_singular_for_one_field(tmp_path: Path, qapp: object) -> None:
    del qapp
    dialog = _customer_dialog(tmp_path)
    dialog.set_included("first_name", False)
    dialog.set_included("joined", False)
    assert dialog.create_button().text() == "Create form with 1 field"
    dialog.close()


def test_from_table_asks_for_a_database_before_one_is_chosen(tmp_path: Path, qapp: object) -> None:
    del qapp
    dialog = FromTableDialog(
        project_root=str(tmp_path),
        stem="customer",
        chrome=_chrome(),
        date_format="M/d/yy",
        name_reason=lambda: None,
    )
    assert dialog.disabled_reason() == "Choose a SQLite file"
    cancel = dialog.findChild(QPushButton, "formBuilder.fromTable.cancel")
    assert cancel is not None
    assert cancel.text() == "Cancel"
    dialog.show()
    QApplication.processEvents()
    assert dialog.create_button().height() == 28
    assert cancel.x() < dialog.create_button().x()
    dialog.close()


def test_an_integer_primary_key_starts_unchecked(tmp_path: Path, qapp: object) -> None:
    del qapp
    folder = tmp_path / "data"
    folder.mkdir()
    path = folder / "shop.sqlite"
    connection = sqlite3.connect(path)
    connection.execute(
        "create table customer (customer_id integer primary key, name text)"
    )
    connection.commit()
    connection.close()
    dialog = FromTableDialog(
        project_root=str(tmp_path),
        stem="customer",
        chrome=_chrome(),
        date_format="M/d/yy",
        name_reason=lambda: None,
    )
    dialog.set_database(str(path))
    table = dialog.findChild(QTableWidget, "formBuilder.fromTable.mapping")
    assert table is not None
    checks = {}
    for row in range(table.rowCount()):
        name_item = table.item(row, 1)
        include = table.item(row, 0)
        assert name_item is not None
        assert include is not None
        checks[name_item.text()] = enum_value(include.checkState())
    assert checks["customer_id"] == enum_value(Qt.Unchecked)
    assert checks["name"] == enum_value(Qt.Checked)
    dialog.close()


def test_the_preview_stays_on_the_runtime_palette(tmp_path: Path, qapp: object) -> None:
    # CONTRACTS 5.4: chrome rules live on the window; the app sheet is tooltip-only.
    app = QApplication.instance()
    assert app is not None
    window = QWidget()
    window.setStyleSheet(
        "QLabel { color: #ffffff; background: #1e1e1e; }"
        " QCheckBox::indicator { background: #000000; }"
    )
    dialog = FromTableDialog(
        project_root=str(tmp_path),
        stem="customer",
        chrome=chrome_from_values(
            window="#1e1e1e",
            panel="#252526",
            text="#ffffff",
            muted="#bbbbbb",
            faint="#888888",
            border="#444444",
            accent="#5b8cff",
            row_hover="#333333",
            input_bg="#1e1e1e",
            error="#ff6666",
            focus_width=1,
        ),
        date_format="M/d/yy",
        name_reason=lambda: None,
        parent=window,
    )
    try:
        dialog.set_database(str(_database(tmp_path)))
        dialog.resize(960, 560)
        dialog.show()
        app.processEvents()
        form = dialog._preview_widget
        assert form is not None
        assert form.graphicsProxyWidget() is not None
        labels = [label for label in form.findChildren(QLabel) if label.text() == "Customer"]
        assert labels
        image = labels[0].grab().toImage()
        light = 0
        dark = 0
        for y in range(image.height()):
            for x in range(image.width()):
                value = image.pixelColor(x, y).lightness()
                if value > 200:
                    light += 1
                elif value < 80:
                    dark += 1
        assert dark > 0
        assert light > dark
    finally:
        dialog.close()
        window.deleteLater()
    del qapp


def test_card_text_is_available_when_it_does_not_fit(tmp_path: Path, qapp: object) -> None:
    from app.features.form_builder.engine.project.templates import template_for

    panel = _panel(tmp_path, qapp)
    card = panel.card("main_window")
    spec = template_for("main_window")
    assert spec is not None
    assert spec.description in card.toolTip()
    assert card.accessibleDescription() == spec.description
    assert len(spec.description) <= 32
    panel.close()


def test_new_form_menu_is_absent_until_the_feature_sets_it(qapp: object) -> None:
    del qapp
    window = QMainWindow()
    empty = build_menu_stubs(window.menuBar(), callbacks=MenuCallbacks())
    assert empty.action("shell.action.file.newForm") is None
    present = build_menu_stubs(
        window.menuBar(),
        callbacks=MenuCallbacks(on_new_form=lambda: None),
    )
    action = present.action("shell.action.file.newForm")
    assert action is not None
    assert action.text() == "New Form…"
    window.close()


class _TreeWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._project_tree_widget = QTreeWidget(self)
        self._loaded_project = None
        self._tree_clipboard_paths: list[str] = []
        self._effective_shortcuts: dict[str, str] = {}
        self._open_new_form = None
        self._project_tree_ui_workflow = None

    def current_theme_tokens(self):  # type: ignore[no-untyped-def]
        return tokens_from_palette(QApplication.instance().palette(), force_mode="light")


def test_the_tree_menu_offers_new_form_on_a_folder(tmp_path: Path, qapp: object, monkeypatch: pytest.MonkeyPatch) -> None:
    del qapp
    opened: list[str] = []
    window = _TreeWindow()
    window._open_new_form = opened.append  # type: ignore[assignment]

    def _exec(menu, *_args):  # type: ignore[no-untyped-def]
        for action in menu.actions():
            if action.text() == "New Form…":
                return action
        return None

    monkeypatch.setattr("app.shell.project_tree_context_menu.exec_qt", _exec)
    folder = tmp_path / "forms"
    folder.mkdir()
    notes = folder / "notes.txt"
    notes.write_text("x\n", encoding="utf-8")
    show_single_item_tree_context_menu(
        window,
        QPoint(0, 0),
        (str(notes), "forms/notes.txt", False),
    )
    assert opened == [str(folder)]
    window.close()


def test_the_tree_menu_hides_new_form_without_the_callback(
    tmp_path: Path, qapp: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    del qapp
    window = _TreeWindow()
    seen: list[str] = []

    def _exec(menu, *_args):  # type: ignore[no-untyped-def]
        seen.extend(action.text() for action in menu.actions())
        return None

    monkeypatch.setattr("app.shell.project_tree_context_menu.exec_qt", _exec)
    folder = tmp_path / "forms"
    folder.mkdir()
    show_single_item_tree_context_menu(window, QPoint(0, 0), (str(folder), "forms", True))
    assert "New Form…" not in seen
    window.close()


def test_primary_button_text_meets_contrast_on_the_accent() -> None:
    from app.features.form_builder.qtside.theme.chrome import _contrast, on_accent_for

    for accent in ("#1971C2", "#5B8CFF", "#9CC0FF", "#0B5CAD"):
        assert _contrast(accent, on_accent_for(accent)) >= 4.5
