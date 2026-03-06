"""Unit tests for the revamped debug panel widget."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtCore import Qt  # noqa: E402
from PySide2.QtWidgets import QApplication, QTreeWidget  # noqa: E402

from app.debug.debug_models import (  # noqa: E402
    DebugExecutionState,
    DebugFrame,
    DebugSessionState,
    DebugVariable,
)
from app.shell.debug_panel_widget import DebugPanelWidget  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module", autouse=True)
def _qapp(request: pytest.FixtureRequest):  # type: ignore[no-untyped-def]
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture()
def panel() -> DebugPanelWidget:
    return DebugPanelWidget()


def _make_paused_state() -> DebugSessionState:
    state = DebugSessionState()
    state.execution_state = DebugExecutionState.PAUSED
    state.frames = [
        DebugFrame(file_path="/home/user/project/run.py", line_number=3, function_name="<module>"),
        DebugFrame(file_path="/home/user/project/main.py", line_number=10, function_name="start"),
    ]
    state.variables = [
        DebugVariable(name="x", value_repr="42"),
        DebugVariable(name="name", value_repr="'hello'"),
    ]
    return state


class TestInstantiation:
    def test_creates_with_correct_object_name(self, panel: DebugPanelWidget) -> None:
        assert panel.objectName() == "shell.debug.panel"

    def test_contains_tree_widgets(self, panel: DebugPanelWidget) -> None:
        trees = panel.findChildren(QTreeWidget)
        assert len(trees) >= 4


class TestUpdateFromState:
    def test_populates_stack_tree(self, panel: DebugPanelWidget) -> None:
        state = _make_paused_state()
        panel.update_from_state(state)

        tree = panel._stack_tree
        assert tree.topLevelItemCount() == 2
        assert tree.topLevelItem(0).text(0) == "<module>"
        assert "run.py:3" in tree.topLevelItem(0).text(1)

    def test_current_frame_is_bold(self, panel: DebugPanelWidget) -> None:
        state = _make_paused_state()
        panel.update_from_state(state)

        item = panel._stack_tree.topLevelItem(0)
        assert item.font(0).bold() is True

    def test_non_current_frame_is_not_bold(self, panel: DebugPanelWidget) -> None:
        state = _make_paused_state()
        panel.update_from_state(state)

        item = panel._stack_tree.topLevelItem(1)
        assert item.font(0).bold() is False

    def test_populates_variables_tree(self, panel: DebugPanelWidget) -> None:
        state = _make_paused_state()
        panel.update_from_state(state)

        tree = panel._vars_tree
        assert tree.topLevelItemCount() == 2
        assert tree.topLevelItem(0).text(0) == "x"
        assert tree.topLevelItem(0).text(1) == "42"

    def test_clears_previous_state(self, panel: DebugPanelWidget) -> None:
        state = _make_paused_state()
        panel.update_from_state(state)

        empty_state = DebugSessionState()
        empty_state.execution_state = DebugExecutionState.RUNNING
        empty_state.frames = []
        empty_state.variables = []
        panel.update_from_state(empty_state)

        assert panel._stack_tree.topLevelItemCount() == 0
        assert panel._vars_tree.topLevelItemCount() == 0


class TestBreakpoints:
    def test_set_breakpoints_populates_tree(self, panel: DebugPanelWidget) -> None:
        panel.set_breakpoints({
            "/home/user/project/main.py": {5, 10},
            "/home/user/project/util.py": {3},
        })
        tree = panel._bp_tree
        assert tree.topLevelItemCount() == 3

    def test_breakpoints_have_checkboxes(self, panel: DebugPanelWidget) -> None:
        panel.set_breakpoints({"/home/user/project/main.py": {5}})
        item = panel._bp_tree.topLevelItem(0)
        assert item.checkState(0) == Qt.Checked

    def test_set_breakpoints_replaces_previous(self, panel: DebugPanelWidget) -> None:
        panel.set_breakpoints({"/home/user/project/main.py": {5, 10}})
        assert panel._bp_tree.topLevelItemCount() == 2

        panel.set_breakpoints({"/home/user/project/main.py": {5}})
        assert panel._bp_tree.topLevelItemCount() == 1


class TestWatchExpressions:
    def test_add_watch_via_input(self, panel: DebugPanelWidget) -> None:
        panel._watch_input.setText("my_var")
        panel._handle_add_watch()
        assert panel.watch_expressions() == ["my_var"]

    def test_duplicate_watch_not_added(self, panel: DebugPanelWidget) -> None:
        panel._watch_input.setText("my_var")
        panel._handle_add_watch()
        panel._watch_input.setText("my_var")
        panel._handle_add_watch()
        assert panel.watch_expressions() == ["my_var"]

    def test_empty_watch_not_added(self, panel: DebugPanelWidget) -> None:
        panel._watch_input.setText("   ")
        panel._handle_add_watch()
        assert panel.watch_expressions() == []

    def test_set_watch_value(self, panel: DebugPanelWidget) -> None:
        panel._watch_input.setText("x")
        panel._handle_add_watch()
        panel.set_watch_value("x", "42")
        item = panel._watch_tree.topLevelItem(0)
        assert item.text(1) == "42"


class TestSignals:
    def test_navigate_requested_on_stack_click(self, panel: DebugPanelWidget) -> None:
        state = _make_paused_state()
        panel.update_from_state(state)

        signals: list[tuple[str, int]] = []
        panel.navigate_requested.connect(lambda fp, ln: signals.append((fp, ln)))

        item = panel._stack_tree.topLevelItem(0)
        panel._on_stack_item_clicked(item, 0)
        assert len(signals) == 1
        assert signals[0] == ("/home/user/project/run.py", 3)

    def test_navigate_permanent_requested_on_stack_double_click(self, panel: DebugPanelWidget) -> None:
        state = _make_paused_state()
        panel.update_from_state(state)

        signals: list[tuple[str, int]] = []
        panel.navigate_permanent_requested.connect(lambda fp, ln: signals.append((fp, ln)))

        item = panel._stack_tree.topLevelItem(0)
        panel._on_stack_item_double_clicked(item, 0)
        assert signals == [("/home/user/project/run.py", 3)]

    def test_navigate_requested_on_bp_click(self, panel: DebugPanelWidget) -> None:
        panel.set_breakpoints({"/home/user/project/main.py": {5}})

        signals: list[tuple[str, int]] = []
        panel.navigate_requested.connect(lambda fp, ln: signals.append((fp, ln)))

        item = panel._bp_tree.topLevelItem(0)
        panel._on_bp_item_clicked(item, 0)
        assert len(signals) == 1
        assert signals[0] == ("/home/user/project/main.py", 5)

    def test_navigate_permanent_requested_on_bp_double_click(self, panel: DebugPanelWidget) -> None:
        panel.set_breakpoints({"/home/user/project/main.py": {5}})

        signals: list[tuple[str, int]] = []
        panel.navigate_permanent_requested.connect(lambda fp, ln: signals.append((fp, ln)))

        item = panel._bp_tree.topLevelItem(0)
        panel._on_bp_item_double_clicked(item, 0)
        assert signals == [("/home/user/project/main.py", 5)]

    def test_watch_evaluate_requested(self, panel: DebugPanelWidget) -> None:
        panel._watch_input.setText("x + 1")
        panel._handle_add_watch()

        signals: list[str] = []
        panel.watch_evaluate_requested.connect(lambda expr: signals.append(expr))
        panel._auto_evaluate_watches()
        assert signals == ["x + 1"]

    def test_breakpoint_remove_requested(self, panel: DebugPanelWidget) -> None:
        panel.set_breakpoints({"/home/user/project/main.py": {5}})

        signals: list[tuple[str, int]] = []
        panel.breakpoint_remove_requested.connect(lambda fp, ln: signals.append((fp, ln)))

        panel._remove_breakpoint("/home/user/project/main.py", 5)
        assert signals == [("/home/user/project/main.py", 5)]

    def test_command_submitted_on_enter(self, panel: DebugPanelWidget) -> None:
        panel.set_command_input_enabled(True)
        signals: list[str] = []
        panel.command_submitted.connect(lambda text: signals.append(text))
        panel._command_input.setText("next")
        panel._command_input.returnPressed.emit()
        assert signals == ["next"]
        assert panel._command_input.text() == ""

    def test_command_submitted_on_send_click(self, panel: DebugPanelWidget) -> None:
        panel.set_command_input_enabled(True)
        signals: list[str] = []
        panel.command_submitted.connect(lambda text: signals.append(text))
        panel._command_input.setText("continue")
        panel._command_send_btn.click()
        assert signals == ["continue"]
        assert panel._command_input.text() == ""

    def test_empty_command_not_submitted(self, panel: DebugPanelWidget) -> None:
        panel.set_command_input_enabled(True)
        signals: list[str] = []
        panel.command_submitted.connect(lambda text: signals.append(text))
        panel._command_input.setText("   ")
        panel._command_input.returnPressed.emit()
        assert signals == []


class TestOutput:
    def test_append_output(self, panel: DebugPanelWidget) -> None:
        panel.append_output("[debug] Paused at breakpoint")
        text = panel._output_widget.toPlainText()
        assert "[debug] Paused at breakpoint" in text

    def test_clear_output(self, panel: DebugPanelWidget) -> None:
        panel.append_output("line 1")
        panel.clear_output()
        assert panel._output_widget.toPlainText() == ""


class TestVariableExpansion:
    def test_dict_variable_gets_children(self, panel: DebugPanelWidget) -> None:
        state = DebugSessionState()
        state.execution_state = DebugExecutionState.PAUSED
        state.frames = [DebugFrame(file_path="test.py", line_number=1, function_name="f")]
        state.variables = [
            DebugVariable(name="data", value_repr="{'a': 1, 'b': 2}"),
        ]
        panel.update_from_state(state)

        item = panel._vars_tree.topLevelItem(0)
        assert item.childCount() == 2

    def test_list_variable_gets_children(self, panel: DebugPanelWidget) -> None:
        state = DebugSessionState()
        state.execution_state = DebugExecutionState.PAUSED
        state.frames = [DebugFrame(file_path="test.py", line_number=1, function_name="f")]
        state.variables = [
            DebugVariable(name="items", value_repr="[10, 20, 30]"),
        ]
        panel.update_from_state(state)

        item = panel._vars_tree.topLevelItem(0)
        assert item.childCount() == 3
        assert item.child(0).text(0) == "[0]"
        assert item.child(0).text(1) == "10"
