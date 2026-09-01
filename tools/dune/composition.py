from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional


class CompositionError(ValueError):
    pass


_PHASES_PATH = "app/shell/main_window_composition_phases.py"
_FEATURE_SPECS_PATH = "app/features/spec.py"
_COMMITTED_INSTALL_COUNT = 7
_COMMITTED_WINDOW_FIELDS = frozenset(
    {
        "_action_registry",
        "_active_named_run_config_name",
        "_active_run_output_tail",
        "_active_transient_entry_file_path",
        "_activity_bar",
        "_auto_open_console_on_run_output",
        "_auto_open_problems_on_run_failure",
        "_auto_save_to_file_timer",
        "_auto_start_repl_timer",
        "_background_tasks",
        "_bottom_tabs_widget",
        "_center_stack",
        "_close_tab_shortcut",
        "_command_broker",
        "_completion_auto_trigger",
        "_completion_enabled",
        "_completion_min_chars",
        "_composition_timers",
        "_console_model",
        "_dark_chrome_palette",
        "_debug_control_workflow",
        "_debug_exception_policy",
        "_debug_execution_editor",
        "_debug_inspector_workflow",
        "_debug_panel",
        "_debug_session",
        "_declarative_contribution_manager",
        "_dependency_inspector_dialog",
        "_diagnostics_enabled",
        "_diagnostics_orchestrator",
        "_diagnostics_realtime",
        "_editor_auto_reindent_flat_python_paste",
        "_editor_auto_save",
        "_editor_detect_indentation_from_file",
        "_editor_enable_preview",
        "_editor_exit_behavior",
        "_editor_font_family",
        "_editor_font_size",
        "_editor_format_on_save",
        "_editor_hover_tooltip_enabled",
        "_editor_indent_size",
        "_editor_indent_style",
        "_editor_insert_final_newline_on_save",
        "_editor_manager",
        "_editor_organize_imports_on_save",
        "_editor_tab_factory",
        "_editor_tab_width",
        "_editor_tab_workflow",
        "_editor_tabs_coordinator",
        "_editor_tabs_widget",
        "_editor_trim_trailing_whitespace_on_save",
        "_editor_widgets_by_path",
        "_effective_shortcuts",
        "_event_bus",
        "_example_project_service",
        "_explorer_new_file_btn",
        "_explorer_new_folder_btn",
        "_explorer_refresh_btn",
        "_explorer_splitter",
        "_external_change_poll_timer",
        "_external_file_change_workflow",
        "_file_project_commands_workflow",
        "_find_replace_bar",
        "_find_replace_workflow",
        "_help_controller",
        "_import_update_policy",
        "_indent_source_by_path",
        "_intelligence_cache_workflow",
        "_intelligence_controller",
        "_intelligence_runtime_settings",
        "_is_shutting_down",
        "_keep_preview_open_shortcut",
        "_known_runtime_modules",
        "_latest_health_report",
        "_latest_import_issue_report",
        "_latest_package_issue_report",
        "_latest_run_issue_ids",
        "_latest_run_issue_report",
        "_latest_runtime_issue_report",
        "_lint_rule_overrides",
        "_lint_workflow",
        "_loaded_project",
        "_local_history_retention_policy",
        "_local_history_workflow",
        "_logger",
        "_main_thread_dispatcher",
        "_markdown_panes_by_path",
        "_menu_registry",
        "_outline_collapsed",
        "_outline_follow_cursor",
        "_outline_panel",
        "_outline_refresh_timer",
        "_outline_sort_mode",
        "_outline_symbols_by_path",
        "_pending_project_tree_preview_path",
        "_pending_realtime_lint_file_path",
        "_plugin_activation_workflow",
        "_plugin_api_broker",
        "_plugin_dialog_workflow",
        "_plugin_manager_dialog",
        "_plugin_runtime_manager",
        "_plugin_safe_mode",
        "_problems_controller",
        "_problems_panel",
        "_problems_tab_widget",
        "_project_controller",
        "_project_inventory_orchestrator",
        "_project_load_workflow",
        "_project_placeholder_label",
        "_project_rescan_workflow",
        "_project_tree_action_coordinator",
        "_project_tree_action_workflow",
        "_project_tree_controller",
        "_project_tree_presenter",
        "_project_tree_preview_click_timer",
        "_project_tree_structure_signature",
        "_project_tree_ui_workflow",
        "_project_tree_widget",
        "_python_console_container",
        "_python_console_history_path",
        "_python_console_widget",
        "_python_console_workflow",
        "_python_style_workflow",
        "_python_tooling_status_controller",
        "_quick_fix_require_preview_for_multifile",
        "_quick_fixes_enabled",
        "_quick_open_dialog",
        "_realtime_lint_timer",
        "_repl_event_queue",
        "_repl_event_timer",
        "_repl_event_workflow",
        "_repl_manager",
        "_reported_completion_degradation_reasons",
        "_restore_project_timer",
        "_run_config_controller",
        "_run_debug_presenter",
        "_run_event_queue",
        "_run_event_timer",
        "_run_event_workflow",
        "_run_launch_workflow",
        "_run_log_panel",
        "_run_service",
        "_run_session_controller",
        "_runtime_introspection_coordinator",
        "_runtime_onboarding_workflow",
        "_runtime_probe_timer",
        "_runtime_support_workflow",
        "_save_workflow",
        "_search_sidebar",
        "_selected_linter",
        "_semantic_navigation_workflow",
        "_semantic_session",
        "_settings_apply_workflow",
        "_settings_service",
        "_shell_layout_workflow",
        "_shell_preferences_runtime",
        "_shell_theme_workflow",
        "_shortcut_overrides",
        "_sidebar_stack",
        "_source_root_workflow",
        "_startup_capability_facade",
        "_startup_probe_refresh_timer",
        "_startup_report",
        "_state_root",
        "_status_controller",
        "_stored_lint_diagnostics",
        "_stored_runtime_problems",
        "_symbol_cache_db_path",
        "_symbol_index_generation",
        "_syntax_color_overrides",
        "_tab_content_registry",
        "_template_service",
        "_test_explorer_panel",
        "_test_runner_workflow",
        "_theme_mode",
        "_toolbar",
        "_top_splitter",
        "_tree_clipboard_cut",
        "_tree_clipboard_paths",
        "_tree_entrypoint_icon",
        "_tree_file_icon",
        "_tree_file_icon_map",
        "_tree_filename_icon_map",
        "_tree_folder_icon",
        "_tree_folder_open_icon",
        "_ui_font_weight",
        "_vertical_splitter",
        "_welcome_widget",
        "_workflow_broker",
        "_workflow_provider_catalog",
        "_workspace_controller",
        "_zoom_delta",
    }
)


