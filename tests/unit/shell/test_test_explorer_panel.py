"""Unit tests for test explorer panel model and helper behavior."""
from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtWidgets import QApplication

from app.run.pytest_discovery_service import DiscoveredTestNode, DiscoveryResult

pytestmark = pytest.mark.unit


@pytest.fixture
def _ensure_qapp(qapp):  # type: ignore[no-untyped-def]
    return qapp


def _sample_discovery() -> DiscoveryResult:
    return DiscoveryResult(nodes=[
        DiscoveredTestNode(node_id="tests/test_foo.py", name="test_foo.py", file_path="/p/tests/test_foo.py", line_number=0, kind="file"),
        DiscoveredTestNode(node_id="tests/test_foo.py::test_hello", name="test_hello", file_path="/p/tests/test_foo.py", line_number=5, kind="function", parent_id="tests/test_foo.py"),
        DiscoveredTestNode(node_id="tests/test_foo.py::test_goodbye", name="test_goodbye", file_path="/p/tests/test_foo.py", line_number=10, kind="function", parent_id="tests/test_foo.py"),
    ])


# -- pure data tests (no Qt) ------------------------------------------------

def test_discovery_result_kind_filters() -> None:
    result = _sample_discovery()
    assert len(result.file_nodes()) == 1
    assert len(result.function_nodes()) == 2


def test_discovery_result_succeeded_is_true_without_error() -> None:
    result = DiscoveryResult(nodes=[])
    assert result.succeeded is True


def test_discovery_result_succeeded_is_false_with_error() -> None:
    result = DiscoveryResult(error_message="test error")
    assert result.succeeded is False


def test_node_parent_id_links_function_to_file() -> None:
    result = _sample_discovery()
    func = result.function_nodes()[0]
    assert func.parent_id == "tests/test_foo.py"
    assert func.name == "test_hello"


def test_all_outcome_builders_exist() -> None:
    from app.shell.test_explorer_panel import _OUTCOME_BUILDERS
    expected = {"passed", "failed", "skipped", "error", "not_run"}
    assert set(_OUTCOME_BUILDERS.keys()) == expected


def test_all_kind_builders_exist() -> None:
    from app.shell.test_explorer_panel import _KIND_BUILDERS
    expected = {"file", "class", "function"}
    assert set(_KIND_BUILDERS.keys()) == expected


# -- outcome icon cache tests -----------------------------------------------

