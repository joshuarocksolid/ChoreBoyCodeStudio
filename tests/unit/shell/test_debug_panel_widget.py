"""Unit tests for the structured debug panel widget."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtCore import Qt  # noqa: E402
from PySide2.QtWidgets import QApplication, QTreeWidget  # noqa: E402

from app.debug.debug_breakpoints import build_breakpoint  # noqa: E402
from app.debug.debug_models import (  # noqa: E402
    DebugExecutionState,
    DebugFrame,
    DebugScope,
    DebugSessionState,
    DebugThread,
    DebugVariable,
    DebugWatchResult,
)
from app.shell.debug_panel_widget import DebugPanelWidget  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module", autouse=True)
def _qapp(qapp):  # type: ignore[no-untyped-def]
    return qapp


@pytest.fixture()
def panel() -> DebugPanelWidget:
    return DebugPanelWidget()


def _make_paused_state(*, load_child_reference: bool = True) -> DebugSessionState:
    variables_by_reference = {
        1: [
            DebugVariable(name="x", value_repr="42", type_name="int"),
            DebugVariable(
                name="data",
                value_repr="{...}",
                type_name="dict",
                variables_reference=2,
                named_child_count=1,
            ),
        ]
    }
    if load_child_reference:
        variables_by_reference[2] = [
            DebugVariable(name="answer", value_repr="42", type_name="int"),
        ]
    return DebugSessionState(
        execution_state=DebugExecutionState.PAUSED,
        last_message="Paused at breakpoint.",
        stop_reason="breakpoint",
        threads=[
            DebugThread(thread_id=1, name="MainThread", is_current=True),
            DebugThread(thread_id=2, name="worker", is_current=False),
        ],
        selected_thread_id=1,
        frames=[
            DebugFrame(
                file_path="/home/user/project/run.py",
                line_number=3,
                function_name="<module>",
                frame_id=101,
                thread_id=1,
            ),
            DebugFrame(
                file_path="/home/user/project/main.py",
                line_number=10,
                function_name="start",
                frame_id=102,
                thread_id=1,
            ),
        ],
        selected_frame_id=101,
        scopes=[DebugScope(name="Locals", variables_reference=1)],
        variables_by_reference=variables_by_reference,
        watch_results={"x + 1": DebugWatchResult(expression="x + 1", value_repr="43", type_name="int")},
        breakpoints=[
            build_breakpoint("/home/user/project/main.py", 5, verified=True),
        ],
    )


def test_creates_with_correct_object_name(panel: DebugPanelWidget) -> None:
    assert panel.objectName() == "shell.debug.panel"


def test_contains_expected_tree_widgets(panel: DebugPanelWidget) -> None:
    trees = panel.findChildren(QTreeWidget)
    assert len(trees) >= 5


def test_update_from_state_populates_threads_stack_variables_and_breakpoints(panel: DebugPanelWidget) -> None:
    state = _make_paused_state()
    panel._watch_input.setText("x + 1")
    panel._handle_add_watch()

    panel.update_from_state(state)
    panel.set_breakpoints(state.breakpoints)

    assert panel._threads_tree.topLevelItemCount() == 2
    assert panel._threads_tree.topLevelItem(0).text(0) == "MainThread (current)"

    assert panel._stack_tree.topLevelItemCount() == 2
    assert panel._stack_tree.topLevelItem(0).text(0) == "<module>"
    assert panel._stack_tree.topLevelItem(0).font(0).bold() is True
    assert panel._stack_tree.topLevelItem(1).font(0).bold() is False

    assert panel._vars_tree.topLevelItemCount() == 1
    scope_item = panel._vars_tree.topLevelItem(0)
    assert scope_item.text(0) == "Locals"
    assert scope_item.childCount() == 2
    assert scope_item.child(0).text(0) == "x"
    assert scope_item.child(1).child(0).text(0) == "answer"

    assert panel._watch_tree.topLevelItem(0).text(1) == "43"

    bp_item = panel._bp_tree.topLevelItem(0)
    assert bp_item.text(0) == "main.py:5"
    assert bp_item.text(1) == "Verified"
    assert bp_item.checkState(0) == Qt.Checked


def test_update_from_state_clears_previous_data_when_session_running(panel: DebugPanelWidget) -> None:
    panel.update_from_state(_make_paused_state())

    running_state = DebugSessionState(
        execution_state=DebugExecutionState.RUNNING,
        last_message="Debug execution running.",
    )
    panel.update_from_state(running_state)

    assert panel._stack_tree.topLevelItemCount() == 0
    assert panel._vars_tree.topLevelItemCount() == 0


def test_set_breakpoints_replaces_previous_breakpoint_list(panel: DebugPanelWidget) -> None:
    panel.set_breakpoints(
        [
            build_breakpoint("/home/user/project/main.py", 5),
            build_breakpoint("/home/user/project/main.py", 10),
        ]
    )
    assert panel._bp_tree.topLevelItemCount() == 2

    panel.set_breakpoints([build_breakpoint("/home/user/project/main.py", 5)])
    assert panel._bp_tree.topLevelItemCount() == 1


def test_breakpoint_label_includes_condition_and_hit_count(panel: DebugPanelWidget) -> None:
    panel.set_breakpoints(
        [
            build_breakpoint(
                "/home/user/project/main.py",
                12,
                condition="value > 10",
                hit_condition=3,
                verified=False,
                verification_message="Pending verify",
            )
        ]
    )

    item = panel._bp_tree.topLevelItem(0)
    assert item.text(0) == "main.py:12 [cond, hit 3]"
    assert item.text(1) == "Pending verify"


def test_add_watch_ignores_duplicates_and_empty_values(panel: DebugPanelWidget) -> None:
    panel._watch_input.setText("my_var")
    panel._handle_add_watch()
    panel._watch_input.setText("my_var")
    panel._handle_add_watch()
    panel._watch_input.setText("   ")
    panel._handle_add_watch()

    assert panel.watch_expressions() == ["my_var"]


def test_auto_evaluate_watches_only_once_for_same_stop(panel: DebugPanelWidget) -> None:
    panel._watch_input.setText("x + 1")
    panel._handle_add_watch()
    signals: list[str] = []
    panel.watch_evaluate_requested.connect(lambda expr: signals.append(expr))

    state = _make_paused_state()
    panel.update_from_state(state)
    panel.update_from_state(state)

    assert signals == ["x + 1"]


def test_stack_click_emits_frame_selection_and_navigation(panel: DebugPanelWidget) -> None:
    panel.update_from_state(_make_paused_state())
    frame_signals: list[int] = []
    navigate_signals: list[tuple[str, int]] = []
    panel.frame_selected_requested.connect(lambda frame_id: frame_signals.append(frame_id))
    panel.navigate_requested.connect(lambda file_path, line_number: navigate_signals.append((file_path, line_number)))

    item = panel._stack_tree.topLevelItem(0)
    panel._on_stack_item_clicked(item, 0)

    assert frame_signals == [101]
    assert navigate_signals == [("/home/user/project/run.py", 3)]


def test_stack_double_click_emits_permanent_navigation(panel: DebugPanelWidget) -> None:
    panel.update_from_state(_make_paused_state())
    signals: list[tuple[str, int]] = []
    panel.navigate_permanent_requested.connect(lambda file_path, line_number: signals.append((file_path, line_number)))

    item = panel._stack_tree.topLevelItem(0)
    panel._on_stack_item_double_clicked(item, 0)

    assert signals == [("/home/user/project/run.py", 3)]


def test_variable_expand_requested_for_unloaded_reference(panel: DebugPanelWidget) -> None:
    panel.update_from_state(_make_paused_state(load_child_reference=False))
    signals: list[int] = []
    panel.variable_expand_requested.connect(lambda reference: signals.append(reference))

    scope_item = panel._vars_tree.topLevelItem(0)
    variable_item = scope_item.child(1)
    panel._on_variable_item_expanded(variable_item)

    assert signals == [2]
    assert 2 in panel._expanded_variable_references


def test_breakpoint_item_change_emits_toggle_request(panel: DebugPanelWidget) -> None:
    panel.set_breakpoints([build_breakpoint("/home/user/project/main.py", 5)])
    signals: list[tuple[str, int, bool]] = []
    panel.breakpoint_toggle_requested.connect(
        lambda file_path, line_number, enabled: signals.append((file_path, line_number, enabled))
    )

    item = panel._bp_tree.topLevelItem(0)
    item.setCheckState(0, Qt.Unchecked)
    signals.clear()
    panel._on_bp_item_changed(item, 0)

    assert signals == [("/home/user/project/main.py", 5, False)]


def test_breakpoint_edit_and_remove_actions_emit_signals(panel: DebugPanelWidget) -> None:
    edit_signals: list[tuple[str, int]] = []
    remove_signals: list[tuple[str, int]] = []
    panel.breakpoint_edit_requested.connect(lambda file_path, line_number: edit_signals.append((file_path, line_number)))
    panel.breakpoint_remove_requested.connect(
        lambda file_path, line_number: remove_signals.append((file_path, line_number))
    )

    panel._edit_breakpoint("/home/user/project/main.py", 5)
    panel._remove_breakpoint("/home/user/project/main.py", 5)

    assert edit_signals == [("/home/user/project/main.py", 5)]
    assert remove_signals == [("/home/user/project/main.py", 5)]


def test_clear_all_breakpoints_emits_remove_for_each_breakpoint(panel: DebugPanelWidget) -> None:
    panel.set_breakpoints(
        [
            build_breakpoint("/home/user/project/main.py", 5),
            build_breakpoint("/home/user/project/util.py", 3),
        ]
    )
    signals: list[tuple[str, int]] = []
    panel.breakpoint_remove_requested.connect(lambda file_path, line_number: signals.append((file_path, line_number)))

    panel._handle_clear_all_breakpoints()

    assert signals == [
        ("/home/user/project/main.py", 5),
        ("/home/user/project/util.py", 3),
    ]


def test_command_submission_and_output_helpers(panel: DebugPanelWidget) -> None:
    panel.set_command_input_enabled(True)
    command_signals: list[str] = []
    panel.command_submitted.connect(lambda text: command_signals.append(text))

    panel._command_input.setText("continue")
    panel._command_input.returnPressed.emit()
    panel.append_output("[debug] Paused at breakpoint")

    assert command_signals == ["continue"]
    assert "[debug] Paused at breakpoint" in panel._output_widget.toPlainText()

    panel.clear_output()
    assert panel._output_widget.toPlainText() == ""