@dataclass(frozen=True)
class _FeatureSpec:
    key: str
    ownership_globs: tuple[str, ...]


@dataclass(frozen=True)
class _FieldOccurrence:
    name: str
    path: str
    line_number: int


def find_composition_violations(
    repo_root: Path,
    tracked_files: Iterable[str],
) -> list[str]:
    normalized_files = tuple(
        path.replace("\\", "/")
        for path in tracked_files
    )
    composition_paths = {_PHASES_PATH, _FEATURE_SPECS_PATH}
    present_paths = composition_paths.intersection(normalized_files)
    if not present_paths:
        return []
    if present_paths != composition_paths:
        missing_path = sorted(composition_paths - present_paths)[0]
        raise CompositionError(f"{missing_path}: tracked composition file is missing")

    feature_specs = _load_feature_specs(repo_root)
    violations = _install_count_violations(repo_root)
    occurrences = _collect_window_fields(repo_root, normalized_files)
    for occurrence in occurrences:
        if occurrence.name in _COMMITTED_WINDOW_FIELDS:
            continue
        if _owned_by_feature(occurrence.path, feature_specs):
            continue
        violations.append(
            f"composition: {occurrence.path}:{occurrence.line_number}: "
            f"window field {occurrence.name} is not committed or owned by a FeatureSpec"
        )
    return violations


def _install_count_violations(repo_root: Path) -> list[str]:
    tree = _parse_python(repo_root / _PHASES_PATH, _PHASES_PATH)
    install_count = sum(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("install_")
        for node in tree.body
    )
    if install_count <= _COMMITTED_INSTALL_COUNT:
        return []
    return [
        f"composition: {_PHASES_PATH}: {install_count} install_* functions "
        f"exceed the committed count of {_COMMITTED_INSTALL_COUNT}"
    ]


