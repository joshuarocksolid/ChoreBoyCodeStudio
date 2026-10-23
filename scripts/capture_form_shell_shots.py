from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

from app.features.form_builder.integration.problems_bridge import to_code_diagnostics
from app.project.project_service import create_blank_project
from app.qt.QtCore import QPoint
from app.qt.QtGui import QPixmap
from app.qt.QtWidgets import QApplication, QMenu, QSplitter, QTreeWidget, QTreeWidgetItem
from app.shell.editor_tab_page import EditorTabPage
from app.shell.main_window import MainWindow
from testing.main_window_shutdown import shutdown_main_window_for_test
from testing.main_window_test_helpers import stop_main_window_timers

_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Invoice</class>
 <widget class="QWidget" name="Invoice">
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QPushButton" name="okButton">
     <property name="text">
      <string>Old</string>
     </property>
     <property name="text">
      <string>OK</string>
     </property>
    </widget>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""

_OUT = Path(os.environ.get("CBCS_FB_SCREENSHOT_DIR") or "/opt/cursor/artifacts")


def _walk(tree: QTreeWidget) -> list[QTreeWidgetItem]:
    found: list[QTreeWidgetItem] = []

    def walk(item: QTreeWidgetItem) -> None:
        found.append(item)
        for index in range(item.childCount()):
            child = item.child(index)
            if child is not None:
                walk(child)

    for index in range(tree.topLevelItemCount()):
        top = tree.topLevelItem(index)
        if top is not None:
            walk(top)
    return found


def _form_problem(tree: QTreeWidget) -> str:
    rows = []
    for item in _walk(tree):
        location = item.text(2)
        code = item.text(3)
        rows.append("%s | %s" % (location, code))
        if code.startswith("Form") and location == "okButton":
            return code
    raise RuntimeError("no form problem row: %s" % rows)


def _save(image: QPixmap, name: str) -> None:
    _OUT.mkdir(parents=True, exist_ok=True)
    path = _OUT / name
    if not image.save(str(path)):
        raise RuntimeError("could not write %s" % path)
    print("%s %dx%d" % (path, image.width(), image.height()), flush=True)


def _capture(window: MainWindow, app: QApplication, project: Path, form: Path) -> None:
    assert window._editor_tab_factory.open_file_in_editor(str(form)) is True
    window._run_event_workflow.focus_problems_tab()
    splitter = window.findChild(QSplitter, "shell.verticalSplitter")
    assert splitter is not None
    splitter.setSizes([520, 280])
    app.processEvents()
    surface = window._tab_content_registry.surface_for_path(str(form))
    assert surface is not None
    # Project open clears the panel on a later turn. Publish after that settles.
    rows = to_code_diagnostics(str(form), surface._problems._store.all())
    window._problems_controller.apply_lint_diagnostics_result(str(form), rows)
    panel = window._problems_panel
    assert panel is not None
    tree = panel.findChild(QTreeWidget, "shell.problemsPanel.tree")
    assert tree is not None
    code = _form_problem(tree)
    print("problem", code, flush=True)
    _save(panel.grab(), "form-problems-panel-form-fb007-okButton.png")

    assert window._save_workflow.handle_save_action() is True
    generated = project / "forms" / "ui_invoice.py"
    notice = surface.content_source().save_notice
    assert generated.is_file(), (notice, list((project / "forms").iterdir()))
    assert window._editor_tab_factory.open_file_in_editor(str(generated)) is True
    app.processEvents()
    tabs = window._editor_tabs_widget
    assert tabs is not None
    page = tabs.currentWidget()
    assert isinstance(page, EditorTabPage)
    bar = page.generated_bar
    opened = window._editor_manager.get_tab(str(generated))
    assert bar.isVisible(), (
        None if opened is None else opened.generated,
        generated.read_text(encoding="utf-8")[:500],
    )
    _save(window.grab(), "generated-ui-invoice-banner.png")

    assert window._editor_tab_factory.open_file_in_editor(str(form)) is True
    app.processEvents()
    menu = window.findChild(QMenu, "shell.menu.form")
    assert menu is not None
    action = menu.menuAction()
    assert action is not None
    bar_widget = window.menuBar()
    corner = bar_widget.mapToGlobal(bar_widget.actionGeometry(action).bottomLeft())
    menu.popup(QPoint(corner.x(), corner.y()))
    app.processEvents()
    assert menu.isVisible()
    _save(menu.grab(), "form-menu-open.png")
    menu.close()


def main() -> None:
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication([])
    root = Path(tempfile.mkdtemp(prefix="cbcs-form-shots-"))
    project = root / "project"
    create_blank_project(str(project), project_name="Forms")
    forms = project / "forms"
    forms.mkdir(parents=True, exist_ok=True)
    form = forms / "invoice.ui"
    form.write_text(_FORM, encoding="utf-8")
    window = MainWindow(state_root=str(root / "state"))
    try:
        stop_main_window_timers(window)
        window._intelligence_cache_workflow.start_symbol_indexing = lambda *_args, **_kwargs: None  # type: ignore[method-assign]
        window._shell_theme_workflow.apply_theme_styles()
        window.resize(1280, 800)
        window.show()
        app.processEvents()
        assert window._file_project_commands_workflow.open_project_by_path(str(project)) is True
        deadline = time.perf_counter() + 2.0
        while time.perf_counter() < deadline:
            app.processEvents()
            if getattr(window, "_loaded_project", None) is not None:
                break
            time.sleep(0.02)
        for _ in range(20):
            app.processEvents()
        _capture(window, app, project, form)
    finally:
        shutdown_main_window_for_test(window, app)
        print("done", flush=True)


if __name__ == "__main__":
    main()
