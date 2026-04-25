"""Unit tests for the QuickOpenDialog overlay."""

from __future__ import annotations

import time

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtWidgets import QApplication  # noqa: E402

from app.editors.quick_open import QuickOpenCandidate, rank_candidates as real_rank_candidates
from app.editors.quick_open_dialog import QuickOpenDialog
from app.shell.theme_tokens import ShellThemeTokens


_TOKENS = ShellThemeTokens(
    window_bg="#1F2428",
    panel_bg="#262C33",
    editor_bg="#1B1F23",
    text_primary="#E9ECEF",
    text_muted="#ADB5BD",
    border="#3C434A",
    accent="#5B8CFF",
    gutter_bg="#1F2428",
    gutter_text="#6C757D",
    line_highlight="#252B33",
    is_dark=True,
)


@pytest.fixture
def _ensure_qapp(qapp):  # type: ignore[no-untyped-def]
    return qapp


@pytest.fixture
def sample_candidates() -> list[QuickOpenCandidate]:
    return [
        QuickOpenCandidate(relative_path="src/main.py", absolute_path="/proj/src/main.py"),
        QuickOpenCandidate(relative_path="src/utils.py", absolute_path="/proj/src/utils.py"),
        QuickOpenCandidate(relative_path="tests/test_main.py", absolute_path="/proj/tests/test_main.py"),
        QuickOpenCandidate(relative_path="README.md", absolute_path="/proj/README.md"),
    ]


def _dialog() -> QuickOpenDialog:
    return QuickOpenDialog(tokens=_TOKENS)


def _wait_for_debounce() -> None:
    app = QApplication.instance()
    if app is not None:
        deadline = time.time() + 0.15
        while time.time() < deadline:
            app.processEvents()
            time.sleep(0.01)
        app.processEvents()


@pytest.mark.unit
class TestQuickOpenDialog:
    def test_set_candidates_populates_list(self, _ensure_qapp, sample_candidates) -> None:  # type: ignore[no-untyped-def]
        dialog = _dialog()
        dialog.set_candidates(sample_candidates)
        assert dialog._list_model.rowCount() == 4

    def test_typing_filters_results(self, _ensure_qapp, sample_candidates) -> None:  # type: ignore[no-untyped-def]
        dialog = _dialog()
        dialog.set_candidates(sample_candidates)
        dialog._search_input.setText("main")
        _wait_for_debounce()
        count = dialog._list_model.rowCount()
        assert count == 2

    def test_typing_no_match_shows_empty(self, _ensure_qapp, sample_candidates) -> None:  # type: ignore[no-untyped-def]
        dialog = _dialog()
        dialog.set_candidates(sample_candidates)
        dialog._search_input.setText("zzznomatchzzz")
        _wait_for_debounce()
        assert dialog._list_model.rowCount() == 0

    def test_clearing_search_restores_all(self, _ensure_qapp, sample_candidates) -> None:  # type: ignore[no-untyped-def]
        dialog = _dialog()
        dialog.set_candidates(sample_candidates)
        dialog._search_input.setText("main")
        _wait_for_debounce()
        assert dialog._list_model.rowCount() == 2
        dialog._search_input.clear()
        _wait_for_debounce()
        assert dialog._list_model.rowCount() == 4

    def test_file_selected_signal(self, _ensure_qapp, sample_candidates) -> None:  # type: ignore[no-untyped-def]
        dialog = _dialog()
        dialog.set_candidates(sample_candidates)
        selected_paths: list[str] = []
        dialog.file_selected.connect(lambda path: selected_paths.append(path))
        idx = dialog._list_model.index(0, 0)
        dialog._on_item_activated(idx)
        assert len(selected_paths) == 1

    def test_accept_current_selects_first(self, _ensure_qapp, sample_candidates) -> None:  # type: ignore[no-untyped-def]
        dialog = _dialog()
        dialog.set_candidates(sample_candidates)
        selected_paths: list[str] = []
        dialog.file_selected.connect(lambda path: selected_paths.append(path))
        dialog._accept_current()
        assert len(selected_paths) == 1

    def test_typing_debounces_ranking(self, _ensure_qapp, sample_candidates, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
        calls: list[str] = []

        def fake_rank(candidates, query, *, limit=50):  # type: ignore[no-untyped-def]
            calls.append(query)
            return real_rank_candidates(candidates, query, limit=limit)

        monkeypatch.setattr("app.editors.quick_open_dialog.rank_candidates", fake_rank)
        dialog = _dialog()
        dialog.set_candidates(sample_candidates)
        dialog._search_input.setText("m")
        dialog._search_input.setText("ma")
        dialog._search_input.setText("main")

        assert calls == [""]

        _wait_for_debounce()

        assert calls == ["", "main"]

    def test_refresh_reuses_cached_query_results(self, _ensure_qapp, sample_candidates, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
        calls: list[str] = []

        def fake_rank(candidates, query, *, limit=50):  # type: ignore[no-untyped-def]
            calls.append(query)
            return real_rank_candidates(candidates, query, limit=limit)

        monkeypatch.setattr("app.editors.quick_open_dialog.rank_candidates", fake_rank)
        dialog = _dialog()
        dialog.set_candidates(sample_candidates)
        dialog._search_input.setText("main")
        _wait_for_debounce()

        dialog._refresh_results()

        assert calls == ["", "main"]

    def test_accept_current_flushes_pending_filter(self, _ensure_qapp, sample_candidates) -> None:  # type: ignore[no-untyped-def]
        dialog = _dialog()
        dialog.set_candidates(sample_candidates)
        selected_paths: list[str] = []
        dialog.file_selected.connect(lambda path: selected_paths.append(path))
        dialog._search_input.setText("utils")

        dialog._accept_current()

        assert selected_paths == ["/proj/src/utils.py"]
