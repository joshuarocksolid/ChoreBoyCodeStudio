"""Unit tests for the QuickOpenDialog overlay."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.editors.quick_open import QuickOpenCandidate
from app.editors.quick_open_dialog import QuickOpenDialog


@pytest.fixture
def _ensure_qapp():
    from PySide2.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def sample_candidates() -> list[QuickOpenCandidate]:
    return [
        QuickOpenCandidate(relative_path="src/main.py", absolute_path="/proj/src/main.py"),
        QuickOpenCandidate(relative_path="src/utils.py", absolute_path="/proj/src/utils.py"),
        QuickOpenCandidate(relative_path="tests/test_main.py", absolute_path="/proj/tests/test_main.py"),
        QuickOpenCandidate(relative_path="README.md", absolute_path="/proj/README.md"),
    ]


@pytest.mark.unit
class TestQuickOpenDialog:
    def test_set_candidates_populates_list(self, _ensure_qapp, sample_candidates) -> None:  # type: ignore[no-untyped-def]
        dialog = QuickOpenDialog()
        dialog.set_candidates(sample_candidates)
        assert dialog._list_model.rowCount() == 4

    def test_typing_filters_results(self, _ensure_qapp, sample_candidates) -> None:  # type: ignore[no-untyped-def]
        dialog = QuickOpenDialog()
        dialog.set_candidates(sample_candidates)
        dialog._search_input.setText("main")
        count = dialog._list_model.rowCount()
        assert count == 2

    def test_typing_no_match_shows_empty(self, _ensure_qapp, sample_candidates) -> None:  # type: ignore[no-untyped-def]
        dialog = QuickOpenDialog()
        dialog.set_candidates(sample_candidates)
        dialog._search_input.setText("zzznomatchzzz")
        assert dialog._list_model.rowCount() == 0

    def test_clearing_search_restores_all(self, _ensure_qapp, sample_candidates) -> None:  # type: ignore[no-untyped-def]
        dialog = QuickOpenDialog()
        dialog.set_candidates(sample_candidates)
        dialog._search_input.setText("main")
        assert dialog._list_model.rowCount() == 2
        dialog._search_input.clear()
        assert dialog._list_model.rowCount() == 4

    def test_file_selected_signal(self, _ensure_qapp, sample_candidates) -> None:  # type: ignore[no-untyped-def]
        dialog = QuickOpenDialog()
        dialog.set_candidates(sample_candidates)
        selected_paths: list[str] = []
        dialog.file_selected.connect(lambda path: selected_paths.append(path))
        idx = dialog._list_model.index(0, 0)
        dialog._on_item_activated(idx)
        assert len(selected_paths) == 1

    def test_accept_current_selects_first(self, _ensure_qapp, sample_candidates) -> None:  # type: ignore[no-untyped-def]
        dialog = QuickOpenDialog()
        dialog.set_candidates(sample_candidates)
        selected_paths: list[str] = []
        dialog.file_selected.connect(lambda path: selected_paths.append(path))
        dialog._accept_current()
        assert len(selected_paths) == 1
