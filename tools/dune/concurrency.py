from __future__ import annotations

import ast
from pathlib import Path
from typing import Iterable


class ConcurrencyError(ValueError):
    pass


_THREAD_FACTORIES = frozenset(
    {
        "app.editors.search_panel.SearchWorker",
        "concurrent.futures.ThreadPoolExecutor",
        "threading.Thread",
    }
)

_THREAD_ALLOWANCES = (
    (
        "app/intelligence/semantic_worker.py",
        "SemanticWorker",
        "threading.Thread",
    ),
    (
        "app/run/process_supervisor.py",
        "ProcessSupervisor",
        "threading.Thread",
    ),
    (
        "app/debug/debug_transport.py",
        "DebugTransportServer",
        "threading.Thread",
    ),
    (
        "app/debug/debug_transport.py",
        "RunnerDebugTransportClient",
        "threading.Thread",
    ),
    (
        "app/project/project_open_worker.py",
        "ProjectOpenWorker",
        "threading.Thread",
    ),
    (
        "app/editors/search_panel.py",
        "SearchWorker",
        "threading.Thread",
    ),
    (
        "app/shell/search_sidebar_widget.py",
        "SearchSidebarWidget",
        "app.editors.search_panel.SearchWorker",
    ),
    (
        "app/runner/repl_control.py",
        "ReplControlServer",
        "threading.Thread",
    ),
    (
        "app/shell/background_tasks.py",
        "GeneralTaskScheduler",
        "concurrent.futures.ThreadPoolExecutor",
    ),
    (
        "app/shell/python_console_workflow.py",
        "PythonConsoleWorkflow._default_start_background_work",
        "threading.Thread",
    ),
    (
        "run_plugin_host.py",
        "main",
        "threading.Thread",
    ),
)

_BLOCKING_ADAPTERS = frozenset(
    {
        "analyze_python_with_workflow",
        "format_python_with_workflow",
        "organize_imports_with_workflow",
    }
)

_BLOCKING_METHODS = frozenset(
    {
        "invoke_command",
        "invoke_query",
        "invoke_runtime_command",
        "invoke_workflow_query",
    }
)

_BLOCKING_ALLOWANCES = (
    (
        "app/shell/python_style_workflow.py",
        "PythonStyleWorkflow.handle_format_current_file_action",
        "format_python_with_workflow",
    ),
    (
        "app/shell/python_style_workflow.py",
        "PythonStyleWorkflow.handle_organize_imports_action",
        "organize_imports_with_workflow",
    ),
    (
        "app/shell/python_style_workflow.py",
        "PythonStyleWorkflow.apply_safe_fixes_for_file",
        "analyze_python_with_workflow",
    ),
    (
        "app/shell/save_workflow.py",
        "SaveWorkflow.apply_save_transforms",
        "format_python_with_workflow",
    ),
    (
        "app/shell/save_workflow.py",
        "SaveWorkflow.apply_save_transforms",
        "organize_imports_with_workflow",
    ),
    (
        "app/shell/plugin_dialog_workflow.py",
        "PluginDialogWorkflow.execute_plugin_runtime_command",
        "invoke_runtime_command",
    ),
)

_UI_PREFIXES = ("app/editors/", "app/shell/")
_ALLOWLISTED_PATHS = frozenset(path for path, _owner, _call in _THREAD_ALLOWANCES)
_SOURCE_HINTS = (
    "Thread",
    "SearchWorker",
    "sleep",
    *_BLOCKING_ADAPTERS,
    *_BLOCKING_METHODS,
)


def find_concurrency_violations(
    repo_root: Path,
    tracked_files: Iterable[str],
) -> list[str]:
    python_files: set[str] = set()
    for path in tracked_files:
        normalized_path = path.replace("\\", "/")
        if not normalized_path.endswith(".py"):
            continue
        if (
            normalized_path.startswith(_UI_PREFIXES)
            or normalized_path in _ALLOWLISTED_PATHS
        ):
            python_files.add(normalized_path)
    if (repo_root / "run_plugin_host.py").is_file():
        python_files.add("run_plugin_host.py")

    violations: list[str] = []
    for relative_path in sorted(python_files):
        source_path = repo_root / relative_path
        source = source_path.read_text(encoding="utf-8")
        if not any(hint in source for hint in _SOURCE_HINTS):
            continue
        try:
            tree = ast.parse(
                source,
                filename=relative_path,
            )
        except SyntaxError as exc:
            line_number = exc.lineno or 1
            raise ConcurrencyError(
                f"{relative_path}:{line_number}: invalid Python syntax: {exc.msg}"
            ) from exc
        visitor = _ConcurrencyVisitor(relative_path, tree)
        visitor.visit(tree)
        violations.extend(visitor.violations)
    return violations


