"""MainWindow surface mutations for ``ProjectLoadWorkflow`` phases."""

from __future__ import annotations

from typing import Any, Callable

from app.core import constants
from app.core.models import LoadedProject
from app.shell.events import ProjectOpenedEvent
from app.shell.project_open_telemetry import ProjectOpenTelemetry
from app.shell.project_tree_utils import effective_excludes_for, filter_tree_signature_entries


def apply_project_surface(
    window: Any,
    loaded_project: LoadedProject,
    *,
    load_effective_exclude_patterns: Callable[[str], list[str]],
) -> None:
    window._loaded_project = loaded_project
    window._runtime_support_workflow.clear_issue_state_for_project_change()
    window._run_launch_workflow.refresh_active_run_config_indicator()
    window._lint_rule_overrides = window._shell_preferences_runtime.load_lint_rule_overrides()
    window._selected_linter = window._shell_preferences_runtime.load_selected_linter()
    window._plugin_activation_workflow.reload()
    window._refresh_python_tooling_status()
    window._runtime_onboarding_workflow.show_editor_screen()
    window.set_project_placeholder(loaded_project.metadata.name)
    window.setWindowTitle(
        f"ChoreBoy Code Studio v{constants.APP_VERSION} — {loaded_project.metadata.name}"
    )
    window._logger.info("Project loaded: %s", loaded_project.project_root)
    window._project_tree_ui_workflow.update_explorer_buttons_enabled()
    window._project_tree_structure_signature = filter_tree_signature_entries(
        tuple(entry.relative_path for entry in loaded_project.entries)
    )
    window._project_inventory_orchestrator.set_tree_structure_signature(
        window._project_tree_structure_signature
    )
    window._editor_tab_workflow.reset_editor_tabs()
    window._stored_lint_diagnostics.clear()
    if window._search_sidebar is not None:
        window._search_sidebar.set_project_root(loaded_project.project_root)
        effective = effective_excludes_for(
            loaded_project,
            load_effective_exclude_patterns=load_effective_exclude_patterns,
        )
        window._search_sidebar.set_exclude_patterns(effective.as_list())
        window._project_inventory_orchestrator.rebuild(
            loaded_project.project_root,
            effective,
        )


def finalize_project_open(
    window: Any,
    loaded_project: LoadedProject,
    telemetry: ProjectOpenTelemetry,
    *,
    exclude_patterns: list[str],
) -> None:
    snapshot = window._project_inventory_orchestrator.snapshot
    window._lint_workflow.lint_all_open_files()
    window._debug_control_workflow.refresh_breakpoints_list()
    window._file_project_commands_workflow.refresh_open_recent_menu()
    window._refresh_save_action_states()
    window._run_event_workflow.refresh_run_action_states()
    if window._intelligence_runtime_settings.force_full_reindex_on_open:
        window._intelligence_cache_workflow.rebuild_intelligence_cache()
    window._intelligence_cache_workflow.start_symbol_indexing(
        loaded_project.project_root,
        exclude_patterns=exclude_patterns,
        inventory_snapshot=snapshot,
    )
    telemetry.log(window._logger)
    window._event_bus.publish(
        ProjectOpenedEvent(
            project_root=loaded_project.project_root,
            project_name=loaded_project.metadata.name,
        )
    )
    window._file_project_commands_workflow.persist_last_project_path(loaded_project.project_root)
    test_runner_workflow = getattr(window, "_test_runner_workflow", None)
    if test_runner_workflow is not None:
        test_runner_workflow.refresh_discovery()
    window.statusBar().showMessage(
        f"Opened project — {loaded_project.metadata.name}",
        3000,
    )
