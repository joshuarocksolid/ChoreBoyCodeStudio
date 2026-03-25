"""Unit tests for the SearchSidebarWidget."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtCore import Qt

from app.editors.search_panel import SearchMatch
from app.shell.search_sidebar_widget import (
    ROLE_ABS_PATH,
    ROLE_IS_FILE,
    ROLE_LINE_NUMBER,
    ROLE_LINE_TEXT,
    ROLE_MATCH_COLUMN,
    ROLE_MATCH_COUNT,
    ROLE_MATCH_LENGTH,
    SearchResultDelegate,
    SearchSidebarWidget,
)


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
        assert widget._filters_container.isVisible() is False

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
        widget.show()
        assert widget._replace_visible is False
        widget._toggle_replace(True)
        assert widget._replace_visible is True
        assert widget._replace_container.isVisible() is True
        assert widget._replace_toggle_btn.text() == "\u25BC"
        widget._toggle_replace(False)
        assert widget._replace_visible is False
        assert widget._replace_container.isVisible() is False
        assert widget._replace_toggle_btn.text() == "\u25B6"

    def test_toggle_filters(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        widget = SearchSidebarWidget()
        widget.show()
        assert widget._filters_visible is False
        assert widget._filters_container.isVisible() is False

        widget._toggle_filters(True)
        assert widget._filters_visible is True
        assert widget._filters_container.isVisible() is True

        widget._toggle_filters(False)
        assert widget._filters_visible is False
        assert widget._filters_container.isVisible() is False

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

    def test_on_search_results_stages_results_without_import_error(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        widget = SearchSidebarWidget()
        matches = [
            SearchMatch("src/main.py", "/proj/src/main.py", 10, "hello world", 0, 5),
        ]

        widget._on_search_results(matches, "hello")

        assert widget._pending_results == matches
        assert widget._pending_query == "hello"
        widget._apply_search_results()
        assert widget._results_tree.topLevelItemCount() == 1
        assert "1 result in 1 file" == widget._summary_label.text()

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

    def test_file_items_have_data_roles(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        widget = SearchSidebarWidget()
        widget._pending_results = [
            SearchMatch("src/main.py", "/proj/src/main.py", 10, "hello world", 6, 5),
        ]
        widget._apply_search_results()
        file_item = widget._results_tree.topLevelItem(0)
        assert file_item is not None
        assert file_item.data(0, ROLE_IS_FILE) is True
        assert file_item.data(0, ROLE_MATCH_COUNT) == 1
        assert file_item.data(0, ROLE_ABS_PATH) is None

    def test_match_items_have_data_roles(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        widget = SearchSidebarWidget()
        widget._pending_results = [
            SearchMatch("src/main.py", "/proj/src/main.py", 10, "hello world", 6, 5),
        ]
        widget._apply_search_results()
        file_item = widget._results_tree.topLevelItem(0)
        assert file_item is not None
        line_item = file_item.child(0)
        assert line_item is not None
        assert line_item.data(0, ROLE_ABS_PATH) == "/proj/src/main.py"
        assert line_item.data(0, ROLE_LINE_NUMBER) == 10
        assert line_item.data(0, ROLE_IS_FILE) is False
        assert line_item.data(0, ROLE_LINE_TEXT) == "hello world"
        assert line_item.data(0, ROLE_MATCH_COLUMN) == 6
        assert line_item.data(0, ROLE_MATCH_LENGTH) == 5

    def test_no_results_shows_empty_state(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        widget = SearchSidebarWidget()
        widget.show()
        widget._search_input.setText("something")
        widget._pending_results = []
        widget._apply_search_results()
        assert widget._no_results_label.isVisible() is True
        assert "No results" in widget._no_results_label.text()
        assert widget._results_tree.isVisible() is False

    def test_clear_results(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        widget = SearchSidebarWidget()
        widget._pending_results = [
            SearchMatch("src/main.py", "/proj/src/main.py", 10, "hello world", 0, 5),
        ]
        widget._apply_search_results()
        assert widget._results_tree.topLevelItemCount() == 1

        widget._clear_results()
        assert widget._results_tree.topLevelItemCount() == 0
        assert widget._search_input.text() == ""
        assert widget._summary_label.text() == ""
        assert widget._clear_btn.isVisible() is False

    def test_results_tree_has_delegate(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        widget = SearchSidebarWidget()
        assert isinstance(widget._results_tree.itemDelegate(), SearchResultDelegate)

    def test_apply_theme_tokens(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        widget = SearchSidebarWidget()
        widget.apply_theme_tokens(
            match_bg="#FF0000",
            text_primary="#000000",
            text_muted="#666666",
            badge_bg="#CCCCCC",
        )
        assert widget._delegate._match_bg == "#FF0000"
        assert widget._delegate._text_primary == "#000000"
        assert widget._delegate._text_muted == "#666666"
        assert widget._delegate._badge_bg == "#CCCCCC"

    def test_file_display_shows_basename_and_dir(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        widget = SearchSidebarWidget()
        widget._pending_results = [
            SearchMatch("src/main.py", "/proj/src/main.py", 10, "hello", 0, 5),
        ]
        widget._apply_search_results()
        file_item = widget._results_tree.topLevelItem(0)
        assert file_item is not None
        text = file_item.text(0)
        assert "main.py" in text
        assert "src" in text
