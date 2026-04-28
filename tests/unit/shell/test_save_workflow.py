"""Unit tests for dirty-buffer save workflow decisions."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.core import constants  # noqa: E402
from app.shell.document_safety import (  # noqa: E402
    DocumentCloseIntent,
    DocumentSafetyDecision,
    DocumentScope,
)
from app.shell.save_workflow import SaveWorkflow  # noqa: E402

pytestmark = pytest.mark.unit


class _FakeHistoryWorkflow:
    def __init__(self) -> None:
        self.discarded: list[tuple[str, ...]] = []
        self.kept: list[tuple[str, ...]] = []

    def discard_drafts_for_paths(self, paths) -> None:  # type: ignore[no-untyped-def]
        self.discarded.append(tuple(paths))

    def keep_drafts_for_paths(self, paths) -> None:  # type: ignore[no-untyped-def]
        self.kept.append(tuple(paths))


def _dirty_tab(path: str = "/tmp/project/main.py") -> SimpleNamespace:
    return SimpleNamespace(
        file_path=path,
        display_name="main.py",
        current_content="print('draft')\n",
        original_content="print('disk')\n",
        last_known_mtime=1.0,
        is_dirty=True,
    )


def _window_with_tabs(*tabs: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(
        _editor_manager=SimpleNamespace(all_tabs=lambda: list(tabs)),
        _local_history_workflow=_FakeHistoryWorkflow(),
        _editor_exit_behavior=constants.UI_EDITOR_EXIT_BEHAVIOR_DEFAULT,
    )


def test_request_unsaved_changes_decision_uses_keep_exit_policy() -> None:
    window = _window_with_tabs(_dirty_tab())
    window._editor_exit_behavior = constants.UI_EDITOR_EXIT_BEHAVIOR_KEEP_UNSAVED
    workflow = SaveWorkflow(window)

    decision = workflow.request_unsaved_changes_decision(
        "exiting",
        scope=DocumentScope.APPLICATION,
        allow_keep_for_next_launch=True,
    )

    assert decision.intent is DocumentCloseIntent.KEEP_FOR_NEXT_LAUNCH
    assert decision.affected_paths == ("/tmp/project/main.py",)


def test_apply_unsaved_changes_decision_discards_drafts() -> None:
    window = _window_with_tabs()
    workflow = SaveWorkflow(window)
    decision = DocumentSafetyDecision(
        intent=DocumentCloseIntent.DISCARD,
        scope=DocumentScope.PROJECT,
        dirty_buffers=(
            SimpleNamespace(file_path="/tmp/project/main.py"),  # type: ignore[arg-type]
        ),
    )

    assert workflow.apply_unsaved_changes_decision(decision) is True
    assert window._local_history_workflow.discarded == [("/tmp/project/main.py",)]


def test_apply_unsaved_changes_decision_keeps_drafts_for_next_launch() -> None:
    window = _window_with_tabs()
    workflow = SaveWorkflow(window)
    decision = DocumentSafetyDecision(
        intent=DocumentCloseIntent.KEEP_FOR_NEXT_LAUNCH,
        scope=DocumentScope.APPLICATION,
        dirty_buffers=(
            SimpleNamespace(file_path="/tmp/project/main.py"),  # type: ignore[arg-type]
        ),
    )

    assert workflow.apply_unsaved_changes_decision(decision) is True
    assert window._local_history_workflow.kept == [("/tmp/project/main.py",)]
