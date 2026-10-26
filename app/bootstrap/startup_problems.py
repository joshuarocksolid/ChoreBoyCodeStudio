"""Startup problems the shell can show, and which ones the user has dismissed.

Dismissal is stored in the local state root, one id per problem, so hiding
history does not hide a shared-settings failure.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Sequence

from app.bootstrap.state_migration import (
    MigrationOutcome,
    SettingsImportFailed,
    SettingsImported,
)
from app.bootstrap.state_roots import SettingsRootChoice
from app.core.models import RuntimeIssue

HELP_LINE = "Click Copy Details and post them to the LibrePy group."
_HELP_CLAUSE = "click Copy Details and post them to the LibrePy group."
DISMISSALS_FILENAME = "startup_dismissals.json"
SHARED_SETTINGS_PROBLEM_ID = "shared-settings-unavailable"
HISTORY_PROBLEM_ID = "local-history-off"
SYMBOL_PROBLEM_ID = "symbol-index-off"
SETTINGS_IMPORTED_ID = "settings-imported"
SETTINGS_IMPORT_FAILED_ID = "settings-import-failed"

STILL_WORKING = (
    "Opening, editing, and saving files",
    "Running, debugging, and packaging projects",
    "Settings and recent projects",
)

_ISSUE_IDS = {
    "runtime.local_history_disabled": HISTORY_PROBLEM_ID,
    "runtime.symbol_index_disabled": SYMBOL_PROBLEM_ID,
}


@dataclass(frozen=True)
class StartupProblem:
    """One card in the startup-problems dialog."""

    problem_id: str
    title: str
    summary: str
    folder: str
    error: str
    fix: str
    kind: str = "problem"


def assemble_startup_problems(
    *,
    degraded_issues: Sequence[RuntimeIssue],
    history_folder: str,
    symbol_folder: str,
    settings_choice: Optional[SettingsRootChoice],
    migration: Optional[MigrationOutcome],
) -> tuple[StartupProblem, ...]:
    """Build the cards for this launch from the records startup already has."""
    problems: list[StartupProblem] = []
    for issue in degraded_issues:
        problem = _problem_from_issue(issue, history_folder=history_folder, symbol_folder=symbol_folder)
        if problem is not None:
            problems.append(problem)
    shared = _shared_settings_problem(settings_choice)
    if shared is not None:
        problems.append(shared)
    imported = _migration_problem(migration)
    if imported is not None:
        problems.append(imported)
    return tuple(problems)


def select_visible_problems(
    problems: Sequence[StartupProblem],
    dismissed_ids: Iterable[str],
) -> tuple[StartupProblem, ...]:
    """Drop problems the user asked not to see again. Other problems stay."""
    hidden = set(dismissed_ids)
    return tuple(problem for problem in problems if problem.problem_id not in hidden)


def load_dismissed_problem_ids(local_root: Path) -> frozenset[str]:
    path = local_root / DISMISSALS_FILENAME
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return frozenset()
    if not isinstance(payload, dict):
        return frozenset()
    raw_ids = payload.get("ids")
    if not isinstance(raw_ids, list):
        return frozenset()
    return frozenset(item for item in raw_ids if isinstance(item, str) and item)


def remember_dismissed_problem_ids(local_root: Path, problem_ids: Iterable[str]) -> None:
    """Add ids. A second call with the same ids leaves the file unchanged in meaning."""
    remembered = set(load_dismissed_problem_ids(local_root))
    remembered.update(item for item in problem_ids if item)
    local_root.mkdir(parents=True, exist_ok=True)
    path = local_root / DISMISSALS_FILENAME
    path.write_text(
        json.dumps({"ids": sorted(remembered)}, indent=2) + "\n",
        encoding="utf-8",
    )


def startup_dialog_title(problems: Sequence[StartupProblem]) -> str:
    real = [problem for problem in problems if problem.kind == "problem"]
    if not real and problems:
        return "CBCS imported settings"
    count = len(real) or len(problems)
    if count == 1:
        return "CBCS opened with a problem"
    return f"CBCS opened with {count} problems"


def startup_problem_copy_text(
    problems: Sequence[StartupProblem],
    *,
    log_path: str,
    app_version: str,
    freecad_version: str,
    python_version: str,
) -> str:
    blocks = [
        f"ChoreBoy Code Studio {app_version}",
        f"FreeCAD {freecad_version}",
        f"Python {python_version}",
        "",
    ]
    for problem in problems:
        blocks.extend(
            [
                problem.title,
                f"Folder: {problem.folder}",
                f"Error: {problem.error}",
                "",
            ]
        )
    blocks.append(f"Startup log: {log_path}")
    blocks.append(HELP_LINE)
    return "\n".join(blocks)


def _problem_from_issue(
    issue: RuntimeIssue,
    *,
    history_folder: str,
    symbol_folder: str,
) -> Optional[StartupProblem]:
    problem_id = _ISSUE_IDS.get(issue.issue_id)
    if problem_id is None:
        return None
    reason = str(issue.evidence.get("reason") or issue.summary)
    if problem_id == HISTORY_PROBLEM_ID:
        return StartupProblem(
            problem_id=problem_id,
            title="Local history is off",
            summary=(
                "CBCS could not lock its history folder, so it will not save "
                "earlier versions of your files this session."
            ),
            folder=history_folder,
            error=reason,
            fix=f"Restart CBCS. If you see this again, {_HELP_CLAUSE}",
        )
    return StartupProblem(
        problem_id=problem_id,
        title="Symbol index is off",
        summary=(
            "CBCS could not open its symbol cache, so project-wide symbol search "
            "stays off this session."
        ),
        folder=symbol_folder,
        error=reason,
        fix=f"Restart CBCS. If you see this again, {_HELP_CLAUSE}",
    )


def _shared_settings_problem(choice: Optional[SettingsRootChoice]) -> Optional[StartupProblem]:
    if choice is None or not choice.fell_back_to_local:
        return None
    return StartupProblem(
        problem_id=SHARED_SETTINGS_PROBLEM_ID,
        title="Shared settings are not available",
        summary=(
            "CBCS could not use the shared settings folder, so it is using this "
            "computer's own settings. Changes you make now stay on this computer."
        ),
        folder=str(choice.requested_path or choice.path),
        error=choice.error or "The shared settings folder could not be written.",
        fix=f"Check that this folder exists on this computer, then restart CBCS. {HELP_LINE}",
    )


def _migration_problem(outcome: Optional[MigrationOutcome]) -> Optional[StartupProblem]:
    if isinstance(outcome, SettingsImported):
        return StartupProblem(
            problem_id=SETTINGS_IMPORTED_ID,
            title="Settings were imported",
            summary=outcome.message,
            folder=str(outcome.source),
            error="",
            fix=HELP_LINE,
            kind="notice",
        )
    if isinstance(outcome, SettingsImportFailed):
        return StartupProblem(
            problem_id=SETTINGS_IMPORT_FAILED_ID,
            title="Settings were not imported",
            summary="CBCS found leftover settings and could not copy them.",
            folder=str(outcome.source),
            error=outcome.error,
            fix=HELP_LINE,
        )
    return None
