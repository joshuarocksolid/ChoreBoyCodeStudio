from __future__ import annotations

import ast
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping


class HandlesError(ValueError):
    pass


_HANDLES_PATH = Path(".cursor/skills/verify-cbcs/references/handles.md")
_REQUIRED_HANDLE = re.compile(
    r"`#(shell(?:\.[A-Za-z_][A-Za-z0-9_]*)+(?:\.\*)?)`"
)
_MENTIONED_HANDLE = re.compile(
    r"`#?(shell(?:\.[A-Za-z_][A-Za-z0-9_]*)+(?:\.\*)?)`"
)
_INLINE_CODE = re.compile(r"`([^`]+)`")
_SHORT_HANDLE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_DUPLICATE_LIMITS = {
    "shell.editorTabs.textEditor": 1,
    "shell.explorerAction": 2,
    "shell.welcome.onboardingActionBtn": 5,
}

@dataclass(frozen=True)
class _Occurrence:
    name: str
    path: str
    line_number: int


@dataclass(frozen=True)
class _CodeHandles:
    occurrences: tuple[_Occurrence, ...]
    prefixes: frozenset[str]


@dataclass(frozen=True)
class _DocumentedHandles:
    required: frozenset[str]
    required_prefixes: frozenset[str]
    mentioned: frozenset[str]
    mentioned_prefixes: frozenset[str]


def find_handle_violations(
    repo_root: Path,
    tracked_files: Iterable[str],
) -> list[str]:
    code = _collect_code_handles(repo_root, tracked_files)
    handles_path = repo_root / _HANDLES_PATH
    if not handles_path.is_file():
        if code.occurrences or code.prefixes:
            raise HandlesError(f"missing {_HANDLES_PATH.as_posix()}")
        return []

    documented = _parse_documented_handles(
        handles_path.read_text(encoding="utf-8")
    )
    occurrences_by_name: dict[str, list[_Occurrence]] = defaultdict(list)
    for occurrence in code.occurrences:
        occurrences_by_name[occurrence.name].append(occurrence)

    violations = _missing_code_violations(
        documented,
        occurrences_by_name,
        code.prefixes,
    )
    violations.extend(
        _code_violations(
            documented,
            occurrences_by_name,
            code.prefixes,
        )
    )
    return violations


def _parse_documented_handles(
    text: str,
) -> _DocumentedHandles:
    required, required_prefixes = _partition_handle_matches(
        _REQUIRED_HANDLE.finditer(text)
    )
    mentioned, mentioned_prefixes = _partition_handle_matches(
        _MENTIONED_HANDLE.finditer(text)
    )
    expanded_required: set[str] = set(required)
    expanded_mentioned: set[str] = set(mentioned)
    for line in text.splitlines():
        if " · " not in line and " / " not in line:
            continue
        prefix = ""
        required_shorthand = False
        for token_match in _INLINE_CODE.finditer(line):
            token = token_match.group(1)
            full_match = _MENTIONED_HANDLE.fullmatch(f"`{token}`")
            if full_match:
                name = full_match.group(1)
                prefix = name.rsplit(".", 1)[0] + "."
                required_shorthand = token.startswith("#")
            elif prefix and _SHORT_HANDLE.fullmatch(token):
                name = prefix + token
                expanded_mentioned.add(name)
                if required_shorthand:
                    expanded_required.add(name)
    return _DocumentedHandles(
        frozenset(expanded_required),
        required_prefixes,
        frozenset(expanded_mentioned),
        mentioned_prefixes,
    )


def _partition_handle_matches(
    matches: Iterable[re.Match[str]],
) -> tuple[frozenset[str], frozenset[str]]:
    names: set[str] = set()
    prefixes: set[str] = set()
    for match in matches:
        name = match.group(1)
        if name.endswith(".*"):
            prefixes.add(name[:-1])
        else:
            names.add(name)
    return frozenset(names), frozenset(prefixes)


def _collect_code_handles(
    repo_root: Path,
    tracked_files: Iterable[str],
) -> _CodeHandles:
    occurrences: list[_Occurrence] = []
    prefixes: set[str] = set()
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
        if "setObjectName" not in source:
            continue
        try:
            tree = ast.parse(source, filename=relative_path)
        except SyntaxError as exc:
            line_number = exc.lineno or 1
            raise HandlesError(
                f"{relative_path}:{line_number}: invalid Python syntax: {exc.msg}"
            ) from exc
        bindings = _string_bindings(tree)
        for node in ast.walk(tree):
            if (
                not isinstance(node, ast.Call)
                or not node.args
                or not isinstance(node.func, ast.Attribute)
                or node.func.attr != "setObjectName"
            ):
                continue
            exact_names, name_prefixes = _resolve_name_expression(
                node.args[0],
                bindings,
            )
            occurrences.extend(
                _Occurrence(name, relative_path, node.lineno)
                for name in exact_names
            )
            prefixes.update(name_prefixes)
    return _CodeHandles(
        tuple(
            sorted(
                occurrences,
                key=lambda item: (item.name, item.path, item.line_number),
            )
        ),
        frozenset(prefixes),
    )


