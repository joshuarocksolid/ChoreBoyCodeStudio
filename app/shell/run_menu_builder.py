"""Run menu construction."""

from __future__ import annotations

from typing import Any, Callable

from app.shell.menu_action_builder import register_menu_action
from app.shell.menu_build_context import MenuBuildContext


def build_run_menu(ctx: MenuBuildContext) -> object:
    run_menu = ctx.menu_bar.addMenu("&Run")
    run_menu.setObjectName("shell.menu.run")
    ctx.menus["shell.menu.run"] = run_menu

    _add_launch_actions(ctx, run_menu)
    run_menu.addSeparator()
    _add_test_and_session_actions(ctx, run_menu)
    run_menu.addSeparator()
    _add_debug_control_actions(ctx, run_menu)
    run_menu.addSeparator()
    _add_console_actions(ctx, run_menu)
    run_menu.addSeparator()
    register_menu_action(
        qt_widgets=ctx.qt_widgets,
        menu=run_menu,
        action_lookup=ctx.actions,
        action_id="shell.action.build.package",
        label="Package Project...",
        callback=ctx.callbacks.on_package_project,
    )
    return run_menu


def _add_launch_actions(ctx: MenuBuildContext, run_menu: Any) -> None:
    callbacks = ctx.callbacks
    run_action = register_menu_action(
        qt_widgets=ctx.qt_widgets,
        menu=run_menu,
        action_lookup=ctx.actions,
        action_id="shell.action.run.run",
        label="Run Active File",
        shortcut="F5",
        callback=callbacks.on_run,
        shortcut_overrides=ctx.shortcut_overrides,
    )
    run_action.setToolTip("Run the currently active file. Output appears in the Run Log tab.")
    run_action.setStatusTip("Run the currently active file. Output appears in the Run Log tab.")

    debug_action = register_menu_action(
        qt_widgets=ctx.qt_widgets,
        menu=run_menu,
        action_lookup=ctx.actions,
        action_id="shell.action.run.debug",
        label="Debug Active File",
        shortcut="Ctrl+F5",
        callback=callbacks.on_debug,
        shortcut_overrides=ctx.shortcut_overrides,
    )
    debug_action.setToolTip("Debug the currently active file. Output appears in Run Log and Debug tabs.")
    debug_action.setStatusTip("Debug the currently active file. Output appears in Run Log and Debug tabs.")

    for action_id, label, shortcut, callback in [
        ("shell.action.run.runProject", "Run Project", "Shift+F5", callbacks.on_run_project),
        ("shell.action.run.debugProject", "Debug Project", "Ctrl+Shift+F5", callbacks.on_debug_project),
    ]:
        _add_run_action(ctx, run_menu, action_id, label, shortcut, callback)


def _add_test_and_session_actions(ctx: MenuBuildContext, run_menu: Any) -> None:
    callbacks = ctx.callbacks
    for action_id, label, shortcut, callback in [
        ("shell.action.run.pytestProject", "Run Project Tests", "Ctrl+Shift+T", callbacks.on_run_pytest_project),
        (
            "shell.action.run.pytestCurrentFile",
            "Run Current File Tests",
            "Ctrl+Alt+T",
            callbacks.on_run_pytest_current_file,
        ),
        (
            "shell.action.run.pytestAtCursor",
            "Run Test at Cursor",
            None,
            callbacks.on_run_pytest_at_cursor,
        ),
        (
            "shell.action.run.debugPytestCurrentFile",
            "Debug Current Test",
            "Ctrl+Alt+Shift+T",
            callbacks.on_debug_pytest_current_file,
        ),
        (
            "shell.action.run.debugPytestFailed",
            "Debug Failed Test",
            None,
            callbacks.on_debug_pytest_failed,
        ),
        ("shell.action.run.runWithArgs", "Run With Arguments...", None, callbacks.on_run_with_args),
        ("shell.action.run.runWithConfig", "Run Configurations...", None, callbacks.on_run_with_config),
        ("shell.action.run.stop", "Stop", "Shift+F2", callbacks.on_stop),
        ("shell.action.run.restart", "Restart", "Ctrl+Shift+F2", callbacks.on_restart),
        (
            "shell.action.run.rerunLastDebugTarget",
            "Rerun Last Debug Target",
            "Ctrl+Shift+F6",
            callbacks.on_rerun_last_debug_target,
        ),
    ]:
        _add_run_action(ctx, run_menu, action_id, label, shortcut, callback)


def _add_debug_control_actions(ctx: MenuBuildContext, run_menu: Any) -> None:
    callbacks = ctx.callbacks
    for action_id, label, shortcut, callback in [
        ("shell.action.run.continue", "Continue", "F6", callbacks.on_continue_debug),
        ("shell.action.run.pause", "Pause", "Ctrl+F6", callbacks.on_pause_debug),
        ("shell.action.run.stepOver", "Step Over", "F10", callbacks.on_step_over),
        ("shell.action.run.stepInto", "Step Into", "F11", callbacks.on_step_into),
        ("shell.action.run.stepOut", "Step Out", "Shift+F11", callbacks.on_step_out),
        ("shell.action.run.toggleBreakpoint", "Toggle Breakpoint", "F9", callbacks.on_toggle_breakpoint),
        ("shell.action.run.removeAllBreakpoints", "Remove All Breakpoints", None, callbacks.on_remove_all_breakpoints),
        ("shell.action.run.debugExceptionStops", "Exception Stop Settings...", None, callbacks.on_debug_exception_stops),
    ]:
        _add_run_action(ctx, run_menu, action_id, label, shortcut, callback)


def _add_console_actions(ctx: MenuBuildContext, run_menu: Any) -> None:
    python_console_action = register_menu_action(
        qt_widgets=ctx.qt_widgets,
        menu=run_menu,
        action_lookup=ctx.actions,
        action_id="shell.action.run.pythonConsole",
        label="Restart Python Console (REPL)",
        shortcut="Ctrl+`",
        enabled=True,
        callback=ctx.callbacks.on_start_python_console,
        shortcut_overrides=ctx.shortcut_overrides,
    )
    python_console_action.setToolTip("Restart the REPL session shown in the Python Console tab.")
    python_console_action.setStatusTip("Restart the REPL session shown in the Python Console tab.")
    register_menu_action(
        qt_widgets=ctx.qt_widgets,
        menu=run_menu,
        action_lookup=ctx.actions,
        action_id="shell.action.run.clearConsole",
        label="Clear Console",
        callback=ctx.callbacks.on_clear_console,
    )


def _add_run_action(
    ctx: MenuBuildContext,
    run_menu: Any,
    action_id: str,
    label: str,
    shortcut: str | None,
    callback: Callable[[], object] | None,
) -> None:
    register_menu_action(
        qt_widgets=ctx.qt_widgets,
        menu=run_menu,
        action_lookup=ctx.actions,
        action_id=action_id,
        label=label,
        shortcut=shortcut,
        callback=callback,
        shortcut_overrides=ctx.shortcut_overrides,
    )
