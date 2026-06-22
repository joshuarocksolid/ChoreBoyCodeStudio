"""Subprocess usage checks for packaging dependency audit."""

from __future__ import annotations

import ast
from pathlib import Path

from app.core.models import RuntimeIssue
from app.support.runtime_explainer import HELP_TOPIC_PACKAGING

_SUBPROCESS_CALL_NAMES = {"Popen", "call", "check_call", "check_output", "run"}


def subprocess_issues(
    *,
    tree: ast.AST,
    file_path: Path,
    project_root: Path,
) -> list[RuntimeIssue]:
    """Return packaging issues for subprocess usage in one parsed module."""
    issues: list[RuntimeIssue] = []
    rel_file = file_path.relative_to(project_root).as_posix()
    if _imports_subprocess_module(tree):
        issues.append(
            RuntimeIssue(
                issue_id=f"package.subprocess.review.{rel_file}",
                workflow="package",
                severity="degraded",
                title="Project uses subprocess APIs that need ChoreBoy review",
                summary="This project imports `subprocess`, which can behave differently on constrained ChoreBoy systems.",
                why_it_happened="Inside the validated AppRun environment, subprocess execution is intentionally restricted and should not assume arbitrary executables are available.",
                next_steps=[
                    "Review subprocess calls for reliance on executables other than `/bin/sh`.",
                    "Prefer in-process Python or documented shell entrypoints where possible.",
                ],
                help_topic=HELP_TOPIC_PACKAGING,
                evidence={"source_file": rel_file},
            )
        )
    for lineno, command_name in _literal_external_commands(tree):
        issues.append(
            RuntimeIssue(
                issue_id=f"package.subprocess.literal_binary.{rel_file}.{lineno}",
                workflow="package",
                severity="blocking",
                title="Package hardcodes a subprocess target that is unlikely to work on ChoreBoy",
                summary=f"A subprocess call launches `{command_name}` directly instead of `/bin/sh`.",
                why_it_happened="The validated ChoreBoy runtime only guarantees subprocess compatibility through `/bin/sh` inside AppRun.",
                next_steps=[
                    "Rewrite the subprocess call to use a supported shell entrypoint or an in-process alternative.",
                    "Re-run packaging after removing the direct binary assumption.",
                ],
                help_topic=HELP_TOPIC_PACKAGING,
                evidence={
                    "source_file": rel_file,
                    "line_number": lineno,
                    "command_name": command_name,
                },
            )
        )
    for lineno in _shell_true_subprocess_calls(tree):
        issues.append(
            RuntimeIssue(
                issue_id=f"package.subprocess.shell_true.{rel_file}.{lineno}",
                workflow="package",
                severity="blocking",
                title="Package uses shell=True subprocess execution",
                summary="A subprocess call opts into shell parsing, which is not part of the supported ChoreBoy packaging contract.",
                why_it_happened="Shell-mediated subprocesses hide the executable boundary and are difficult to validate under ChoreBoy's restricted runtime.",
                next_steps=[
                    "Replace shell=True with an explicit argv-list launch.",
                    "If a shell is required, call `/bin/sh` explicitly and document the command contract.",
                ],
                help_topic=HELP_TOPIC_PACKAGING,
                evidence={"source_file": rel_file, "line_number": lineno},
            )
        )
    return issues


def _imports_subprocess_module(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name.split(".")[0] == "subprocess" for alias in node.names):
                return True
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] == "subprocess":
                return True
    return False


def _literal_external_commands(tree: ast.AST) -> list[tuple[int, str]]:
    commands: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        command_name = ""
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            if func.value.id == "subprocess" and func.attr in _SUBPROCESS_CALL_NAMES:
                command_name = _first_command_name(node)
            elif func.value.id == "os" and func.attr in {
                "execl",
                "execle",
                "execlp",
                "execlpe",
                "execv",
                "execve",
                "execvp",
                "execvpe",
                "system",
                "popen",
            }:
                command_name = _first_command_name(node)
        if not command_name:
            continue
        if command_name != "/bin/sh":
            commands.append((int(getattr(node, "lineno", 1) or 1), command_name))
    return commands


def _first_command_name(node: ast.Call) -> str:
    if not node.args:
        return ""
    first_arg = node.args[0]
    if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
        command_text = first_arg.value.strip()
        if not command_text:
            return ""
        return command_text.split()[0]
    if isinstance(first_arg, (ast.List, ast.Tuple)) and first_arg.elts:
        first_element = first_arg.elts[0]
        if isinstance(first_element, ast.Constant) and isinstance(first_element.value, str):
            return first_element.value.strip()
    return ""


def _shell_true_subprocess_calls(tree: ast.AST) -> list[int]:
    line_numbers: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or not isinstance(func.value, ast.Name):
            continue
        if func.value.id != "subprocess" or func.attr not in _SUBPROCESS_CALL_NAMES:
            continue
        for keyword in node.keywords:
            if (
                keyword.arg == "shell"
                and isinstance(keyword.value, ast.Constant)
                and keyword.value.value is True
            ):
                line_numbers.append(int(getattr(node, "lineno", 1) or 1))
    return line_numbers
