"""Performance checks for local history listing and filtering."""

from __future__ import annotations

from pathlib import Path
import time

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtWidgets import QApplication

from app.persistence.local_history_store import LocalHistoryStore
from app.shell.history_restore_picker import HistoryRestorePickerDialog

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module", autouse=True)
def _qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _build_history_store_with_timelines(tmp_path: Path, count: int) -> LocalHistoryStore:
    state_root = tmp_path / "state"
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    store = LocalHistoryStore(state_root=state_root)
    for index in range(count):
        file_path = project_root / "pkg" / f"file_{index:03d}.py"
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(f"VALUE = {index}\n", encoding="utf-8")
        store.create_checkpoint(
            str(file_path.resolve()),
            f"VALUE = {index}\n",
            project_id="proj_demo",
            project_root=str(project_root.resolve()),
            source="save",
            created_at=f"2026-03-24T10:{index % 60:02d}:00",
        )
    return store


def test_list_global_history_files_250_timelines_under_750ms(tmp_path: Path) -> None:
    store = _build_history_store_with_timelines(tmp_path, 250)

    start = time.perf_counter()
    summaries = store.list_global_history_files(project_id="proj_demo")
    elapsed = time.perf_counter() - start

    assert len(summaries) == 250
    assert elapsed <= 0.75


def test_history_restore_picker_filters_250_timelines_under_250ms(tmp_path: Path) -> None:
    store = _build_history_store_with_timelines(tmp_path, 250)
    summaries = store.list_global_history_files(project_id="proj_demo")
    dialog = HistoryRestorePickerDialog()
    dialog.set_entries(summaries)

    dialog._search_input.blockSignals(True)
    dialog._search_input.setText("file_249")
    dialog._search_input.blockSignals(False)
    start = time.perf_counter()
    dialog._refresh_results()
    elapsed = time.perf_counter() - start

    assert dialog._results.topLevelItemCount() == 1
    assert dialog._results.topLevelItem(0).text(0).endswith("file_249.py")
    assert elapsed <= 0.25