def _string_bindings(
    tree: ast.AST,
) -> dict[str, tuple[frozenset[str], frozenset[str]]]:
    bindings: dict[str, tuple[frozenset[str], frozenset[str]]] = {}
    assignments = sorted(
        (
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.Assign, ast.AnnAssign))
        ),
        key=lambda node: getattr(node, "lineno", 0),
    )
    for node in assignments:
        value = node.value
        if value is None:
            continue
        names = _assigned_names(node)
        if not names:
            continue
        exact_names, prefixes = _resolve_name_expression(value, bindings)
        if not exact_names and not prefixes:
            continue
        resolved = (frozenset(exact_names), frozenset(prefixes))
        for name in names:
            bindings[name] = resolved
    return bindings


def _assigned_names(node: ast.AST) -> tuple[str, ...]:
    if isinstance(node, ast.AnnAssign):
        if isinstance(node.target, ast.Name):
            return (node.target.id,)
        return ()
    if isinstance(node, ast.Assign):
        return tuple(
            target.id
            for target in node.targets
            if isinstance(target, ast.Name)
        )
    return ()


def _resolve_name_expression(
    node: ast.AST,
    bindings: Mapping[str, tuple[frozenset[str], frozenset[str]]],
) -> tuple[set[str], set[str]]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        if node.value.startswith("shell."):
            return {node.value}, set()
        return set(), set()
    if isinstance(node, ast.Name):
        exact_names, prefixes = bindings.get(
            node.id,
            (frozenset(), frozenset()),
        )
        return set(exact_names), set(prefixes)
    if isinstance(node, ast.JoinedStr):
        prefix = _joined_string_prefix(node)
        if prefix.startswith("shell."):
            return set(), {prefix}
    return set(), set()


def _joined_string_prefix(node: ast.JoinedStr) -> str:
    parts: list[str] = []
    for value in node.values:
        if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
            break
        parts.append(value.value)
    return "".join(parts)


def _missing_code_violations(
    documented: _DocumentedHandles,
    occurrences_by_name: Mapping[str, list[_Occurrence]],
    code_prefixes: frozenset[str],
) -> list[str]:
    violations = []
    for name in sorted(documented.required):
        if name in occurrences_by_name:
            continue
        if any(name.startswith(prefix) for prefix in code_prefixes):
            continue
        violations.append(
            f"handles: {name} is documented but has no setObjectName in app"
        )
    for prefix in sorted(documented.required_prefixes):
        if any(name.startswith(prefix) for name in occurrences_by_name):
            continue
        if any(
            prefix.startswith(code_prefix) or code_prefix.startswith(prefix)
            for code_prefix in code_prefixes
        ):
            continue
        violations.append(
            f"handles: {prefix}* is documented but has no setObjectName in app"
        )
    return violations


def _code_violations(
    documented: _DocumentedHandles,
    occurrences_by_name: Mapping[str, list[_Occurrence]],
    code_prefixes: frozenset[str],
) -> list[str]:
    violations: list[str] = []
    for name in sorted(occurrences_by_name):
        occurrences = occurrences_by_name[name]
        documented_name = name in documented.mentioned or any(
            name.startswith(prefix) for prefix in documented.mentioned_prefixes
        )
        if documented_name and name not in _DUPLICATE_LIMITS:
            continue
        limit = _DUPLICATE_LIMITS.get(name, 0)
        if len(occurrences) <= limit:
            continue
        occurrence = occurrences[limit]
        if limit == 0:
            violations.append(
                f"handles: {occurrence.path}:{occurrence.line_number}: "
                f"{name} is not documented in {_HANDLES_PATH.as_posix()}"
            )
        elif name in _DUPLICATE_LIMITS:
            violations.append(
                f"handles: {occurrence.path}:{occurrence.line_number}: "
                f"{name} has {len(occurrences)} setObjectName assignments; "
                f"duplicate allowlist permits {limit}"
            )

    for prefix in sorted(code_prefixes):
        if any(name.startswith(prefix) for name in documented.mentioned):
            continue
        if any(
            prefix.startswith(wildcard) or wildcard.startswith(prefix)
            for wildcard in documented.mentioned_prefixes
        ):
            continue
        violations.append(
            f"handles: dynamic setObjectName prefix {prefix} is not documented in "
            f"{_HANDLES_PATH.as_posix()}"
        )
    return violations
