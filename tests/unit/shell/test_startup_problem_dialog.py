"""The problems dialog lists every card, and dismissal is per problem."""

from __future__ import annotations

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.qt.QtWidgets import QApplication, QCheckBox, QLabel  # noqa: E402

from app.bootstrap.startup_problems import HISTORY_PROBLEM_ID, SHARED_SETTINGS_PROBLEM_ID, StartupProblem  # noqa: E402
from app.shell.startup_dialogs import build_startup_problems_dialog, checked_problem_ids  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module", autouse=True)
def _qapp(qapp):  # type: ignore[no-untyped-def]
    return qapp


def test_problems_dialog_lists_each_problem_and_checks_one_box(_qapp: QApplication) -> None:
    problems = (
        StartupProblem(
            problem_id=HISTORY_PROBLEM_ID,
            title="Local history is off",
            summary="History stays off this session.",
            folder="/home/default/FreeCAD/CBCS/state/history",
            error="Permission denied (errno 13) taking a file lock",
            fix="Restart CBCS.",
        ),
        StartupProblem(
            problem_id=SHARED_SETTINGS_PROBLEM_ID,
            title="Shared settings are not available",
            summary="Using this computer's own settings.",
            folder="/home/default/share/net1/CBCS/settings",
            error="No such file or directory (errno 2)",
            fix="Check the share.",
        ),
    )
    dialog = build_startup_problems_dialog(None, problems, log_path="/tmp/app.log")
    texts = [label.text() for label in dialog.findChildren(QLabel)]
    assert "CBCS opened with 2 problems" in texts
    assert "Local history is off" in texts
    assert "Shared settings are not available" in texts
    assert "/home/default/FreeCAD/CBCS/state/history" in " ".join(texts)
    assert "/tmp/app.log" in texts
    boxes = dialog.findChildren(QCheckBox, "shell.startupProblems.dismiss")
    assert len(boxes) == 2
    boxes[0].setChecked(True)
    assert checked_problem_ids(dialog) == [HISTORY_PROBLEM_ID]
    dialog.deleteLater()
