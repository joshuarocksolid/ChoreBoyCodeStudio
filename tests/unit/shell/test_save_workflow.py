"""Unit tests for dirty-buffer save workflow decisions."""

# pyright: reportArgumentType=false

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.core import constants  # noqa: E402
from app.editors.editor_manager import EditorManager  # noqa: E402
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


class _FakeSaveDocumentHost:
    def __init__(
        self,
        *,
        editor_exit_behavior: str,
        editor_manager: object,
    ) -> None:
        self._editor_exit_behavior = editor_exit_behavior
        self._editor_manager = editor_manager

    def editor_manager(self) -> object:
        return self._editor_manager

    def dialog_parent(self) -> SimpleNamespace:
        return SimpleNamespace()

    def editor_exit_behavior(self) -> str:
        return self._editor_exit_behavior

    def refresh_save_action_states(self) -> None:
        return None

    def editor_auto_save(self) -> bool:
        return False

    def set_editor_auto_save(self, enabled: bool) -> None:
        return None

    def stop_auto_save_timer(self) -> None:
        return None

    def logger(self) -> object:
        return SimpleNamespace(info=lambda *_a, **_kw: None, warning=lambda *_a, **_kw: None)

    def has_editor_tabs_widget(self) -> bool:
        return False

    def editor_trim_trailing_whitespace_on_save(self) -> bool:
        return True

    def editor_insert_final_newline_on_save(self) -> bool:
        return True

    def editor_organize_imports_on_save(self) -> bool:
        return False

    def editor_format_on_save(self) -> bool:
        return False

    def resolve_python_tooling_project_root(self, file_path: str) -> str:
        return file_path

    def apply_text_to_open_tab(self, file_path: str, transformed_text: str) -> None:
        return None

    def intelligence_runtime_settings(self) -> object:
        return SimpleNamespace()

    def loaded_project(self) -> object | None:
        return None

    def project_inventory_snapshot(self) -> object:
        return None

    def workflow_broker(self) -> object:
        return object()

    def tab_index_for_path(self, file_path: str) -> int:
        return -1

    def refresh_tab_presentation(self, file_path: str) -> None:
        return None

    def update_editor_status_for_path(self, file_path: str) -> None:
        return None

    def rescan_project_from_disk(self, *, reload_plugins: bool, reindex: bool) -> None:
        return None

    def render_lint_for_file(self, file_path: str, *, trigger: str) -> None:
        return None

    def refresh_test_discovery(self) -> None:
        return None


def _dirty_tab(path: str = "/tmp/project/main.py") -> SimpleNamespace:
    return SimpleNamespace(
        file_path=path,
        display_name="main.py",
        current_content="print('draft')\n",
        original_content="print('disk')\n",
        last_known_mtime=1.0,
        is_dirty=True,
    )


def _build_workflow(
    *,
    tabs: tuple[SimpleNamespace, ...] = (),
    editor_exit_behavior: str = constants.UI_EDITOR_EXIT_BEHAVIOR_DEFAULT,
) -> tuple[SaveWorkflow, _FakeHistoryWorkflow]:
    history = _FakeHistoryWorkflow()
    editor_manager = SimpleNamespace(all_tabs=lambda: list(tabs))
    workflow = SaveWorkflow(
        local_history=history,
        intelligence_cache=SimpleNamespace(start_symbol_indexing=lambda *_a, **_kw: None),
        host=_FakeSaveDocumentHost(
            editor_exit_behavior=editor_exit_behavior,
            editor_manager=editor_manager,
        ),
        settings_service=SimpleNamespace(update_global=lambda updater: updater({})),
    )
    return workflow, history


def test_request_unsaved_changes_decision_uses_keep_exit_policy() -> None:
    workflow, _history = _build_workflow(
        tabs=(_dirty_tab(),),
        editor_exit_behavior=constants.UI_EDITOR_EXIT_BEHAVIOR_KEEP_UNSAVED,
    )

    decision = workflow.request_unsaved_changes_decision(
        "exiting",
        scope=DocumentScope.APPLICATION,
        allow_keep_for_next_launch=True,
    )

    assert decision.intent is DocumentCloseIntent.KEEP_FOR_NEXT_LAUNCH
    assert decision.affected_paths == ("/tmp/project/main.py",)


