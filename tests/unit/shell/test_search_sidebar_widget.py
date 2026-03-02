"""Unit tests for the SearchSidebarWidget."""

from __future__ import annotations

import pytest

from app.editors.search_panel import SearchMatch
from app.shell.search_sidebar_widget import SearchSidebarWidget


@pytest.fixture
def _ensure_qapp():
    from PySide2.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.mark.unit
class TestSearchSidebarWidget:
    def test_initial_state(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        widget = SearchSidebarWidget()
        assert widget._search_input.text() == ""
        assert widget._results_tree.topLevelItemCount() == 0
        assert widget._replace_container.isVisible() is False

    def test_set_project_root(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        widget = SearchSidebarWidget()
        widget.set_project_root("/some/project")
        assert widget._project_root == "/some/project"

    def test_clear_project_root(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        widget = SearchSidebarWidget()
        widget.set_project_root("/some/project")
        widget.set_project_root(None)
        assert widget._project_root is None

    def test_toggle_replace(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        widget = SearchSidebarWidget()
        assert widget._replace_visible is False
        widget._toggle_replace(True)
        assert widget._replace_visible is True
        widget._toggle_replace(False)
        assert widget._replace_visible is False

    def test_search_options_defaults(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        widget = SearchSidebarWidget()
        opts = widget._search_options()
        assert opts.case_sensitive is False
        assert opts.whole_word is False
        assert opts.regex is False
        assert opts.include_globs is None
        assert opts.exclude_globs is None

    def test_search_options_with_toggles(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        widget = SearchSidebarWidget()
        widget._case_btn.setChecked(True)
        widget._word_btn.setChecked(True)
        opts = widget._search_options()
        assert opts.case_sensitive is True
        assert opts.whole_word is True

    def test_search_options_with_globs(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        widget = SearchSidebarWidget()
        widget._include_input.setText("*.py, *.txt")
        widget._exclude_input.setText("tests/*")
        opts = widget._search_options()
        assert opts.include_globs == ["*.py", " *.txt"]
        assert opts.exclude_globs == ["tests/*"]

    def test_apply_search_results_populates_tree(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        widget = SearchSidebarWidget()
        widget._pending_results = [
            SearchMatch("src/main.py", "/proj/src/main.py", 10, "hello world", 0, 5),
            SearchMatch("src/main.py", "/proj/src/main.py", 20, "hello again", 0, 5),
            SearchMatch("src/utils.py", "/proj/src/utils.py", 5, "hello util", 0, 5),
        ]
        widget._apply_search_results()
        assert widget._results_tree.topLevelItemCount() == 2
        first_file = widget._results_tree.topLevelItem(0)
        assert first_file is not None
        assert first_file.childCount() == 2
        assert "3 result" in widget._summary_label.text()
        assert "2 file" in widget._summary_label.text()

    def test_focus_search(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        widget = SearchSidebarWidget()
        widget.focus_search("test query")
        assert widget._search_input.text() == "test query"

    def test_open_file_at_line_signal(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        widget = SearchSidebarWidget()
        signals: list[tuple] = []
        widget.open_file_at_line.connect(lambda path, line: signals.append((path, line)))

        widget._pending_results = [
            SearchMatch("src/main.py", "/proj/src/main.py", 10, "hello world", 0, 5),
        ]
        widget._apply_search_results()
        file_item = widget._results_tree.topLevelItem(0)
        assert file_item is not None
        line_item = file_item.child(0)
        assert line_item is not None
        widget._on_result_activated(line_item)
        assert len(signals) == 1
        assert signals[0] == ("/proj/src/main.py", 10)
