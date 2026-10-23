"""New form tab, from-table dialog, and the menu entries that open them."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.qt.QtCore import QPoint, Qt  # noqa: E402
from app.qt.QtTest import QTest  # noqa: E402
from app.qt.QtWidgets import (  # noqa: E402
    QApplication,
    QLabel,
    QMainWindow,
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
from app.shell.menus import MenuCallbacks, build_menu_stubs  # noqa: E402
from app.shell.project_tree_context_menu import show_single_item_tree_context_menu  # noqa: E402
from app.shell.tab_content_providers import TabMatchContext  # noqa: E402
from app.shell.theme_tokens import tokens_from_palette  # noqa: E402

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
    assert shows["customer_id"] == "QSpinBox"
    assert shows["joined"] == "QDateEdit"
    built = dialog.built_form()
    assert 'name="customer_id"' in built.text
    assert "yyyy" in built.text
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