def test_apply_unsaved_changes_decision_discards_drafts() -> None:
    workflow, history = _build_workflow()
    decision = DocumentSafetyDecision(
        intent=DocumentCloseIntent.DISCARD,
        scope=DocumentScope.PROJECT,
        dirty_buffers=(
            SimpleNamespace(file_path="/tmp/project/main.py"),  # type: ignore[arg-type]
        ),
    )

    assert workflow.apply_unsaved_changes_decision(decision) is True
    assert history.discarded == [("/tmp/project/main.py",)]


def test_apply_unsaved_changes_decision_keeps_drafts_for_next_launch() -> None:
    workflow, history = _build_workflow()
    decision = DocumentSafetyDecision(
        intent=DocumentCloseIntent.KEEP_FOR_NEXT_LAUNCH,
        scope=DocumentScope.APPLICATION,
        dirty_buffers=(
            SimpleNamespace(file_path="/tmp/project/main.py"),  # type: ignore[arg-type]
        ),
    )

    assert workflow.apply_unsaved_changes_decision(decision) is True
    assert history.kept == [("/tmp/project/main.py",)]


def test_confirm_proceed_before_tree_delete_blocks_on_cancel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow, _history = _build_workflow(tabs=(_dirty_tab(),))
    monkeypatch.setattr(
        workflow,
        "request_unsaved_changes_decision",
        lambda *args, **kwargs: DocumentSafetyDecision(  # type: ignore[assignment]
            intent=DocumentCloseIntent.CANCEL,
            scope=DocumentScope.PROJECT,
            dirty_buffers=(),
        ),
    )

    assert workflow.confirm_proceed_before_tree_delete(["/tmp/project/main.py"]) is False


def test_confirm_proceed_before_tree_delete_proceeds_when_no_dirty_tabs() -> None:
    clean_tab = SimpleNamespace(
        file_path="/tmp/project/main.py",
        is_dirty=False,
    )
    workflow, _history = _build_workflow(tabs=(clean_tab,))

    assert workflow.confirm_proceed_before_tree_delete(["/tmp/project/main.py"]) is True


def test_save_tab_does_not_overwrite_a_conflicted_buffer(tmp_path: Path) -> None:
    file_path = tmp_path / "main.py"
    file_path.write_text("other\n", encoding="utf-8")
    manager = EditorManager()
    tab = manager.open_file(str(file_path)).tab
    tab.update_content("mine\n")
    tab.set_disk_conflict("changed", file_path.stat().st_mtime)
    prompts: list[str] = []

    class _PromptHost(_FakeSaveDocumentHost):
        def editor_auto_save(self) -> bool:
            return True

        def resolve_external_change_before_save(self, path: str) -> str:
            prompts.append(path)
            return "abort"

    workflow = SaveWorkflow(
        local_history=_FakeHistoryWorkflow(),
        intelligence_cache=SimpleNamespace(start_symbol_indexing=lambda *_a, **_kw: None),
        host=_PromptHost(
            editor_exit_behavior=constants.UI_EDITOR_EXIT_BEHAVIOR_DEFAULT,
            editor_manager=manager,
        ),
        settings_service=SimpleNamespace(update_global=lambda updater: updater({})),
    )

    assert workflow.save_tab(tab.file_path) is False
    assert prompts == [tab.file_path]
    assert file_path.read_text(encoding="utf-8") == "other\n"
    assert tab.current_content == "mine\n"


def test_auto_save_skips_a_conflicted_buffer(tmp_path: Path) -> None:
    file_path = tmp_path / "main.py"
    file_path.write_text("other\n", encoding="utf-8")
    manager = EditorManager()
    tab = manager.open_file(str(file_path)).tab
    tab.update_content("mine\n")
    tab.set_disk_conflict("changed", file_path.stat().st_mtime)
    prompts: list[str] = []

    class _PromptHost(_FakeSaveDocumentHost):
        def editor_auto_save(self) -> bool:
            return True

        def resolve_external_change_before_save(self, path: str) -> str:
            prompts.append(path)
            return "proceed"

    workflow = SaveWorkflow(
        local_history=_FakeHistoryWorkflow(),
        intelligence_cache=SimpleNamespace(start_symbol_indexing=lambda *_a, **_kw: None),
        host=_PromptHost(
            editor_exit_behavior=constants.UI_EDITOR_EXIT_BEHAVIOR_DEFAULT,
            editor_manager=manager,
        ),
        settings_service=SimpleNamespace(update_global=lambda updater: updater({})),
    )

    workflow.flush_auto_save_to_file()

    assert prompts == []
    assert file_path.read_text(encoding="utf-8") == "other\n"
    assert tab.current_content == "mine\n"