def _load_feature_specs(repo_root: Path) -> tuple[_FeatureSpec, ...]:
    tree = _parse_python(repo_root / _FEATURE_SPECS_PATH, _FEATURE_SPECS_PATH)
    registry = next(
        (
            node.value
            for node in tree.body
            if isinstance(node, (ast.Assign, ast.AnnAssign))
            and _assigned_name(node) == "FEATURE_SPECS"
            and node.value is not None
        ),
        None,
    )
    if registry is None:
        raise CompositionError(
            f"{_FEATURE_SPECS_PATH}: FEATURE_SPECS is missing"
        )
    if not isinstance(registry, (ast.List, ast.Tuple)):
        raise CompositionError(
            f"{_FEATURE_SPECS_PATH}:{registry.lineno}: "
            "FEATURE_SPECS must be a literal list or tuple"
        )

    specs: list[_FeatureSpec] = []
    keys: set[str] = set()
    for item in registry.elts:
        spec = _parse_feature_spec(item)
        if spec.key in keys:
            raise CompositionError(
                f"{_FEATURE_SPECS_PATH}:{item.lineno}: "
                f"duplicate FeatureSpec key {spec.key}"
            )
        keys.add(spec.key)
        specs.append(spec)
    return tuple(specs)


def _parse_feature_spec(node: ast.AST) -> _FeatureSpec:
    if not isinstance(node, ast.Call) or _call_name(node.func) != "FeatureSpec":
        line_number = getattr(node, "lineno", 1)
        raise CompositionError(
            f"{_FEATURE_SPECS_PATH}:{line_number}: "
            "FEATURE_SPECS entries must be FeatureSpec calls"
        )
    key_node = _call_argument(node, "key", 0)
    globs_node = _call_argument(node, "ownership_globs", 1)
    key = _string_literal(key_node)
    if not key:
        raise CompositionError(
            f"{_FEATURE_SPECS_PATH}:{node.lineno}: "
            "FeatureSpec key must be a non-empty string"
        )
    ownership_globs = _string_sequence(globs_node)
    if not ownership_globs:
        raise CompositionError(
            f"{_FEATURE_SPECS_PATH}:{node.lineno}: "
            f"FeatureSpec {key} must declare ownership_globs"
        )
    for pattern in ownership_globs:
        _validate_feature_glob(pattern, node.lineno)
    return _FeatureSpec(key, ownership_globs)


def _call_argument(
    node: ast.Call,
    keyword_name: str,
    position: int,
) -> Optional[ast.AST]:
    keyword_value = next(
        (
            keyword.value
            for keyword in node.keywords
            if keyword.arg == keyword_name
        ),
        None,
    )
    if keyword_value is not None:
        return keyword_value
    if position < len(node.args):
        return node.args[position]
    return None


def _string_literal(node: Optional[ast.AST]) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return ""


def _string_sequence(node: Optional[ast.AST]) -> tuple[str, ...]:
    if not isinstance(node, (ast.List, ast.Tuple)):
        return ()
    values = tuple(_string_literal(item) for item in node.elts)
    if not all(values):
        return ()
    return values


def _validate_feature_glob(pattern: str, line_number: int) -> None:
    if (
        not pattern.startswith("app/features/")
        or pattern in {"app/features/**", "app/features/"}
        or "\\" in pattern
        or "/../" in f"/{pattern}/"
    ):
        raise CompositionError(
            f"{_FEATURE_SPECS_PATH}:{line_number}: "
            f"invalid FeatureSpec ownership glob {pattern}"
        )
    wildcard_prefix = pattern[:-3] if pattern.endswith("/**") else pattern
    if any(character in wildcard_prefix for character in "*?["):
        raise CompositionError(
            f"{_FEATURE_SPECS_PATH}:{line_number}: "
            f"unsupported FeatureSpec ownership glob {pattern}"
        )