class _ConcurrencyVisitor(ast.NodeVisitor):
    def __init__(self, relative_path: str, tree: ast.AST) -> None:
        self._relative_path = relative_path
        self._aliases, self._scheduled_nodes = _analyze_tree(tree)
        self._scope: list[ast.AST] = []
        self.violations: list[str] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._scope.append(node)
        self.generic_visit(node)
        self._scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._scope.append(node)
        self.generic_visit(node)
        self._scope.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._scope.append(node)
        self.generic_visit(node)
        self._scope.pop()

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self._scope.append(node)
        self.generic_visit(node)
        self._scope.pop()

    def visit_Call(self, node: ast.Call) -> None:
        call_name = _qualified_name(node.func, self._aliases)
        call_tail = call_name.rsplit(".", 1)[-1]

        if self._is_ui_file() and call_tail == "QThread":
            self._add_violation(
                node,
                "app.shell and app.editors must not create QThread",
            )
        elif self._is_ui_file() and call_name == "time.sleep":
            self._add_violation(
                node,
                "app.shell and app.editors must not call time.sleep",
            )
        elif call_name in _THREAD_FACTORIES:
            if not self._thread_call_is_allowed(call_name):
                self._add_violation(
                    node,
                    f"{call_tail} is not an approved worker; "
                    "use GeneralTaskScheduler for shell work",
                )

        blocking_call = _blocking_call_name(call_name)
        if (
            self._is_ui_file()
            and blocking_call
            and not self._blocking_call_is_allowed(blocking_call)
        ):
            self._add_violation(
                node,
                f"GUI-thread {blocking_call} call must run through "
                "GeneralTaskScheduler",
            )

        self.generic_visit(node)

    def _is_ui_file(self) -> bool:
        return self._relative_path.startswith(_UI_PREFIXES)

    def _thread_call_is_allowed(self, call_name: str) -> bool:
        return _matches_allowance(
            _THREAD_ALLOWANCES,
            self._relative_path,
            self._owner_name(),
            call_name,
        )

    def _blocking_call_is_allowed(self, call_name: str) -> bool:
        if any(id(scope) in self._scheduled_nodes for scope in self._scope):
            return True
        return _matches_allowance(
            _BLOCKING_ALLOWANCES,
            self._relative_path,
            self._owner_name(),
            call_name,
        )

    def _owner_name(self) -> str:
        return ".".join(
            node.name
            for node in self._scope
            if isinstance(
                node,
                (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef),
            )
        )

    def _add_violation(self, node: ast.AST, message: str) -> None:
        line_number = getattr(node, "lineno", 1)
        self.violations.append(
            f"concurrency: {self._relative_path}:{line_number}: {message}"
        )


def _matches_allowance(
    allowances: tuple[tuple[str, str, str], ...],
    relative_path: str,
    owner: str,
    call_name: str,
) -> bool:
    return any(
        allowed_path == relative_path
        and (
            allowed_owner == owner
            or owner.startswith(f"{allowed_owner}.")
        )
        and allowed_call == call_name
        for allowed_path, allowed_owner, allowed_call in allowances
    )


def _blocking_call_name(call_name: str) -> str:
    call_tail = call_name.rsplit(".", 1)[-1]
    if call_tail in _BLOCKING_ADAPTERS or call_tail in _BLOCKING_METHODS:
        return call_tail
    return ""


def _analyze_tree(tree: ast.AST) -> tuple[dict[str, str], set[int]]:
    aliases: dict[str, str] = {}
    parents = {
        id(child): parent
        for parent in ast.walk(tree)
        for child in ast.iter_child_nodes(parent)
    }
    definitions: dict[tuple[int, str], list[ast.AST]] = {}
    calls: list[ast.Call] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                local_name = alias.asname or alias.name.split(".", 1)[0]
                aliases[local_name] = alias.name if alias.asname else local_name
        elif isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                if alias.name == "*":
                    continue
                aliases[alias.asname or alias.name] = (
                    f"{node.module}.{alias.name}"
                )
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            scope = next(_enclosing_scopes(node, parents))
            definitions.setdefault((id(scope), node.name), []).append(node)
        elif isinstance(node, ast.Call):
            calls.append(node)
    return aliases, _scheduled_task_nodes(
        calls,
        definitions,
        parents,
        aliases,
    )


def _scheduled_task_nodes(
    calls: Iterable[ast.Call],
    definitions: dict[tuple[int, str], list[ast.AST]],
    parents: dict[int, ast.AST],
    aliases: dict[str, str],
) -> set[int]:
    scheduled: set[int] = set()
    for node in calls:
        call_name = _qualified_name(node.func, aliases)
        if call_name.rsplit(".", 1)[-1] != "run":
            continue
        if "background_tasks" not in call_name and "scheduler" not in call_name:
            continue
        task_value = next(
            (
                keyword.value
                for keyword in node.keywords
                if keyword.arg == "task"
            ),
            None,
        )
        if isinstance(task_value, ast.Name):
            scheduled.update(
                id(definition)
                for definition in _resolve_definitions(
                    task_value.id,
                    node,
                    definitions,
                    parents,
                )
            )
        elif isinstance(task_value, ast.Lambda):
            scheduled.add(id(task_value))
    return scheduled


def _resolve_definitions(
    name: str,
    node: ast.AST,
    definitions: dict[tuple[int, str], list[ast.AST]],
    parents: dict[int, ast.AST],
) -> Iterable[ast.AST]:
    for scope in _enclosing_scopes(node, parents):
        matches = definitions.get((id(scope), name))
        if matches:
            return matches
    return ()


def _enclosing_scopes(
    node: ast.AST,
    parents: dict[int, ast.AST],
) -> Iterable[ast.AST]:
    current = parents.get(id(node))
    inside_function = False
    while current is not None:
        if isinstance(
            current,
            (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda),
        ):
            inside_function = True
            yield current
        elif isinstance(current, ast.ClassDef):
            if not inside_function:
                yield current
        elif isinstance(current, ast.Module):
            yield current
        current = parents.get(id(current))


def _qualified_name(
    node: ast.AST,
    aliases: dict[str, str],
) -> str:
    if isinstance(node, ast.Name):
        return aliases.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        prefix = _qualified_name(node.value, aliases)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    if isinstance(node, ast.Call):
        return _qualified_name(node.func, aliases)
    return ""
