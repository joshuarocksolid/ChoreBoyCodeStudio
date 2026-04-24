"""Unit tests for the inline FindReplaceBar widget."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.editors.find_replace_bar import FindOptions, FindReplaceBar


@pytest.fixture
def _ensure_qapp(qapp):  # type: ignore[no-untyped-def]
    return qapp


@pytest.mark.unit
class TestFindOptions:
    def test_defaults(self) -> None:
        opts = FindOptions()
        assert opts.case_sensitive is False
        assert opts.whole_word is False
        assert opts.regex is False

    def test_all_enabled(self) -> None:
        opts = FindOptions(case_sensitive=True, whole_word=True, regex=True)
        assert opts.case_sensitive is True
        assert opts.whole_word is True
        assert opts.regex is True


@pytest.mark.unit
class TestFindReplaceBar:
    def test_initial_state_hidden(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        bar = FindReplaceBar()
        assert not bar.isVisible()

    def test_open_find_shows_bar(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        bar = FindReplaceBar()
        bar.open_find("hello")
        assert bar.isVisible()
        assert bar.find_text() == "hello"
        assert not bar._replace_row.isVisible()

    def test_open_find_replace_shows_replace_row(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        bar = FindReplaceBar()
        bar.open_find_replace("search")
        assert bar.isVisible()
        assert bar.find_text() == "search"
        assert bar._replace_row.isVisible()

    def test_find_options_reflect_toggle_state(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        bar = FindReplaceBar()
        bar._case_btn.setChecked(True)
        bar._word_btn.setChecked(True)
        bar._regex_btn.setChecked(False)
        opts = bar.find_options()
        assert opts.case_sensitive is True
        assert opts.whole_word is True
        assert opts.regex is False

    def test_update_match_count_no_results(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        bar = FindReplaceBar()
        bar.update_match_count(0, 0)
        assert bar._match_count_label.text() == "No results"

    def test_update_match_count_with_results(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        bar = FindReplaceBar()
        bar.update_match_count(3, 12)
        assert bar._match_count_label.text() == "3/12"

    def test_close_hides_bar(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        bar = FindReplaceBar()
        bar.open_find("test")
        assert bar.isVisible()
        bar._on_close()
        assert not bar.isVisible()

    def test_find_requested_signal(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        bar = FindReplaceBar()
        signals: list[tuple] = []
        bar.find_requested.connect(lambda text, opts: signals.append((text, opts)))
        bar._find_input.setText("hello")
        bar._debounce_timer.stop()
        bar._emit_find()
        assert len(signals) == 1
        assert signals[0][0] == "hello"

    def test_find_next_signal(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        bar = FindReplaceBar()
        calls: list[bool] = []
        bar.find_next_requested.connect(lambda: calls.append(True))
        bar._on_find_next()
        assert len(calls) == 1

    def test_find_previous_signal(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        bar = FindReplaceBar()
        calls: list[bool] = []
        bar.find_previous_requested.connect(lambda: calls.append(True))
        bar._on_find_prev()
        assert len(calls) == 1

    def test_replace_signal(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        bar = FindReplaceBar()
        replacements: list[str] = []
        bar.replace_requested.connect(lambda text: replacements.append(text))
        bar._replace_input.setText("world")
        bar._on_replace()
        assert replacements == ["world"]

    def test_replace_all_signal(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        bar = FindReplaceBar()
        replacements: list[str] = []
        bar.replace_all_requested.connect(lambda text: replacements.append(text))
        bar._replace_input.setText("world")
        bar._on_replace_all()
        assert replacements == ["world"]

    def test_chevron_toggles_replace_row(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        bar = FindReplaceBar()
        bar.show()
        assert not bar._replace_row.isVisible()
        assert bar._chevron_btn.text() == "\u25B6"

        bar._chevron_btn.setChecked(True)
        assert bar._replace_row.isVisible()
        assert bar._chevron_btn.text() == "\u25BC"
        assert bar._replace_visible is True

        bar._chevron_btn.setChecked(False)
        assert not bar._replace_row.isVisible()
        assert bar._chevron_btn.text() == "\u25B6"
        assert bar._replace_visible is False

    def test_open_find_resets_chevron(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        bar = FindReplaceBar()
        bar.open_find_replace("test")
        assert bar._chevron_btn.isChecked()
        bar.open_find("test")
        assert not bar._chevron_btn.isChecked()
        assert not bar._replace_row.isVisible()

    def test_open_find_replace_sets_chevron(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        bar = FindReplaceBar()
        bar.open_find_replace("test")
        assert bar._chevron_btn.isChecked()
        assert bar._replace_row.isVisible()

    def test_option_buttons_have_fixed_size(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        bar = FindReplaceBar()
        for btn in [bar._case_btn, bar._word_btn, bar._regex_btn]:
            assert btn.width() == 24
            assert btn.height() == 24

    def test_nav_buttons_have_fixed_size(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        bar = FindReplaceBar()
        for btn in [bar._prev_btn, bar._next_btn]:
            assert btn.width() == 24
            assert btn.height() == 24