def _collect_window_fields(
    repo_root: Path,
    tracked_files: Iterable[str],
) -> tuple[_FieldOccurrence, ...]:
    occurrences: list[_FieldOccurrence] = []
    python_files = sorted(
        {
            path.replace("\\", "/")
            for path in tracked_files
            if path.endswith(".py")
            and (path == "app" or path.startswith("app/"))
        }
    )
    for relative_path in python_files:
        source = (repo_root / relative_path).read_text(encoding="utf-8")
        if "._" not in source and "bind_private_attrs" not in source:
            continue
        tree = _parse_python(repo_root / relative_path, relative_path)
        visitor = _WindowFieldVisitor(relative_path)
        visitor.visit(tree)
        occurrences.extend(visitor.occurrences)
        if visitor.dynamic_bind_lines:
            line_number = visitor.dynamic_bind_lines[0]
            raise CompositionError(
                f"{relative_path}:{line_number}: "
                "bind_private_attrs keys must be a literal dictionary"
            )
    return tuple(
        sorted(
            occurrences,
            key=lambda item: (item.path, item.line_number, item.name),
        )
    )


class _WindowFieldVisitor(ast.NodeVisitor):
    def __init__(self, relative_path: str) -> None:
        self._relative_path = relative_path
        self.occurrences: list[_FieldOccurrence] = []
        self.dynamic_bind_lines: list[int] = []

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            self._record_target(target)
        self.generic_visit(node.value)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self._record_target(node.target)
        if node.value is not None:
            self.generic_visit(node.value)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self._record_target(node.target)
        self.generic_visit(node.value)

    def visit_Call(self, node: ast.Call) -> None:
        call_name = _call_name(node.func)
        if call_name == "bind_private_attrs":
            attrs = _call_argument(node, "attrs", 1)
            if not isinstance(attrs, ast.Dict):
                self.dynamic_bind_lines.append(node.lineno)
            else:
                for key in attrs.keys:
                    name = _string_literal(key)
                    if name.startswith("_"):
                        self._record(name, key or node)
        elif call_name == "setattr":
            target = _call_argument(node, "object", 0)
            name = _string_literal(_call_argument(node, "name", 1))
            if name.startswith("_") and _is_window_reference(
                target,
                self._relative_path,
            ):
                self._record(name, node)
        self.generic_visit(node)

    def _record_target(self, target: ast.AST) -> None:
        if (
            isinstance(target, ast.Attribute)
            and target.attr.startswith("_")
            and _is_window_reference(target.value, self._relative_path)
        ):
            self._record(target.attr, target)
            return
        if isinstance(target, (ast.List, ast.Tuple)):
            for item in target.elts:
                self._record_target(item)

    def _record(self, name: str, node: ast.AST) -> None:
        self.occurrences.append(
            _FieldOccurrence(
                name=name,
                path=self._relative_path,
                line_number=getattr(node, "lineno", 1),
            )
        )


def _is_window_reference(
    node: Optional[ast.AST],
    relative_path: str,
) -> bool:
    if isinstance(node, ast.Name):
        if node.id in {"window", "w"}:
            return True
        return (
            node.id == "self"
            and relative_path == "app/shell/main_window.py"
        )
    if not isinstance(node, ast.Attribute):
        return False
    if node.attr in {"w", "window"} and isinstance(node.value, ast.Name):
        return node.value.id == "ctx"
    if node.attr == "_window":
        return True
    return False


def _owned_by_feature(
    relative_path: str,
    specs: tuple[_FeatureSpec, ...],
) -> bool:
    return any(
        _matches(pattern, relative_path)
        for spec in specs
        for pattern in spec.ownership_globs
    )


def _matches(pattern: str, path: str) -> bool:
    if pattern.endswith("/**"):
        prefix = pattern[:-3]
        return path.startswith(f"{prefix}/")
    return path == pattern


def _parse_python(path: Path, relative_path: str) -> ast.Module:
    try:
        return ast.parse(
            path.read_text(encoding="utf-8"),
            filename=relative_path,
        )
    except OSError as exc:
        raise CompositionError(f"{relative_path}: {exc}") from exc
    except SyntaxError as exc:
        line_number = exc.lineno or 1
        raise CompositionError(
            f"{relative_path}:{line_number}: invalid Python syntax: {exc.msg}"
        ) from exc


def _assigned_name(node: ast.AST) -> str:
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return node.target.id
    if (
        isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
    ):
        return node.targets[0].id
    return ""


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""
