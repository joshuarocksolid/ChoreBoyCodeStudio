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
_DUPLICATE_LIMITS = {
    "shell.editorTabs.textEditor": 1,
    "shell.explorerAction": 2,
    "shell.welcome.onboardingActionBtn": 5,
}
_UNDOCUMENTED_LIMITS = {
    "shell.action.file.autoSave": 1,
    "shell.bottom.pythonConsole.clearBtn": 1,
    "shell.bottom.pythonConsoleContainer": 1,
    "shell.bottom.runLog.clearBtn": 1,
    "shell.bottom.runLog.metaLabel": 1,
    "shell.bottom.runLog.openBtn": 1,
    "shell.bottom.runLog.statusDot": 1,
    "shell.bottom.runLog.toolbar": 1,
    "shell.centerPanel": 1,
    "shell.centralWidget": 1,
    "shell.debug.commandInputRow": 1,
    "shell.debug.leftSplitter": 1,
    "shell.debug.mainSplitter": 1,
    "shell.debug.output": 1,
    "shell.debug.rightSplitter": 1,
    "shell.debug.sectionBtn": 6,
    "shell.debug.sectionCount": 1,
    "shell.debug.sectionHeader": 1,
    "shell.debug.sectionTitle": 1,
    "shell.debug.statusDot": 1,
    "shell.debug.statusHeader": 1,
    "shell.debug.threadsTree": 1,
    "shell.debug.watchInputRow": 1,
    "shell.debug.watchTree": 1,
    "shell.dialogChrome.body": 1,
    "shell.dialogChrome.footer": 1,
    "shell.dialogChrome.header": 1,
    "shell.dialogChrome.icon": 1,
    "shell.dialogChrome.meta.chip": 1,
    "shell.dialogChrome.metaRow": 1,
    "shell.dialogChrome.subtitle": 1,
    "shell.dialogChrome.title": 1,
    "shell.diffView": 1,
    "shell.diffView.afterPane": 1,
    "shell.diffView.beforePane": 1,
    "shell.diffView.inline": 1,
    "shell.diffView.message": 1,
    "shell.diffView.modeButton.inline": 1,
    "shell.diffView.modeButton.sideBySide": 1,
    "shell.diffView.modeToolbar": 1,
    "shell.diffView.paneLabel": 2,
    "shell.diffView.splitter": 1,
    "shell.editorPage": 1,
    "shell.explorerHeader": 1,
    "shell.explorerPage": 1,
    "shell.fieldAction.button": 1,
    "shell.findBar.caseBtn": 1,
    "shell.findBar.chevronBtn": 1,
    "shell.findBar.closeBtn": 1,
    "shell.findBar.findRow": 1,
    "shell.findBar.matchCount": 1,
    "shell.findBar.navGroup": 1,
    "shell.findBar.prevBtn": 1,
    "shell.findBar.regexBtn": 1,
    "shell.findBar.replaceAllBtn": 1,
    "shell.findBar.replaceBtn": 1,
    "shell.findBar.replaceRow": 1,
    "shell.findBar.topRow": 1,
    "shell.findBar.wordBtn": 1,
    "shell.helpDialog.browser": 1,
    "shell.helpDialog.closeBtn": 1,
    "shell.helpDialog.footer": 1,
    "shell.helpDialog.header": 1,
    "shell.helpDialog.icon": 1,
    "shell.helpDialog.title": 1,
    "shell.leftRegion.body": 1,
    "shell.leftRegion.title": 1,
    "shell.localHistoryDialog.compareCurrent": 1,
    "shell.localHistoryDialog.compareLabel": 1,
    "shell.localHistoryDialog.comparePrevious": 1,
    "shell.localHistoryDialog.revisionTree": 1,
    "shell.localHistoryDialog.splitter": 1,
    "shell.localHistoryDialog.toolbar": 1,
    "shell.markdownEditorPane.modeGroup": 1,
    "shell.markdownEditorPane.refreshButton": 1,
    "shell.markdownEditorPane.splitter": 1,
    "shell.markdownEditorPane.status": 1,
    "shell.markdownEditorPane.title": 1,
    "shell.markdownEditorPane.toolbar": 1,
    "shell.outlinePanel": 1,
    "shell.outlinePanel.body": 1,
    "shell.outlinePanel.chevron": 1,
    "shell.outlinePanel.emptyLabel": 1,
    "shell.outlinePanel.fileLabel": 1,
    "shell.outlinePanel.filter": 1,
    "shell.outlinePanel.filterRow": 1,
    "shell.outlinePanel.header": 1,
    "shell.outlinePanel.title": 1,
    "shell.outlinePanel.tree": 1,
    "shell.problemsPanel.emptyLabel": 1,
    "shell.problemsPanel.filterErrors": 1,
    "shell.problemsPanel.filterInfo": 1,
    "shell.problemsPanel.filterWarnings": 1,
    "shell.problemsPanel.sourceLabel": 1,
    "shell.problemsPanel.toolbar": 1,
    "shell.problemsPanel.tree": 1,
    "shell.quickOpen": 1,
    "shell.quickOpen.count": 1,
    "shell.quickOpen.empty": 1,
    "shell.quickOpen.results": 1,
    "shell.quickOpen.resultsContainer": 1,
    "shell.quickSymbolDialog.count": 1,
    "shell.quickSymbolDialog.empty": 1,
    "shell.quickSymbolDialog.input": 1,
    "shell.quickSymbolDialog.list": 1,
    "shell.runConfigurationsDialog.addButton": 1,
    "shell.runConfigurationsDialog.configsDetailForm": 1,
    "shell.runConfigurationsDialog.configsDetailPanel": 1,
    "shell.runConfigurationsDialog.configsDetailScroll": 1,
    "shell.runConfigurationsDialog.configsGroup": 1,
    "shell.runConfigurationsDialog.defaultArgvGroup": 1,
    "shell.runConfigurationsDialog.defaultEntryLabel": 1,
    "shell.runConfigurationsDialog.deleteButton": 1,
    "shell.runConfigurationsDialog.duplicateButton": 1,
    "shell.runConfigurationsDialog.emptyState": 1,
    "shell.runConfigurationsDialog.entryField": 1,
    "shell.runConfigurationsDialog.error": 1,
    "shell.runConfigurationsDialog.list": 1,
    "shell.runConfigurationsDialog.nameField": 1,
    "shell.runConfigurationsDialog.workingDirField": 1,
    "shell.runEnvOverridesDialog": 1,
    "shell.runEnvOverridesDialog.table": 1,
    "shell.runFormSection": 1,
    "shell.runFormSection.title": 1,
    "shell.runWithArgumentsDialog.advancedGroup": 1,
    "shell.runWithArgumentsDialog.commandPreview": 1,
    "shell.runWithArgumentsDialog.entry": 1,
    "shell.runWithArgumentsDialog.error": 1,
    "shell.runWithArgumentsDialog.footerSeparator": 1,
    "shell.runWithArgumentsDialog.formScroll": 1,
    "shell.runWithArgumentsDialog.formScrollContent": 1,
    "shell.runWithArgumentsDialog.overridesSummary": 1,
    "shell.runWithArgumentsDialog.overridesTitle": 1,
    "shell.runWithArgumentsDialog.overridesToggle": 1,
    "shell.runWithArgumentsDialog.prefill": 1,
    "shell.runWithArgumentsDialog.wdHelper": 1,
    "shell.runWithArgumentsDialog.workingDir": 1,
    "shell.runtimeCenterDialog.closeButton": 1,
    "shell.runtimeCenterDialog.detailBrowser": 1,
    "shell.runtimeCenterDialog.footer": 1,
    "shell.runtimeCenterDialog.header": 1,
    "shell.runtimeCenterDialog.helpButton": 1,
    "shell.runtimeCenterDialog.issueList": 1,
    "shell.runtimeCenterDialog.summary": 1,
    "shell.runtimeCenterDialog.title": 1,
    "shell.searchSidebar.caseBtn": 1,
    "shell.searchSidebar.clearBtn": 1,
    "shell.searchSidebar.excludeInput": 1,
    "shell.searchSidebar.filterToggle": 1,
    "shell.searchSidebar.filtersContainer": 1,
    "shell.searchSidebar.header": 1,
    "shell.searchSidebar.headerRow": 1,
    "shell.searchSidebar.includeInput": 1,
    "shell.searchSidebar.noResults": 1,
    "shell.searchSidebar.regexBtn": 1,
    "shell.searchSidebar.replaceAllBtn": 1,
    "shell.searchSidebar.replaceInput": 1,
    "shell.searchSidebar.replaceToggle": 1,
    "shell.searchSidebar.summary": 1,
    "shell.searchSidebar.wordBtn": 1,
    "shell.settingsDialog.addExcludeBtn": 1,
    "shell.settingsDialog.addLocalHistoryExcludeBtn": 1,
    "shell.settingsDialog.appearanceGroup": 1,
    "shell.settingsDialog.buttonBox": 1,
    "shell.settingsDialog.cancelBtn": 1,
    "shell.settingsDialog.editorGroup": 1,
    "shell.settingsDialog.editorResetGlobal": 1,
    "shell.settingsDialog.fileExcludeInput": 1,
    "shell.settingsDialog.fileExcludesGroup": 1,
    "shell.settingsDialog.fileExcludesHelp": 1,
    "shell.settingsDialog.fileExcludesList": 1,
    "shell.settingsDialog.generalScroll": 1,
    "shell.settingsDialog.generalScrollContent": 1,
    "shell.settingsDialog.intelligenceGroup": 1,
    "shell.settingsDialog.intelligenceResetGlobal": 1,
    "shell.settingsDialog.linterProviderGroup": 1,
    "shell.settingsDialog.linterProviderScopeHint": 1,
    "shell.settingsDialog.linterResetGlobal": 1,
    "shell.settingsDialog.linterTable": 1,
    "shell.settingsDialog.localHistoryExcludeInput": 1,
    "shell.settingsDialog.localHistoryExcludesHelp": 1,
    "shell.settingsDialog.localHistoryExcludesList": 1,
    "shell.settingsDialog.localHistoryGroup": 1,
    "shell.settingsDialog.localHistoryHelp": 1,
    "shell.settingsDialog.okBtn": 1,
    "shell.settingsDialog.outputGroup": 1,
    "shell.settingsDialog.outputResetGlobal": 1,
    "shell.settingsDialog.removeExcludeBtn": 1,
    "shell.settingsDialog.removeLocalHistoryExcludeBtn": 1,
    "shell.settingsDialog.resetAllShortcuts": 1,
    "shell.settingsDialog.resetExcludesBtn": 1,
    "shell.settingsDialog.resetLocalHistoryBtn": 1,
    "shell.settingsDialog.scopeBanner": 1,
    "shell.settingsDialog.scopeHeader": 1,
    "shell.settingsDialog.scopeSegmented": 1,
    "shell.settingsDialog.shortcutConflict": 1,
    "shell.settingsDialog.shortcutSearch": 1,
    "shell.settingsDialog.shortcutTable": 1,
    "shell.settingsDialog.syntaxColorTable": 1,
    "shell.settingsDialog.syntaxThemeInput": 1,
    "shell.settingsDialog.syntaxValidation": 1,
    "shell.settingsDialog.tabs": 1,
    "shell.settingsDialog.validationBanner": 1,
    "shell.testExplorer.countSkipped": 1,
    "shell.testExplorer.debugFailedBtn": 1,
    "shell.testExplorer.filterBar": 1,
    "shell.testExplorer.statusBar": 1,
    "shell.testExplorer.statusDot": 1,
    "shell.testExplorer.title": 1,
    "shell.testExplorer.toolbar": 1,
    "shell.toolbar.separator": 1,
    "shell.topSplitter": 1,
    "shell.unsavedChangesDialog.fileList": 1,
    "shell.unsavedChangesDialog.row": 1,
    "shell.unsavedChangesDialog.row.name": 1,
    "shell.unsavedChangesDialog.row.path": 1,
    "shell.verticalSplitter": 1,
    "shell.welcome.btnRow": 1,
    "shell.welcome.container": 1,
    "shell.welcome.emptyLabel": 1,
    "shell.welcome.onboardingActionRow": 2,
    "shell.welcome.onboardingChecklist": 1,
    "shell.welcome.onboardingReminder": 1,
    "shell.welcome.onboardingRuntimeSummary": 1,
    "shell.welcome.onboardingStateRow": 1,
    "shell.welcome.onboardingTitle": 1,
    "shell.welcome.recentLabel": 1,
    "shell.welcome.subtitle": 1,
    "shell.welcome.title": 1,
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
    return _DocumentedHandles(
        required,
        required_prefixes,
        mentioned,
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
        if documented_name:
            limit = _DUPLICATE_LIMITS.get(name, 1)
        else:
            limit = _UNDOCUMENTED_LIMITS.get(name, 0)
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
        elif name in _UNDOCUMENTED_LIMITS:
            violations.append(
                f"handles: {occurrence.path}:{occurrence.line_number}: "
                f"{name} has {len(occurrences)} setObjectName assignments; "
                f"legacy allowance permits {limit}"
            )
        else:
            violations.append(
                f"handles: {occurrence.path}:{occurrence.line_number}: "
                f"{name} has {len(occurrences)} setObjectName assignments; "
                "documented handles must be unique"
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
