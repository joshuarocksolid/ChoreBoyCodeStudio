"""Unit tests for the global history restore picker."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtWidgets import QApplication

from app.persistence.history_models import LocalHistoryFileSummary
from app.shell.history_restore_picker import HistoryRestorePickerDialog

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module", autouse=True)
def _qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _summary(
    *,
    file_key: str = "file_1",
    display_path: str = "pkg/renamed.py",
    file_path: str = "/tmp/project/pkg/renamed.py",
    relative_path: str = "pkg/renamed.py",
    is_deleted: bool = False,
    path_aliases: tuple[str, ...] = ("pkg/renamed.py", "/tmp/project/pkg/renamed.py"),
) -> LocalHistoryFileSummary:
    return LocalHistoryFileSummary(
        file_key=file_key,
        project_id="proj_demo",
        project_root="/tmp/project",
        file_path=file_path,
        relative_path=relative_path,
        display_path=display_path,
        is_deleted=is_deleted,
        deleted_at=None,
        latest_revision_id=7,
        latest_checkpoint_at="2026-03-24T10:06:00",
        latest_label="Saved Revision",
        latest_source="save",
        checkpoint_count=2,
        path_aliases=path_aliases,
    )


def test_history_restore_picker_filters_using_old_alias_paths() -> None:
    dialog = HistoryRestorePickerDialog()
    dialog.set_entries(
        [
            _summary(path_aliases=("pkg/renamed.py", "/tmp/project/pkg/renamed.py", "pkg/module.py")),
            _summary(file_key="file_2", display_path="other.py", file_path="/tmp/project/other.py", relative_path="other.py"),
        ]
    )

    dialog._search_input.setText("module.py")

    assert dialog._results.topLevelItemCount() == 1
    assert dialog._results.topLevelItem(0).text(0) == "pkg/renamed.py"
    assert dialog._results.topLevelItem(0).text(1) == "Moved/Renamed"


def test_history_restore_picker_marks_deleted_entries() -> None:
    dialog = HistoryRestorePickerDialog()
    dialog.set_entries([_summary(is_deleted=True)])

    assert dialog._results.topLevelItemCount() == 1
    assert dialog._results.topLevelItem(0).text(1) == "Deleted"
