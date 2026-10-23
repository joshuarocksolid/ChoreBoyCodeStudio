"""A sourced edit updates the dirty UI for the tab's path at the moment it fires."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.editors.editor_manager import EditorManager  # noqa: E402
from app.editors.editor_tab import EditorTabState  # noqa: E402
from app.shell.active_surface_chrome import ActiveSurfaceChrome  # noqa: E402
from app.shell.editor_tab_buffer_workflow import EditorTabBufferWorkflow  # noqa: E402
from app.shell.editor_tab_factory import EditorTabFactory  # noqa: E402
from app.shell.tab_content_providers import TabContentProviderRegistry  # noqa: E402

pytestmark = pytest.mark.unit


class _DirtySource:
    def current_text(self) -> str:
        return "edited"

    def is_dirty(self) -> bool:
        return True

    def mark_saved(self, saved_text: str) -> None:
        del saved_text

    def revision(self) -> int:
        return 2

    def subscribe_changed(self, listener: object) -> object:
        self.listener = listener
        return lambda: None


class _Host:
    def __init__(self) -> None:
        self.noted: list[str] = []
        self.timer_starts = 0
        self.save_refreshes = 0

    def editor_tabs_widget(self) -> object:
        return object()

    def local_history_note_source_changed(self, file_path: str) -> None:
        self.noted.append(file_path)

    def editor_auto_save(self) -> bool:
        return True

    def start_auto_save_to_file_timer(self) -> None:
        self.timer_starts += 1

    def local_history_discard_pending_autosave(self, file_path: str) -> None:
        del file_path

    def local_history_delete_draft(self, file_path: str) -> None:
        del file_path

    def refresh_save_action_states(self) -> None:
        self.save_refreshes += 1


class _Coordinator:
    def __init__(self, manager: EditorManager) -> None:
        self._manager = manager
        self.promoted: list[str] = []
        self.presented: list[str] = []

    def promote_preview_tab(self, file_path: str) -> bool:
        self.promoted.append(file_path)
        self._manager.promote_tab(file_path)
        return True

    def tab_index_for_path(self, file_path: str) -> int:
        del file_path
        return 0

    def refresh_tab_presentation(self, file_path: str) -> None:
        self.presented.append(file_path)


def test_source_change_after_rename_dirties_the_new_path(tmp_path: Path) -> None:
    old_path = str((tmp_path / "project" / "README.md").resolve())
    new_path = str((tmp_path / "project" / "NOTES.md").resolve())
    manager = EditorManager()
    tab = manager.open_file_with_content(old_path, "old", preview=True).tab
    tab.content_source = _DirtySource()  # type: ignore[assignment]
    manager.remap_paths_for_move(old_path, new_path)
    host = _Host()
    coordinator = _Coordinator(manager)
    workflow = EditorTabBufferWorkflow(
        host=host,  # type: ignore[arg-type]
        editor_manager=manager,
        editor_tabs_coordinator=coordinator,
        outline_workflow=SimpleNamespace(),
        markdown_workflow=SimpleNamespace(),
        tab_workflow=SimpleNamespace(),
        active_surface_chrome=ActiveSurfaceChrome(TabContentProviderRegistry()),
    )

    workflow.handle_content_source_changed(tab)

    assert coordinator.promoted == [new_path]
    assert coordinator.presented == [new_path]
    assert host.noted == [new_path]
    assert host.timer_starts == 1
    assert host.save_refreshes == 1
    assert manager.get_tab(new_path) is not None
    assert manager.get_tab(new_path).is_preview is False  # type: ignore[union-attr]


def test_attached_listener_reads_the_tab_path_when_it_fires(tmp_path: Path) -> None:
    old_path = str((tmp_path / "project" / "README.md").resolve())
    new_path = str((tmp_path / "project" / "NOTES.md").resolve())
    seen: list[str] = []
    source = _DirtySource()
    tab = EditorTabState(
        file_path=old_path,
        display_name="README.md",
        original_content="old",
        current_content="old",
    )
    window = SimpleNamespace(
        _editor_tab_workflow=SimpleNamespace(
            handle_content_source_changed=lambda current: seen.append(current.file_path)
        )
    )
    EditorTabFactory(window)._attach_content_source(tab, source)  # type: ignore[arg-type]

    tab.file_path = new_path
    source.listener()  # type: ignore[attr-defined]

    assert seen == [new_path]
    assert tab.content_source_unsubscribe is not None
