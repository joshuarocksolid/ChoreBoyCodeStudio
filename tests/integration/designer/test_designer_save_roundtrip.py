"""Integration tests for Designer save flow and round-trip persistence."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

import PySide2.QtGui as qt_gui
import PySide2.QtWidgets as qt_widgets

from app.project.project_service import create_blank_project
from app.shell.main_window import MainWindow
from app.designer.io import read_ui_file
from app.designer.model import WidgetNode

pytestmark = pytest.mark.integration


def _collect_widget_class_names(root: WidgetNode) -> set[str]:
    class_names: set[str] = set()
    stack: list[WidgetNode] = [root]
    while stack:
        current = stack.pop()
        class_names.add(current.class_name)
        stack.extend(current.children)
        if current.layout is not None:
            for item in current.layout.items:
                if item.widget is not None:
                    stack.append(item.widget)
    return class_names


def _ensure_qapplication(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    if not hasattr(qt_widgets, "QActionGroup"):
        qt_widgets.QActionGroup = qt_gui.QActionGroup  # type: ignore[attr-defined]
    app = qt_widgets.QApplication.instance()
    if app is None:
        app = qt_widgets.QApplication([])
    return app


def test_designer_changes_mark_dirty_and_save_to_disk(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _ensure_qapplication(monkeypatch)
    state_root = tmp_path / "state"
    state_root.mkdir(parents=True, exist_ok=True)
    project_root = tmp_path / "project"
    create_blank_project(str(project_root.resolve()), project_name="Designer Save")
    ui_file = project_root / "save_test.ui"
    ui_file.write_text(
        (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<ui version=\"4.0\"><class>SaveForm</class>"
            "<widget class=\"QWidget\" name=\"SaveForm\">"
            "<widget class=\"QPushButton\" name=\"pushButton\"/>"
            "</widget>"
            "<resources/><connections/></ui>\n"
        ),
        encoding="utf-8",
    )

    window = MainWindow(state_root=str(state_root.resolve()))
    monkeypatch.setattr(window, "_start_symbol_indexing", lambda _project_root: None)
    assert window._open_project_by_path(str(project_root.resolve())) is True
    assert window._open_file_in_editor(str(ui_file.resolve())) is True

    window._handle_designer_layout_vertical_action()
    active_tab = window._editor_manager.active_tab()
    assert active_tab is not None
    assert active_tab.is_dirty is True

    assert window._editor_tabs_widget is not None
    current_tab_text = window._editor_tabs_widget.tabText(window._editor_tabs_widget.currentIndex())
    assert current_tab_text.endswith(" *")

    assert window._handle_save_action() is True
    active_tab = window._editor_manager.active_tab()
    assert active_tab is not None
    assert active_tab.is_dirty is False

    reloaded_text = ui_file.read_text(encoding="utf-8")
    assert "<layout class=\"QVBoxLayout\"" in reloaded_text
    window.close()


def test_designer_repeated_insertions_recover_after_non_container_selection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _ensure_qapplication(monkeypatch)
    monkeypatch.setattr(
        "app.shell.main_window.QMessageBox.warning",
        lambda *args, **kwargs: qt_widgets.QMessageBox.Discard,
    )
    state_root = tmp_path / "state"
    state_root.mkdir(parents=True, exist_ok=True)
    project_root = tmp_path / "project"
    create_blank_project(str(project_root.resolve()), project_name="Designer Insertions")
    ui_file = project_root / "insertions.ui"
    ui_file.write_text(
        (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<ui version=\"4.0\"><class>InsertionsForm</class>"
            "<widget class=\"QWidget\" name=\"InsertionsForm\"/>"
            "<resources/><connections/></ui>\n"
        ),
        encoding="utf-8",
    )

    window = MainWindow(state_root=str(state_root.resolve()))
    monkeypatch.setattr(window, "_start_symbol_indexing", lambda _project_root: None)
    assert window._open_project_by_path(str(project_root.resolve())) is True
    assert window._open_file_in_editor(str(ui_file.resolve())) is True

    surface = window._active_designer_surface()
    assert surface is not None
    assert surface.model is not None

    # First insertion selects non-container pushButton.
    surface._handle_palette_insert_request("QPushButton")  # type: ignore[attr-defined]
    push_button = surface.model.root_widget.find_by_object_name("pushButton")
    assert push_button is not None
    assert surface.selected_object_name == "pushButton"

    # Second insertion should recover by using a valid container ancestor/root.
    surface._handle_palette_insert_request("QLabel")  # type: ignore[attr-defined]
    label = surface.model.root_widget.find_by_object_name("label")
    assert label is not None
    assert surface.model.root_widget.find_by_object_name("pushButton") is not None

    window.close()


def test_designer_save_roundtrip_preserves_grid_layout_item_attributes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _ensure_qapplication(monkeypatch)
    state_root = tmp_path / "state"
    state_root.mkdir(parents=True, exist_ok=True)
    project_root = tmp_path / "project"
    create_blank_project(str(project_root.resolve()), project_name="Designer Grid Save")
    ui_file = project_root / "grid_layout.ui"
    ui_file.write_text(
        (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<ui version=\"4.0\"><class>GridForm</class>"
            "<widget class=\"QWidget\" name=\"GridForm\">"
            "<layout class=\"QGridLayout\" name=\"gridLayout\">"
            "<item row=\"0\" column=\"0\">"
            "<widget class=\"QLabel\" name=\"label\">"
            "<property name=\"text\"><string>Name</string></property>"
            "</widget>"
            "</item>"
            "<item row=\"1\" column=\"0\" rowspan=\"1\" colspan=\"2\" alignment=\"Qt::AlignCenter\">"
            "<widget class=\"QLineEdit\" name=\"lineEdit\"/>"
            "</item>"
            "</layout>"
            "</widget>"
            "<resources/><connections/></ui>\n"
        ),
        encoding="utf-8",
    )

    window = MainWindow(state_root=str(state_root.resolve()))
    monkeypatch.setattr(window, "_start_symbol_indexing", lambda _project_root: None)
    assert window._open_project_by_path(str(project_root.resolve())) is True
    assert window._open_file_in_editor(str(ui_file.resolve())) is True
    assert window._handle_save_action() is True
    window.close()

    reloaded = read_ui_file(str(ui_file.resolve()))
    assert reloaded.root_widget.layout is not None
    assert len(reloaded.root_widget.layout.items) == 2
    assert reloaded.root_widget.layout.items[0].attributes == {"row": "0", "column": "0"}
    assert reloaded.root_widget.layout.items[1].attributes == {
        "row": "1",
        "column": "0",
        "rowspan": "1",
        "colspan": "2",
        "alignment": "Qt::AlignCenter",
    }


def test_designer_save_roundtrip_persists_tranche_one_palette_widgets(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _ensure_qapplication(monkeypatch)
    monkeypatch.setattr(
        "app.shell.main_window.QMessageBox.warning",
        lambda *args, **kwargs: qt_widgets.QMessageBox.Discard,
    )
    state_root = tmp_path / "state"
    state_root.mkdir(parents=True, exist_ok=True)
    project_root = tmp_path / "project"
    create_blank_project(str(project_root.resolve()), project_name="Designer Palette Tranche One")
    ui_file = project_root / "palette_tranche_one.ui"
    ui_file.write_text(
        (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<ui version=\"4.0\"><class>PaletteTrancheOneForm</class>"
            "<widget class=\"QWidget\" name=\"PaletteTrancheOneForm\">"
            "<layout class=\"QVBoxLayout\" name=\"verticalLayout\"/>"
            "</widget>"
            "<resources/><connections/></ui>\n"
        ),
        encoding="utf-8",
    )

    window = MainWindow(state_root=str(state_root.resolve()))
    monkeypatch.setattr(window, "_start_symbol_indexing", lambda _project_root: None)
    assert window._open_project_by_path(str(project_root.resolve())) is True
    assert window._open_file_in_editor(str(ui_file.resolve())) is True

    surface = window._active_designer_surface()
    assert surface is not None
    assert surface.model is not None

    for class_name in (
        "QSpinBox",
        "QDoubleSpinBox",
        "QSlider",
        "QProgressBar",
        "QDateEdit",
        "QTimeEdit",
        "QDateTimeEdit",
        "QDial",
        "QToolButton",
        "QDialogButtonBox",
    ):
        surface._handle_palette_insert_request(class_name)  # type: ignore[attr-defined]

    assert window._handle_save_action() is True
    window.close()

    reloaded = read_ui_file(str(ui_file.resolve()))
    class_names = _collect_widget_class_names(reloaded.root_widget)
    assert {
        "QSpinBox",
        "QDoubleSpinBox",
        "QSlider",
        "QProgressBar",
        "QDateEdit",
        "QTimeEdit",
        "QDateTimeEdit",
        "QDial",
        "QToolButton",
        "QDialogButtonBox",
    }.issubset(class_names)


def test_designer_save_roundtrip_persists_tranche_two_palette_widgets(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _ensure_qapplication(monkeypatch)
    monkeypatch.setattr(
        "app.shell.main_window.QMessageBox.warning",
        lambda *args, **kwargs: qt_widgets.QMessageBox.Discard,
    )
    state_root = tmp_path / "state"
    state_root.mkdir(parents=True, exist_ok=True)
    project_root = tmp_path / "project"
    create_blank_project(str(project_root.resolve()), project_name="Designer Palette Tranche Two")
    ui_file = project_root / "palette_tranche_two.ui"
    ui_file.write_text(
        (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<ui version=\"4.0\"><class>PaletteTrancheTwoForm</class>"
            "<widget class=\"QWidget\" name=\"PaletteTrancheTwoForm\">"
            "<layout class=\"QVBoxLayout\" name=\"verticalLayout\"/>"
            "</widget>"
            "<resources/><connections/></ui>\n"
        ),
        encoding="utf-8",
    )

    window = MainWindow(state_root=str(state_root.resolve()))
    monkeypatch.setattr(window, "_start_symbol_indexing", lambda _project_root: None)
    assert window._open_project_by_path(str(project_root.resolve())) is True
    assert window._open_file_in_editor(str(ui_file.resolve())) is True

    surface = window._active_designer_surface()
    assert surface is not None
    assert surface.model is not None

    for class_name in (
        "QListWidget",
        "QTreeWidget",
        "QTableWidget",
        "QStackedWidget",
        "QSplitter",
        "QMainWindow",
    ):
        surface._handle_palette_insert_request(class_name)  # type: ignore[attr-defined]

    assert window._handle_save_action() is True
    window.close()

    reloaded = read_ui_file(str(ui_file.resolve()))
    class_names = _collect_widget_class_names(reloaded.root_widget)
    assert {
        "QListWidget",
        "QTreeWidget",
        "QTableWidget",
        "QStackedWidget",
        "QSplitter",
        "QMainWindow",
    }.issubset(class_names)
