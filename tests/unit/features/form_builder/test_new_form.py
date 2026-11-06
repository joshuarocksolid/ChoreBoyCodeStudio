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
    QCheckBox,
    QComboBox,
    QLabel,
    QLineEdit,
    QListWidget,
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
    # Five templates wrap to a second row at four columns (M5.5c adds the side-buttons dialog).
    QTest.keyClick(panel.card("data_entry"), Qt.Key_Down)
    assert app.focusWidget() is panel.card("dialog_buttons_right")
    QTest.keyClick(panel.card("dialog_buttons_right"), Qt.Key_Down)
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
    assert app.focusWidget() is panel.card("wizard")
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
    name = panel.findChild(QLineEdit, "formBuilder.newForm.name")
    assert name is not None
    assert name.toolTip() == (
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


def test_a_blank_form_opens_with_the_root_selected(tmp_path: Path, qapp: object) -> None:
    """UX-START-004: the root for blank forms."""
    root = tmp_path / "proj"
    (root / "forms").mkdir(parents=True)
    surface = _Surface()
    window = type("Window", (), {})()
    window._loaded_project = _Project(str(root))
    window._editor_tab_factory = _Factory()
    window._editor_tab_workflow = _Workflow()
    window._tab_content_registry = _Registry(surface)
    result = perform_create(window, template="dialog", stem="shop_window", directory=str(root / "forms"))
    assert result.refused is None
    assert surface.selected == "ShopWindow"
    QApplication.processEvents()
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
    name = panel.findChild(QLineEdit, "formBuilder.newForm.name")
    assert name is not None
    assert name.toolTip() == "Creates new_form.ui, ui_new_form.py and new_form_window.py."
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
        "create table customer (id integer primary key, customer_id integer, first_name text, joined date)"
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
    dialog.set_database(str(path), "shop")
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
        label_edit = table.cellWidget(row, 4)
        widget = table.cellWidget(row, 3)
        assert name_item is not None
        assert isinstance(label_edit, QLineEdit)
        assert widget is not None
        labels[name_item.text()] = label_edit.text()
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
    assert dialog.create_button().text() == "Create customer form with 3 fields"
    assert dialog.create_button().isEnabled()
    dialog.set_included("customer_id", False)
    dialog.set_included("first_name", False)
    dialog.set_included("joined", False)
    assert dialog.create_button().text() == "Create customer form with 0 fields"
    assert not dialog.create_button().isEnabled()
    assert dialog.disabled_reason() == "Include at least one column"
    dialog.close()


def test_from_table_uses_singular_for_one_field(tmp_path: Path, qapp: object) -> None:
    del qapp
    dialog = _customer_dialog(tmp_path)
    dialog.set_included("first_name", False)
    dialog.set_included("joined", False)
    assert dialog.create_button().text() == "Create customer form with 1 field"
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
    assert dialog.disabled_reason() == "Choose a connection"
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
    dialog.set_database(str(path), "shop")
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


def test_the_preview_follows_the_dialog_chrome(tmp_path: Path, qapp: object) -> None:
    # The window sheet does not paint the realized form. Fusion stays light (UX-ISO).
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
        dialog.set_database(str(_database(tmp_path)), "shop")
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
        assert light > 0
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


def test_preview_lays_out_at_the_column_width(tmp_path: Path, qapp: object) -> None:
    dialog = FromTableDialog(
        project_root=str(tmp_path),
        stem="customer",
        chrome=chrome_from_values(
            window="#ffffff", panel="#ffffff", text="#000000", muted="#555555", faint="#888888",
            border="#cccccc", accent="#1971c2", row_hover="#eeeeee", input_bg="#ffffff",
            error="#c00000", focus_width=1,
        ),
        date_format="M/d/yy",
        name_reason=lambda: None,
    )
    try:
        dialog.set_database(str(_database(tmp_path)), "shop")
        dialog.resize(960, 560)
        dialog.show()
        for _ in range(4):
            QApplication.processEvents()
        form = dialog._preview_widget
        view = dialog._preview_view
        assert form is not None and view is not None
        assert view.transform().m11() == 1
        off = getattr(getattr(Qt, "ScrollBarPolicy", Qt), "ScrollBarAlwaysOff")
        needed = getattr(getattr(Qt, "ScrollBarPolicy", Qt), "ScrollBarAsNeeded")
        assert enum_value(view.horizontalScrollBarPolicy()) == enum_value(off)
        assert enum_value(view.verticalScrollBarPolicy()) == enum_value(needed)
        assert view.horizontalScrollBar().maximum() == 0
        assert form.width() <= view.viewport().width()
        labels = [label for label in form.findChildren(QLabel) if label.isVisible() and label.text()]
        assert labels
        assert min(label.height() for label in labels) >= 12
        names = (
            "firstButton",
            "previousButton",
            "positionLabel",
            "nextButton",
            "lastButton",
            "newButton",
            "saveButton",
            "revertButton",
            "deleteButton",
            "findButton",
        )
        found = []
        for name in names:
            control = form.findChild(QWidget, name)
            assert control is not None and control.text()
            corner = control.mapTo(form, control.rect().bottomRight())
            assert corner.x() <= form.width()
            assert corner.y() <= form.height()
            found.append(corner.y())
        assert max(found) > min(found)
        assert "First Name" in [label.text() for label in labels]
        dialog.set_included("first_name", False)
        for _ in range(4):
            QApplication.processEvents()
        form = dialog._preview_widget
        view = dialog._preview_view
        assert form is not None and view is not None
        texts = [label.text() for label in form.findChildren(QLabel)]
        assert "First Name" not in texts
        assert "Joined" in texts
        assert view.transform().m11() == 1
        assert form.width() <= view.viewport().width()
        assert view.horizontalScrollBar().maximum() == 0
    finally:
        dialog.close()
    del qapp


def _ink_chrome():
    return chrome_from_values(
        window="#000000",
        panel="#000000",
        text="#ffffff",
        muted="#d0d0d0",
        faint="#d0d0d0",
        border="#ffffff",
        accent="#7cb7ff",
        row_hover="#222222",
        input_bg="#1a1a1a",
        error="#ff8080",
        focus_width=2,
        is_dark=True,
        is_high_contrast=True,
    )


def _light_pixels(widget: QWidget, start: int) -> int:
    image = widget.grab().toImage()
    assert not image.isNull()
    found = 0
    for y in range(image.height()):
        for x in range(start, image.width()):
            if image.pixelColor(x, y).lightness() > 200:
                found += 1
    return found


def test_checkbox_text_is_visible_on_black(tmp_path: Path, qapp: object) -> None:
    dialog = FromTableDialog(
        project_root=str(tmp_path),
        stem="customer",
        chrome=_ink_chrome(),
        date_format="M/d/yy",
        name_reason=lambda: None,
    )
    try:
        dialog.resize(800, 600)
        dialog.show()
        QApplication.processEvents()
        for name in ("formBuilder.fromTable.lines", "formBuilder.fromTable.start"):
            box = dialog.findChild(QCheckBox, name)
            assert box is not None and box.text()
            assert _light_pixels(box, box.width() // 3) > 20
    finally:
        dialog.close()
    del qapp


def test_field_lists_use_the_input_color(tmp_path: Path, qapp: object) -> None:
    dialog = FromTableDialog(
        project_root=str(tmp_path),
        stem="customer",
        chrome=_ink_chrome(),
        date_format="M/d/yy",
        name_reason=lambda: None,
    )
    try:
        dialog.resize(800, 600)
        dialog.show()
        QApplication.processEvents()
        for name in ("formBuilder.fromTable.tables", "formBuilder.fromTable.mapping"):
            listed = dialog.findChild(QWidget, name)
            assert listed is not None
            image = listed.viewport().grab().toImage()  # type: ignore[attr-defined]
            assert not image.isNull()
            color = image.pixelColor(image.width() // 2, image.height() // 2)
            assert color.name().lower() == "#1a1a1a"
    finally:
        dialog.close()
    del qapp


def _theme():
    return tokens_from_palette(QApplication.instance().palette(), force_mode="light")


def _surface(root: Path, window: QWidget):
    from app.features.form_builder.integration.new_form import NewFormSurface
    from app.shell.tab_content_providers import TabSurfaceRequest

    return NewFormSurface(
        TabSurfaceRequest(
            file_path=str(root / "cbcs" / "new-form.cbcs-tab"),
            initial_text="",
            parent=window,
            theme=_theme(),
            create_source_editor=lambda: None,
            open_linked_file=lambda _path: None,
            project_root=str(root),
        ),
        window,
    )


def _shop_dialog(root: Path, stem: str) -> FromTableDialog:
    from tests.form_builder.fixtures.m8.make_shop import build

    data = root / "data"
    data.mkdir(parents=True, exist_ok=True)
    database = data / "shop.db"
    if not database.is_file():
        build(str(database))
    dialog = FromTableDialog(
        project_root=str(root),
        stem=stem,
        chrome=_chrome(),
        date_format="yyyy-MM-dd",
        name_reason=lambda: None,
    )
    dialog.set_database(str(database), "shop")
    return dialog


def _select_table(dialog: FromTableDialog, name: str) -> None:
    tables = dialog.findChild(QListWidget, "formBuilder.fromTable.tables")
    assert tables is not None
    for row in range(tables.count()):
        item = tables.item(row)
        if item is not None and item.text() == name:
            tables.setCurrentRow(row)
            QApplication.processEvents()
            return
    raise AssertionError(name)


def _assert_include_cells(table: QTableWidget) -> None:
    QApplication.processEvents()
    combos = table.findChildren(QComboBox)
    assert len(combos) == table.rowCount()
    for row in range(table.rowCount()):
        item = table.item(row, 0)
        assert item is not None
        state = enum_value(item.checkState())
        assert state in (enum_value(Qt.Checked), enum_value(Qt.Unchecked))
        assert table.cellWidget(row, 0) is None
        index = table.model().index(row, 0)
        assert table.indexWidget(index) is None
        assert table.cellWidget(row, 3) in combos
    for combo in combos:
        assert any(table.cellWidget(row, 3) is combo for row in range(table.rowCount()))


def test_include_cells_stay_checkboxes_for_every_make(tmp_path: Path, qapp: object) -> None:
    del qapp
    dialog = _shop_dialog(tmp_path, "invoice")
    try:
        mapping = dialog.findChild(QTableWidget, "formBuilder.fromTable.mapping")
        make = dialog.findChild(QComboBox, "formBuilder.fromTable.make")
        assert mapping is not None and make is not None
        _select_table(dialog, "customers")
        _select_table(dialog, "invoices")
        mapping.setCurrentCell(0, 0)
        QApplication.processEvents()
        for index in range(make.count()):
            make.setCurrentIndex(index)
            QApplication.processEvents()
            _assert_include_cells(mapping)
    finally:
        dialog.close()


def test_lines_that_cannot_be_planned_disable_create(tmp_path: Path, qapp: object) -> None:
    from app.features.form_builder.engine.data.schema import Column, Reference, Schema, Table
    from app.features.form_builder.engine.project.from_table_plan import (
        CHOOSE_LINK,
        NO_LINE_COLUMNS,
        NO_LINE_KEY,
    )

    del qapp
    root = tmp_path / "shop"
    data = root / "data"
    data.mkdir(parents=True)
    database = data / "shop.db"
    connection = sqlite3.connect(str(database))
    connection.executescript(
        "CREATE TABLE accounts (id INTEGER PRIMARY KEY, name TEXT);"
        "CREATE TABLE transfers ("
        "id INTEGER PRIMARY KEY, "
        "from_id INTEGER REFERENCES accounts(id), "
        "to_id INTEGER REFERENCES accounts(id), "
        "amount REAL);"
        "CREATE TABLE empty_lines (id INTEGER PRIMARY KEY, account_id INTEGER NOT NULL REFERENCES accounts(id));"
    )
    connection.commit()
    connection.close()
    dialog = FromTableDialog(
        project_root=str(root),
        stem="account",
        chrome=_chrome(),
        date_format="yyyy-MM-dd",
        name_reason=lambda: None,
    )
    try:
        dialog.set_database(str(database), "shop")
        _select_table(dialog, "accounts")
        dialog._lines.setChecked(True)
        lines_table = dialog.findChild(QComboBox, "formBuilder.fromTable.linesTable")
        assert lines_table is not None
        lines_table.setCurrentIndex(lines_table.findData("transfers"))
        QApplication.processEvents()
        assert "and lines" in dialog.create_button().text()
        assert not dialog.create_button().isEnabled()
        assert dialog.disabled_reason() == CHOOSE_LINK

        lines_table.setCurrentIndex(lines_table.findData("empty_lines"))
        QApplication.processEvents()
        assert "and lines" in dialog.create_button().text()
        assert dialog.disabled_reason() == NO_LINE_COLUMNS % "empty_lines"

        dialog._connection_name = "shop"
        dialog._use_schema(
            Schema(
                "shop",
                "postgres",
                "PostgreSQL 9.3",
                "2026-11-03T00:00:00",
                "psycopg",
                (
                    Table("accounts", (Column("id", "integer", False), Column("name", "text", True)), key="id"),
                    Table(
                        "transfers",
                        (
                            Column("from_id", "integer", False, references=Reference("accounts", "id")),
                            Column("amount", "numeric", True),
                        ),
                        key=None,
                    ),
                ),
            )
        )
        _select_table(dialog, "accounts")
        dialog._lines.setChecked(True)
        QApplication.processEvents()
        assert "and lines" in dialog.create_button().text()
        assert dialog.disabled_reason() == NO_LINE_KEY % "transfers"
        assert dialog.request() is None
    finally:
        dialog.close()


def test_offline_cache_lists_tables_with_the_footer(tmp_path: Path, qapp: object) -> None:
    from app.features.form_builder.engine.data.connections import Connection, ConnectionSet, save_connections
    from app.features.form_builder.engine.data.schema_cache import store_schema
    from app.features.form_builder.engine.data.schema_sqlite import read_sqlite_file

    del qapp
    root = tmp_path / "proj"
    data = root / "data"
    data.mkdir(parents=True)
    database = data / "shop.db"
    from tests.form_builder.fixtures.m8.make_shop import build

    build(str(database))
    schema = read_sqlite_file(str(database), "shop", read_at="2026-11-03T00:00:00")
    store_schema(str(root), schema)
    database.unlink()
    save_connections(str(root), ConnectionSet((Connection("shop", "Shop database", "sqlite", file="data/shop.db"),)))
    dialog = FromTableDialog(
        project_root=str(root),
        stem="invoice",
        chrome=_chrome(),
        date_format="yyyy-MM-dd",
        name_reason=lambda: None,
    )
    try:
        tables = dialog.findChild(QListWidget, "formBuilder.fromTable.tables")
        reason = dialog.findChild(QLabel, "formBuilder.fromTable.reason")
        assert tables is not None and reason is not None
        names = [tables.item(row).text() for row in range(tables.count())]
        assert "invoices" in names and "customers" in names
        assert "Using columns read" in reason.text()
    finally:
        dialog.close()


def test_no_single_key_and_a_missing_database_disable_create(tmp_path: Path, qapp: object) -> None:
    from app.features.form_builder.engine.data.connections import Connection, ConnectionSet, save_connections
    from app.features.form_builder.engine.project.from_table_plan import NO_KEY

    del qapp
    missing = tmp_path / "missing"
    (missing / "data").mkdir(parents=True)
    save_connections(
        str(missing),
        ConnectionSet((Connection("shop", "Shop database", "sqlite", file="data/gone.db"),)),
    )
    unread = FromTableDialog(
        project_root=str(missing),
        stem="invoice",
        chrome=_chrome(),
        date_format="yyyy-MM-dd",
        name_reason=lambda: None,
    )
    try:
        assert unread.findChild(QListWidget, "formBuilder.fromTable.tables").count() == 0
        assert not unread.create_button().isEnabled()
        assert "is missing" in unread.disabled_reason()
    finally:
        unread.close()

    root = tmp_path / "pair"
    data = root / "data"
    data.mkdir(parents=True)
    database = data / "shop.db"
    connection = sqlite3.connect(str(database))
    connection.execute(
        "CREATE TABLE pair (left_col INTEGER NOT NULL, right_col INTEGER NOT NULL, note TEXT, "
        "PRIMARY KEY (left_col, right_col))"
    )
    connection.commit()
    connection.close()
    dialog = FromTableDialog(
        project_root=str(root),
        stem="pair",
        chrome=_chrome(),
        date_format="yyyy-MM-dd",
        name_reason=lambda: None,
    )
    try:
        dialog.set_database(str(database), "shop")
        assert not dialog.create_button().isEnabled()
        assert dialog.disabled_reason() == NO_KEY % "pair"
    finally:
        dialog.close()


def test_add_connection_keeps_or_selects(tmp_path: Path, qapp: object) -> None:
    from app.features.form_builder.engine.data.connections import Connection, ConnectionSet, save_connections

    del qapp

    def _file(folder: Path, name: str) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(folder / name))
        connection.execute("CREATE TABLE customer (id INTEGER PRIMARY KEY, name TEXT)")
        connection.commit()
        connection.close()

    kept = tmp_path / "kept"
    _file(kept / "data", "shop.db")
    _file(kept / "data", "other.db")
    shop = Connection("shop", "Shop", "sqlite", file="data/shop.db")
    other = Connection("other", "Other", "sqlite", file="data/other.db")
    save_connections(str(kept), ConnectionSet((shop,)))

    def add_other() -> None:
        save_connections(str(kept), ConnectionSet((shop, other)))

    dialog = FromTableDialog(
        project_root=str(kept),
        stem="customer",
        chrome=_chrome(),
        date_format="yyyy-MM-dd",
        name_reason=lambda: None,
        add_connection=add_other,
    )
    try:
        assert dialog.findChild(QComboBox, "formBuilder.fromTable.connection").currentData() == "shop"
        dialog.findChild(QPushButton, "formBuilder.fromTable.addConnection").click()
        QApplication.processEvents()
        assert dialog.findChild(QComboBox, "formBuilder.fromTable.connection").currentData() == "other"
        assert dialog.findChild(QListWidget, "formBuilder.fromTable.tables").count() >= 1
    finally:
        dialog.close()

    fresh = tmp_path / "fresh"
    _file(fresh / "data", "shop.db")

    def add_first() -> None:
        save_connections(str(fresh), ConnectionSet((shop,)))

    opened = FromTableDialog(
        project_root=str(fresh),
        stem="customer",
        chrome=_chrome(),
        date_format="yyyy-MM-dd",
        name_reason=lambda: None,
        add_connection=add_first,
    )
    try:
        assert opened.findChild(QComboBox, "formBuilder.fromTable.connection").count() == 0
        opened.findChild(QPushButton, "formBuilder.fromTable.addConnection").click()
        QApplication.processEvents()
        assert opened.findChild(QComboBox, "formBuilder.fromTable.connection").currentData() == "shop"
        assert opened.findChild(QListWidget, "formBuilder.fromTable.tables").count() == 1
    finally:
        opened.close()


def test_line_memory_is_per_table_and_clears_when_the_schema_changes(tmp_path: Path, qapp: object) -> None:
    from dataclasses import replace

    from app.features.form_builder.engine.data.schema import Column, Schema

    del qapp
    dialog = _shop_dialog(tmp_path, "invoice")
    try:
        _select_table(dialog, "invoices")
        dialog._lines.setChecked(False)
        _select_table(dialog, "customers")
        _select_table(dialog, "invoices")
        assert not dialog._lines.isChecked()
        schema = dialog.schema()
        assert schema is not None
        tables = []
        for table in schema.tables:
            if table.name == "invoices":
                table = replace(table, columns=table.columns + (Column("extra", "TEXT", True),))
            tables.append(table)
        dialog._use_schema(
            Schema(schema.connection, schema.engine, schema.server, schema.read_at, schema.driver, tuple(tables))
        )
        _select_table(dialog, "invoices")
        assert dialog._lines.isChecked()
    finally:
        dialog.close()


def test_packing_list_record_is_created_after_its_list(tmp_path: Path, qapp: object, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.features.form_builder.engine.data.schema import Column, Schema, Table
    from app.features.form_builder.engine.project.create import CreateResult
    from app.features.form_builder.engine.project.forms import FormScope

    del qapp
    calls = []
    focused = []

    def fake_perform(window, *, template, stem, directory, ui_text, first_widget):
        del window, template, directory, ui_text, first_widget
        calls.append(stem)
        forms = tmp_path / "forms"
        return CreateResult(
            (),
            (),
            FormScope(
                kind="project",
                ui_path=str(forms / ("%s.ui" % stem)),
                project_root=str(tmp_path),
                generated_path=str(forms / ("ui_%s.py" % stem)),
                window_path=str(forms / ("%s_window.py" % stem)),
                module_name="forms.ui_%s" % stem,
            ),
            None,
        )

    monkeypatch.setattr("app.features.form_builder.integration.new_form.perform_create", fake_perform)
    (tmp_path / "forms").mkdir()
    window = QWidget()
    surface = _surface(tmp_path, window)
    surface._focus_data = focused.append
    dialog = FromTableDialog(
        project_root=str(tmp_path),
        stem="packing_list",
        chrome=_chrome(),
        date_format="yyyy-MM-dd",
        name_reason=lambda: None,
    )
    try:
        dialog._connection_name = "shop"
        dialog._use_schema(
            Schema(
                "shop",
                "sqlite",
                "",
                "2026-11-03T00:00:00",
                "sqlite",
                (Table("packing_list", (Column("id", "INTEGER", False), Column("title", "TEXT", True)), key="id"),),
            )
        )
        dialog.findChild(QComboBox, "formBuilder.fromTable.make").setCurrentIndex(2)
        surface._create_from_dialog(dialog)
        assert calls == ["packing_list_list", "packing_list"]
        assert os.path.basename(focused[-1]) == "packing_list.ui"
    finally:
        dialog.close()


def test_create_from_dialog_writes_nothing_on_a_clash(tmp_path: Path, qapp: object) -> None:
    del qapp
    root = tmp_path / "proj"
    (root / "forms").mkdir(parents=True)
    (root / "cbcs").mkdir()
    window = QWidget()

    class Project:
        project_root = str(root)

    window._loaded_project = Project()
    surface = _surface(root, window)
    dialog = _shop_dialog(root, "invoice")
    try:
        _select_table(dialog, "invoices")
        dialog.findChild(QComboBox, "formBuilder.fromTable.make").setCurrentIndex(2)
        (root / "forms" / "invoice_list.py").write_text("# kept\n", encoding="utf-8")
        before = sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file())
        surface._create_from_dialog(dialog)
        after = sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file())
        assert after == before
        assert (root / "forms" / "invoice_list.py").read_text(encoding="utf-8") == "# kept\n"
        assert not (root / "forms" / "invoice.ui").is_file()
        status = surface.widget().findChild(QLabel, "formBuilder.newForm.status")
        assert status is not None and "invoice_list.py" in status.text()
    finally:
        dialog.close()


def test_create_from_dialog_undoes_on_the_editor_tab(tmp_path: Path, qapp: object) -> None:
    import json

    from app.features.form_builder.engine.ids import IdAllocator
    from app.features.form_builder.engine.ui4.reader import read_ui
    from app.features.form_builder.engine.ui4.writer import write_ui
    from app.project.project_service import open_project
    from app.shell.main_window import MainWindow
    from testing.main_window_shutdown import shutdown_main_window_for_test

    root = tmp_path / "proj"
    (root / "forms").mkdir(parents=True)
    (root / "main.py").write_text("print(1)\n", encoding="utf-8")
    meta = root / "cbcs"
    meta.mkdir()
    (meta / "project.json").write_text(
        json.dumps({"schema_version": 2, "name": "Shop", "default_entry": "main.py"}) + "\n",
        encoding="utf-8",
    )
    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    dialog = None
    try:
        window._loaded_project = open_project(str(root))
        surface = _surface(root, window)
        dialog = _shop_dialog(root, "customer")
        _select_table(dialog, "customers")
        dialog.findChild(QComboBox, "formBuilder.fromTable.make").setCurrentIndex(0)
        dialog._lines.setChecked(False)
        surface._create_from_dialog(dialog)
        QApplication.processEvents()
        ui_path = os.path.abspath(str(root / "forms" / "customer.ui"))
        tab = window._tab_content_registry.surface_for_path(ui_path)
        assert tab is not None
        assert len(tab.session.log.entries()) == 1
        text = write_ui(tab.session.document).text
        assert "New customer" in text
        assert tab.undo() is True
        assert not tab.session.document.by_name("name")
        disk = read_ui(
            (root / "forms" / "customer.ui").read_text(encoding="utf-8"),
            allocator=IdAllocator(),
        )
        assert "New customer" in write_ui(disk.document).text
    finally:
        if dialog is not None:
            dialog.close()
        shutdown_main_window_for_test(window, qapp)


def test_data_sections_stack_and_the_footer_stays_at_the_bottom(tmp_path: Path, qapp: object) -> None:
    from app.features.form_builder.engine.project.from_table_plan import plan_forms
    from app.features.form_builder.qtside.data_panel.panel import DataPanel
    from app.features.form_builder.qtside.dialogs.table_apply import open_plan
    from app.qt.QtWidgets import QSizePolicy
    from tests.form_builder.engine.test_m8_3d_from_table import _invoice_request, _shop

    del qapp
    root, schema = _shop(tmp_path)
    session = open_plan(plan_forms(_invoice_request(), schema).forms[0], schema, str(root))

    class Bench(QWidget):
        def __init__(self) -> None:
            super().__init__()
            self.session = session

    bench = Bench()
    panel = DataPanel(bench)
    try:
        panel.resize(320, 720)
        panel.show()
        QApplication.processEvents()
        footer = panel.findChild(QWidget, "formBuilder.data.schemaFooter")
        source = panel.findChild(QWidget, "formBuilder.data.sourceLine")
        assert footer is not None and source is not None
        assert enum_value(source.sizePolicy().verticalPolicy()) == enum_value(QSizePolicy.Policy.Maximum)
        assert footer.y() + footer.height() >= panel.height() - 40
        assert source.y() < 80
        assert footer.y() - source.y() > 200
        layout = panel.layout()
        footer_at = layout.indexOf(footer)
        spacer = layout.itemAt(footer_at - 1)
        assert spacer is not None and spacer.spacerItem() is not None
    finally:
        panel.close()
        session.dispose()
