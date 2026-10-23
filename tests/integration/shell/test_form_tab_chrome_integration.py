"""A form tab in the real shell: the Form menu between Run and View, and the selection in the status bar."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.features.form_builder.install import form_builder_enabled  # noqa: E402
from app.project.project_service import create_blank_project  # noqa: E402
from app.qt.QtCore import Qt  # noqa: E402
from app.qt.QtWidgets import QTreeWidget  # noqa: E402
from app.shell.main_window import MainWindow  # noqa: E402
from testing.main_window_shutdown import shutdown_main_window_for_test  # noqa: E402
from testing.main_window_test_helpers import prepare_main_window_for_test  # noqa: E402

pytestmark = pytest.mark.integration

needs_form_builder = pytest.mark.skipif(not form_builder_enabled(), reason="the form builder needs PySide6")

_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Invoice</class>
 <widget class="QWidget" name="Invoice">
  <property name="geometry">
   <rect>
    <x>0</x>
    <y>0</y>
    <width>400</width>
    <height>300</height>
   </rect>
  </property>
  <layout class="QFormLayout" name="formLayout">
   <item row="0" column="0">
    <widget class="QLabel" name="nameLabel">
     <property name="text">
      <string>Name</string>
     </property>
    </widget>
   </item>
   <item row="0" column="1">
    <widget class="QLineEdit" name="name"/>
   </item>
   <item row="1" column="0">
    <widget class="QLabel" name="emailLabel">
     <property name="text">
      <string>Email</string>
     </property>
    </widget>
   </item>
   <item row="1" column="1">
    <widget class="QLineEdit" name="email"/>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


def _window(tmp_path: Path, app):  # type: ignore[no-untyped-def]
    project_root = tmp_path / "project"
    create_blank_project(str(project_root.resolve()), project_name="Forms")
    report = project_root / "report.py"
    report.write_text("print('v1')\n", encoding="utf-8")
    form = project_root / "invoice.ui"
    form.write_text(_FORM, encoding="utf-8")
    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    prepare_main_window_for_test(window, app=app)
    window.resize(1400, 900)
    window.show()
    assert window._file_project_commands_workflow.open_project_by_path(str(project_root.resolve())) is True
    return window, str(report.resolve()), str(form.resolve())


def _menu_titles(window: MainWindow) -> list[str]:
    return [action.text().replace("&", "") for action in window.menuBar().actions() if action.isVisible()]


@needs_form_builder
def test_form_menu_shows_between_run_and_view_only_on_the_form_tab(tmp_path: Path, shell_qapp) -> None:  # type: ignore[no-untyped-def]
    window, report, form = _window(tmp_path, shell_qapp)
    assert window._editor_tab_factory.open_file_in_editor(report) is True
    assert "Form" not in _menu_titles(window)

    assert window._editor_tab_factory.open_file_in_editor(form) is True
    titles = _menu_titles(window)
    index = titles.index("Form")
    assert titles[index - 1 : index + 2] == ["Run", "Form", "View"]

    assert window._editor_tab_factory.open_file_in_editor(report) is True
    assert "Form" not in _menu_titles(window)
    shutdown_main_window_for_test(window, shell_qapp)


def test_without_the_form_builder_there_is_no_form_menu(tmp_path: Path, shell_qapp, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("CBCS_FORM_BUILDER", "0")
    window, _report, form = _window(tmp_path, shell_qapp)
    assert window._editor_tab_factory.open_file_in_editor(form) is True

    assert window._menu_registry.menu("shell.menu.form") is None
    assert "Form" not in [action.text().replace("&", "") for action in window.menuBar().actions()]
    shutdown_main_window_for_test(window, shell_qapp)


@needs_form_builder
def test_shell_toggle_source_switches_the_form_tab(tmp_path: Path, shell_qapp) -> None:  # type: ignore[no-untyped-def]
    window, _report, form = _window(tmp_path, shell_qapp)
    assert window._editor_tab_factory.open_file_in_editor(form) is True
    source = window._tab_content_registry.surface_for_path(form).content_source()
    toggle = window._menu_registry.action("shell.action.view.markdownTogglePreview")

    assert toggle.isEnabled() is True
    toggle.trigger()
    assert source.mode == "xml"
    toggle.trigger()
    assert source.mode == "visual"
    shutdown_main_window_for_test(window, shell_qapp)


@needs_form_builder
def test_editor_status_reads_the_selection_on_a_form_tab_and_ln_col_on_code(tmp_path: Path, shell_qapp) -> None:  # type: ignore[no-untyped-def]
    window, report, form = _window(tmp_path, shell_qapp)
    assert window._editor_tab_factory.open_file_in_editor(report) is True
    assert window._editor_tab_factory.open_file_in_editor(form) is True
    surface = window._tab_content_registry.surface_for_path(form)
    tree = surface.widget().findChild(QTreeWidget, "formBuilder.structure")
    assert tree is not None
    matches = tree.findItems("QLineEdit  email", Qt.MatchFlag.MatchExactly | Qt.MatchFlag.MatchRecursive, 0)
    assert len(matches) == 1

    tree.setCurrentItem(matches[0])
    assert window._status_controller.editor_status_text() == "email · Line edit · row 2 of the form layout"

    assert window._editor_tab_factory.open_file_in_editor(report) is True
    assert window._status_controller.editor_status_text() == "Editor: report.py | Ln 1, Col 1 | saved"

    assert window._editor_tab_factory.open_file_in_editor(form) is True
    assert window._status_controller.editor_status_text() == "email · Line edit · row 2 of the form layout"
    shutdown_main_window_for_test(window, shell_qapp)
