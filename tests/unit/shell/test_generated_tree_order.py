"""A generated module sits under its form, and a ui_ helper does not look generated."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.core.models import LoadedProject, ProjectFileEntry, ProjectMetadata  # noqa: E402
from app.qt.QtGui import QColor  # noqa: E402
from app.qt.QtWidgets import QApplication, QTreeWidgetItem  # noqa: E402
from app.shell.main_window import MainWindow  # noqa: E402
from app.shell.tree_item_roles import TREE_ROLE_RELATIVE_PATH  # noqa: E402
from testing.main_window_shutdown import shutdown_main_window_for_test  # noqa: E402

pytestmark = pytest.mark.unit


def _item(window: MainWindow, relative_path: str) -> QTreeWidgetItem:
    for item in window._project_tree_ui_workflow.iter_project_tree_items():  # noqa: SLF001
        if str(item.data(0, TREE_ROLE_RELATIVE_PATH) or "") == relative_path:
            return item
    raise AssertionError(relative_path)


def test_generated_module_sorts_after_its_form_and_a_helper_stays_plain(
    tmp_path: Path, qapp: QApplication
) -> None:
    project_root = tmp_path / "project"
    forms = project_root / "forms"
    forms.mkdir(parents=True)
    (forms / "invoice.ui").write_text("<ui/>\n", encoding="utf-8")
    (forms / "ui_invoice.py").write_text("label = 1\n", encoding="utf-8")
    (forms / "ui_helpers.py").write_text("def label(text):\n    return text\n", encoding="utf-8")
    (forms / "readme.txt").write_text("notes\n", encoding="utf-8")
    entries = [
        ProjectFileEntry(
            relative_path="forms",
            absolute_path=str(forms.resolve()),
            is_directory=True,
        ),
        ProjectFileEntry(
            relative_path="forms/ui_invoice.py",
            absolute_path=str((forms / "ui_invoice.py").resolve()),
            is_directory=False,
        ),
        ProjectFileEntry(
            relative_path="forms/readme.txt",
            absolute_path=str((forms / "readme.txt").resolve()),
            is_directory=False,
        ),
        ProjectFileEntry(
            relative_path="forms/invoice.ui",
            absolute_path=str((forms / "invoice.ui").resolve()),
            is_directory=False,
        ),
        ProjectFileEntry(
            relative_path="forms/ui_helpers.py",
            absolute_path=str((forms / "ui_helpers.py").resolve()),
            is_directory=False,
        ),
    ]
    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    try:
        loaded = LoadedProject(
            project_root=str(project_root.resolve()),
            manifest_path=str((project_root / "cbcs" / "project.json").resolve()),
            metadata=ProjectMetadata(schema_version=1, name="Tree", default_entry="forms/invoice.ui"),
            entries=entries,
        )
        window._loaded_project = loaded  # noqa: SLF001
        window._project_tree_ui_workflow.populate_project_tree(loaded)  # noqa: SLF001
        folder = _item(window, "forms")
        folder.setExpanded(True)
        window._project_tree_presenter.ensure_children_loaded(folder)  # noqa: SLF001
        names = [folder.child(index).text(0) for index in range(folder.childCount())]
        assert names.index("ui_invoice.py") == names.index("invoice.ui") + 1
        tokens = window._shell_theme_workflow.resolve_theme_tokens()  # noqa: SLF001
        muted = QColor(tokens.text_muted).name().lower()
        generated = _item(window, "forms/ui_invoice.py")
        helper = _item(window, "forms/ui_helpers.py")
        assert generated.foreground(0).color().name().lower() == muted
        assert helper.foreground(0).color().name().lower() != muted
    finally:
        shutdown_main_window_for_test(window, qapp)