class TestOutcomeIconCache:
    def test_outcome_icon_returns_qicon(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        from PySide2.QtGui import QIcon
        from app.shell.test_explorer_panel import _OUTCOME_ICON_CACHE, outcome_icon
        _OUTCOME_ICON_CACHE.clear()
        icon = outcome_icon("passed", "#3FB950")
        assert isinstance(icon, QIcon)

    def test_outcome_icon_caches_result(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        from app.shell.test_explorer_panel import _OUTCOME_ICON_CACHE, outcome_icon
        _OUTCOME_ICON_CACHE.clear()
        icon1 = outcome_icon("failed", "#FF6B6B")
        icon2 = outcome_icon("failed", "#FF6B6B")
        assert icon1 is icon2

    def test_outcome_icon_different_color_different_cache(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        from app.shell.test_explorer_panel import _OUTCOME_ICON_CACHE, outcome_icon
        _OUTCOME_ICON_CACHE.clear()
        icon1 = outcome_icon("failed", "#FF6B6B")
        icon2 = outcome_icon("failed", "#E03131")
        assert icon1 is not icon2

    def test_unknown_outcome_falls_back(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        from app.shell.test_explorer_panel import _OUTCOME_ICON_CACHE, outcome_icon
        _OUTCOME_ICON_CACHE.clear()
        icon = outcome_icon("unknown_state", "#AAAAAA")
        assert icon is not None


# -- kind icon cache tests ---------------------------------------------------

class TestKindIconCache:
    def test_kind_icon_returns_qicon(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        from PySide2.QtGui import QIcon
        from app.shell.test_explorer_panel import _KIND_ICON_CACHE, kind_icon
        _KIND_ICON_CACHE.clear()
        icon = kind_icon("file", "#5B8CFF")
        assert isinstance(icon, QIcon)

    def test_kind_icon_caches_result(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        from app.shell.test_explorer_panel import _KIND_ICON_CACHE, kind_icon
        _KIND_ICON_CACHE.clear()
        icon1 = kind_icon("class", "#5B8CFF")
        icon2 = kind_icon("class", "#5B8CFF")
        assert icon1 is icon2


# -- action icon cache tests -------------------------------------------------

class TestActionIconCache:
    def test_action_icon_returns_qicon(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        from PySide2.QtGui import QIcon
        from app.shell.test_explorer_panel import _ACTION_ICON_CACHE, _action_icon
        _ACTION_ICON_CACHE.clear()
        icon = _action_icon("play", "#CED4DA")
        assert isinstance(icon, QIcon)

    def test_action_icon_caches_result(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        from app.shell.test_explorer_panel import _ACTION_ICON_CACHE, _action_icon
        _ACTION_ICON_CACHE.clear()
        icon1 = _action_icon("refresh", "#CED4DA")
        icon2 = _action_icon("refresh", "#CED4DA")
        assert icon1 is icon2


# -- filter toggle tests -----------------------------------------------------

class TestOutcomeFilterToggle:
    def test_initial_count_is_zero(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        from app.shell.test_explorer_panel import _OutcomeFilterToggle
        toggle = _OutcomeFilterToggle("Passed", "shell.testExplorer.filterPassed")
        assert toggle.count() == 0
        assert "0" in toggle.text()

    def test_set_count_updates_text(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        from app.shell.test_explorer_panel import _OutcomeFilterToggle
        toggle = _OutcomeFilterToggle("Failed", "shell.testExplorer.filterFailed")
        toggle.set_count(5)
        assert toggle.count() == 5
        assert "5" in toggle.text()
        assert "Failed" in toggle.text()

    def test_starts_checked(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        from app.shell.test_explorer_panel import _OutcomeFilterToggle
        toggle = _OutcomeFilterToggle("Skipped", "shell.testExplorer.filterSkipped")
        assert toggle.isChecked()


# -- panel construction and state tests --------------------------------------

class TestTestExplorerPanelConstruction:
    def test_panel_creates_without_error(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        from app.shell.test_explorer_panel import TestExplorerPanel
        panel = TestExplorerPanel()
        assert panel.objectName() == "shell.testExplorer"

    def test_panel_tree_has_object_name(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        from app.shell.test_explorer_panel import TestExplorerPanel
        panel = TestExplorerPanel()
        assert panel._tree.objectName() == "shell.testExplorer.tree"

    def test_empty_state_shown_initially(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        from app.shell.test_explorer_panel import TestExplorerPanel
        panel = TestExplorerPanel()
        assert panel._stack_layout.currentWidget() is panel._empty_label

    def test_update_discovery_shows_tree(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        from app.shell.test_explorer_panel import TestExplorerPanel
        panel = TestExplorerPanel()
        panel.update_discovery(_sample_discovery())
        assert panel._stack_layout.currentWidget() is panel._tree

    def test_update_discovery_error_shows_empty(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        from app.shell.test_explorer_panel import TestExplorerPanel
        panel = TestExplorerPanel()
        result = DiscoveryResult(error_message="boom")
        panel.update_discovery(result)
        assert panel._stack_layout.currentWidget() is panel._empty_label
        assert "boom" in panel._empty_label.text()

    def test_update_discovery_empty_result_shows_empty_label(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        from app.shell.test_explorer_panel import TestExplorerPanel
        panel = TestExplorerPanel()
        panel.update_discovery(DiscoveryResult(nodes=[]))
        assert panel._stack_layout.currentWidget() is panel._empty_label

    def test_set_outcomes_enables_rerun_failed(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        from app.shell.test_explorer_panel import TestExplorerPanel
        panel = TestExplorerPanel()
        panel.update_discovery(_sample_discovery())
        panel.set_outcomes({"tests/test_foo.py::test_hello": "failed"})
        assert panel._run_failed_btn.isEnabled()
        assert panel._debug_failed_btn.isEnabled()

    def test_set_outcomes_disables_rerun_when_none_failed(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        from app.shell.test_explorer_panel import TestExplorerPanel
        panel = TestExplorerPanel()
        panel.update_discovery(_sample_discovery())
        panel.set_outcomes({"tests/test_foo.py::test_hello": "passed"})
        assert not panel._run_failed_btn.isEnabled()
        assert not panel._debug_failed_btn.isEnabled()

    def test_failed_node_ids(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        from app.shell.test_explorer_panel import TestExplorerPanel
        panel = TestExplorerPanel()
        panel.update_discovery(_sample_discovery())
        panel.set_outcomes({
            "tests/test_foo.py::test_hello": "failed",
            "tests/test_foo.py::test_goodbye": "passed",
        })
        assert panel.failed_node_ids() == ["tests/test_foo.py::test_hello"]


class TestTestExplorerPanelRunningState:
    def test_set_running_disables_buttons(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        from app.shell.test_explorer_panel import TestExplorerPanel
        panel = TestExplorerPanel()
        panel.set_running(True)
        assert not panel._run_all_btn.isEnabled()
        assert not panel._refresh_btn.isEnabled()

    def test_set_running_false_re_enables(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        from app.shell.test_explorer_panel import TestExplorerPanel
        panel = TestExplorerPanel()
        panel.update_discovery(_sample_discovery())
        panel.set_running(True)
        panel.set_running(False)
        assert panel._run_all_btn.isEnabled()
        assert panel._refresh_btn.isEnabled()

    def test_set_running_updates_status_dot(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        from app.shell.test_explorer_panel import TestExplorerPanel
        panel = TestExplorerPanel()
        panel.set_running(True)
        assert panel._status_dot.property("testState") == "running"

    def test_set_discovering_shows_message(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        from app.shell.test_explorer_panel import TestExplorerPanel
        panel = TestExplorerPanel()
        panel.set_discovering(True)
        assert panel._stack_layout.currentWidget() is panel._empty_label
        assert "Discovering" in panel._empty_label.text()


class TestTestExplorerPanelFilters:
    def test_filter_bar_hidden_when_no_outcomes(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        from app.shell.test_explorer_panel import TestExplorerPanel
        panel = TestExplorerPanel()
        panel.update_discovery(_sample_discovery())
        assert not panel._filter_bar.isVisible()

    def test_filter_bar_visible_after_outcomes(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        from app.shell.test_explorer_panel import TestExplorerPanel
        panel = TestExplorerPanel()
        panel.show()
        panel.update_discovery(_sample_discovery())
        panel.set_outcomes({
            "tests/test_foo.py::test_hello": "passed",
            "tests/test_foo.py::test_goodbye": "failed",
        })
        assert panel._filter_bar.isVisible()

    def test_filter_counts_updated(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        from app.shell.test_explorer_panel import TestExplorerPanel
        panel = TestExplorerPanel()
        panel.update_discovery(_sample_discovery())
        panel.set_outcomes({
            "tests/test_foo.py::test_hello": "passed",
            "tests/test_foo.py::test_goodbye": "failed",
        })
        assert panel._passed_toggle.count() == 1
        assert panel._failed_toggle.count() == 1
        assert panel._skipped_toggle.count() == 0


class TestTestExplorerPanelSummary:
    def test_summary_counts_after_outcomes(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        from app.shell.test_explorer_panel import TestExplorerPanel
        panel = TestExplorerPanel()
        panel.show()
        panel.update_discovery(_sample_discovery())
        panel.set_outcomes({
            "tests/test_foo.py::test_hello": "passed",
            "tests/test_foo.py::test_goodbye": "failed",
        })
        assert panel._count_passed.isVisible()
        assert "1" in panel._count_passed.text()
        assert panel._count_failed.isVisible()
        assert "1" in panel._count_failed.text()

    def test_status_dot_shows_fail_when_any_failed(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        from app.shell.test_explorer_panel import TestExplorerPanel
        panel = TestExplorerPanel()
        panel.update_discovery(_sample_discovery())
        panel.set_outcomes({
            "tests/test_foo.py::test_hello": "passed",
            "tests/test_foo.py::test_goodbye": "failed",
        })
        assert panel._status_dot.property("testState") == "fail"

    def test_status_dot_shows_pass_when_all_passed(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        from app.shell.test_explorer_panel import TestExplorerPanel
        panel = TestExplorerPanel()
        panel.update_discovery(_sample_discovery())
        panel.set_outcomes({
            "tests/test_foo.py::test_hello": "passed",
            "tests/test_foo.py::test_goodbye": "passed",
        })
        assert panel._status_dot.property("testState") == "pass"


class TestTestExplorerApplyTheme:
    def test_apply_theme_clears_icon_caches(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        from app.shell.test_explorer_panel import (
            _OUTCOME_ICON_CACHE, _KIND_ICON_CACHE, _ACTION_ICON_CACHE,
            TestExplorerPanel, outcome_icon, kind_icon, _action_icon,
        )
        _OUTCOME_ICON_CACHE.clear()
        _KIND_ICON_CACHE.clear()
        _ACTION_ICON_CACHE.clear()
        outcome_icon("passed", "#3FB950")
        kind_icon("file", "#5B8CFF")
        _action_icon("play", "#CED4DA")
        assert len(_OUTCOME_ICON_CACHE) > 0
        assert len(_KIND_ICON_CACHE) > 0
        assert len(_ACTION_ICON_CACHE) > 0

        panel = TestExplorerPanel()
        from app.shell.theme_tokens import ShellThemeTokens
        tokens = ShellThemeTokens(
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
            icon_primary="#CED4DA",
            diag_error_color="#FF6B6B",
            diag_warning_color="#E5A100",
            test_passed_color="#3FB950",
            debug_running_color="#3FB950",
        )
        panel.apply_theme(tokens)
        # apply_theme clears caches then rebuilds toolbar action icons (and would
        # repopulate outcome/kind icons when the tree is non-empty).
        assert len(_OUTCOME_ICON_CACHE) == 0
        assert len(_KIND_ICON_CACHE) == 0
        assert len(_ACTION_ICON_CACHE) == 3
