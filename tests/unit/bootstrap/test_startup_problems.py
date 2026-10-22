"""Startup problem list and dismissal."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.bootstrap.startup_problems import (
    HISTORY_PROBLEM_ID,
    SHARED_SETTINGS_PROBLEM_ID,
    StartupProblem,
    load_dismissed_problem_ids,
    remember_dismissed_problem_ids,
    select_visible_problems,
)
from app.core.models import RuntimeIssue
from app.bootstrap.startup_problems import assemble_startup_problems

pytestmark = pytest.mark.unit


def _history_issue() -> RuntimeIssue:
    return RuntimeIssue(
        issue_id="runtime.local_history_disabled",
        workflow="startup",
        severity="degraded",
        title="Local history is off",
        summary="Local history is off: locked",
        why_it_happened="locked",
        evidence={"reason": "Permission denied (errno 13) taking a file lock"},
    )


def _shared_problem() -> StartupProblem:
    return StartupProblem(
        problem_id=SHARED_SETTINGS_PROBLEM_ID,
        title="Shared settings are not available",
        summary="using local settings",
        folder="/home/default/share/net1/CBCS/settings",
        error="No such file or directory (errno 2)",
        fix="Check the share.",
    )


def test_dialog_inputs_list_every_problem_and_dismissal_hides_only_that_one(tmp_path: Path) -> None:
    problems = assemble_startup_problems(
        degraded_issues=[_history_issue()],
        history_folder="/home/default/FreeCAD/CBCS/state/history",
        symbol_folder="/home/default/FreeCAD/CBCS/state/cache",
        settings_choice=None,
        migration=None,
    )
    problems = problems + (_shared_problem(),)
    assert [problem.problem_id for problem in problems] == [HISTORY_PROBLEM_ID, SHARED_SETTINGS_PROBLEM_ID]
    assert "history" in problems[0].folder

    visible = select_visible_problems(problems, [])
    assert [problem.title for problem in visible] == [
        "Local history is off",
        "Shared settings are not available",
    ]
    remember_dismissed_problem_ids(tmp_path, [HISTORY_PROBLEM_ID])
    hidden = select_visible_problems(problems, load_dismissed_problem_ids(tmp_path))
    assert [problem.problem_id for problem in hidden] == [SHARED_SETTINGS_PROBLEM_ID]
    remember_dismissed_problem_ids(tmp_path, [HISTORY_PROBLEM_ID])
    assert load_dismissed_problem_ids(tmp_path) == frozenset({HISTORY_PROBLEM_ID})
