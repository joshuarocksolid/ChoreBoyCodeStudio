"""Path-keyed close, delete, move, and reload for a surface with no source editor."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.editors.editor_manager import EditorManager  # noqa: E402
from app.shell.breakpoint_store import BreakpointStore  # noqa: E402
from app.shell.editor_sync_workflow import EditorDiskSyncSource, EditorSyncWorkflow  # noqa: E402
from app.shell.editor_tab_lifecycle_workflow import EditorTabLifecycleWorkflow  # noqa: E402
from app.shell.project_tree_controller import ProjectTreeController  # noqa: E402
from app.shell.project_tree_ui_workflow import ProjectTreeUiWorkflow  # noqa: E402
from app.shell.tab_content_providers import TabContentProviderRegistry, TabMatchContext  # noqa: E402

pytestmark = pytest.mark.unit


class _LazySurface:
    def __init__(self) -> None:
        self.released = 0
        self.changed: list[str] = []
        self.restored: list[tuple[str, str]] = []

    def source_editor(self) -> None:
        return None

    def close_blockers(self) -> tuple[str, ...]:
        return ()

    def release(self) -> None:
        self.released += 1

    def file_path_changed(self, new_path: str) -> None:
        self.changed.append(new_path)

    def restore_text(self, text: str, reason: str) -> None:
        self.restored.append((text, reason))


class _MarkdownProvider:
    provider_id = "markdown"
    priority = 0

    def matches(self, file_path: str, context: TabMatchContext) -> bool:
        del context
        return file_path.endswith(".md")


class _Tabs:
    def __init__(self, file_path: str) -> None:
        self._file_path = file_path
        self.removed: list[int] = []

    def tabToolTip(self, index: int) -> str:  # noqa: N802
        return self._file_path if index == 0 else ""

    def removeTab(self, index: int) -> None:  # noqa: N802
        self.removed.append(index)


class _Workspace:
    def __init__(self) -> None:
        self.widgets: dict[str, object] = {}

    def pop_editor(self, file_path: str) -> object | None:
        return self.widgets.pop(file_path, None)


class _CloseHost:
    def __init__(
        self,
        registry: TabContentProviderRegistry,
        tabs: _Tabs,
        workspace: _Workspace,
    ) -> None:
        self._registry = registry
        self._tabs = tabs
        self._workspace = workspace
        self.diagnostics: dict[str, list[object]] = {}

    def editor_tabs_widget(self) -> _Tabs:
        return self._tabs

    def parent_widget(self) -> None:
        return None

    def tab_content_registry(self) -> TabContentProviderRegistry:
        return self._registry

    def workspace_controller(self) -> _Workspace:
        return self._workspace

    def debug_execution_editor(self) -> None:
        return None

    def clear_debug_execution_indicator(self) -> None:
        return None

    def stored_lint_diagnostics(self) -> dict[str, list[object]]:
        return self.diagnostics

    def render_merged_problems_panel(self) -> None:
        return None

    def refresh_save_action_states(self) -> None:
        return None

    def refresh_run_action_states(self) -> None:
        return None

    def local_history_forget_source(self, file_path: str) -> None:
        del file_path


def _lifecycle(
    manager: EditorManager,
    registry: TabContentProviderRegistry,
    file_path: str,
) -> tuple[EditorTabLifecycleWorkflow, _LazySurface]:
    surface = _LazySurface()
    registry.bind(file_path, surface, "markdown")  # type: ignore[arg-type]
    host = _CloseHost(registry, _Tabs(file_path), _Workspace())
    workflow = EditorTabLifecycleWorkflow(
        host=host,  # type: ignore[arg-type]
        editor_manager=manager,
        editor_tabs_coordinator=SimpleNamespace(tab_index_for_path=lambda _path: 0),
        save_workflow=SimpleNamespace(),
        debug_control_workflow=SimpleNamespace(
            breakpoint_store=SimpleNamespace(clear_file=lambda _path: None),
            refresh_breakpoints_list=lambda: None,
        ),
        markdown_workflow=SimpleNamespace(refresh_markdown_action_states=lambda: None),
        tab_workflow=SimpleNamespace(),
    )
    return workflow, surface


def test_close_releases_a_surface_with_no_source_editor(tmp_path: Path) -> None:
    file_path = str((tmp_path / "NOTES.md").resolve())
    manager = EditorManager()
    manager.open_file_with_content(file_path, "hello\n", original_content="hello\n")
    registry = TabContentProviderRegistry()
    workflow, surface = _lifecycle(manager, registry, file_path)

    workflow.handle_tab_close_requested(0)

    assert surface.released == 1
    assert registry.surface_for_path(file_path) is None
    assert manager.get_tab(file_path) is None


def test_delete_releases_a_tab_that_has_no_editor_widget(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    file_path = str((root / "NOTES.md").resolve())
    manager = EditorManager()
    manager.open_file_with_content(file_path, "hello\n", original_content="hello\n")
    registry = TabContentProviderRegistry()
    workflow, surface = _lifecycle(manager, registry, file_path)
    controller = ProjectTreeController()

    controller.close_deleted_editor_paths(
        str(root.resolve()),
        open_tab_paths=manager.open_paths(),
        tab_index_for_path=lambda _path: 0,
        remove_tab_at_index=lambda _index: None,
        release_tab_content=workflow.release_tab_content,
        close_editor_file=manager.close_file,
        breakpoint_store=BreakpointStore(),
        refresh_breakpoints_list=lambda: None,
    )

    assert surface.released == 1
    assert registry.surface_for_path(file_path) is None
    assert manager.get_tab(file_path) is None


def test_move_rekeys_a_surface_with_no_source_editor(tmp_path: Path) -> None:
    old_path = str((tmp_path / "README.md").resolve())
    new_path = str((tmp_path / "NOTES.md").resolve())
    surface = _LazySurface()
    registry = TabContentProviderRegistry()
    registry.register(_MarkdownProvider())  # type: ignore[arg-type]
    registry.bind(old_path, surface, "markdown")  # type: ignore[arg-type]
    host = SimpleNamespace(
        tab_content_registry=lambda: registry,
        loaded_project=lambda: None,
        editor_tabs_coordinator=lambda: SimpleNamespace(
            replace_tab_content_widget=lambda _path, _widget: None
        ),
    )
    ui = ProjectTreeUiWorkflow(host)  # type: ignore[arg-type]
    controller = ProjectTreeController()

    controller.apply_path_move_updates(
        old_path,
        new_path,
        remap_editor_paths=lambda _old, _new: {old_path: new_path},
        editor_widgets_by_path={},
        tab_index_for_path=lambda _path: -1,
        update_tab_path_and_name=lambda _index, _path: None,
        breakpoint_store=BreakpointStore(),
        apply_breakpoints_to_widget=lambda _widget, _lines: None,
        update_widget_language=lambda _widget, _path: None,
        refresh_breakpoints_list=lambda: None,
        maybe_rewrite_imports=lambda _source, _destination: None,
        rekey_tab_content=ui.rekey_tab_content,
    )

    assert surface.released == 0
    assert surface.changed == [new_path]
    assert registry.surface_for_path(new_path) is surface
    assert registry.surface_for_path(old_path) is None


def test_external_reload_applies_without_an_editor_widget(tmp_path: Path) -> None:
    file_path = tmp_path / "NOTES.md"
    file_path.write_text("old\n", encoding="utf-8")
    manager = EditorManager()
    tab = manager.open_file(str(file_path)).tab
    tab.mark_saved(last_known_mtime=1.0)
    surface = _LazySurface()
    host = SimpleNamespace(
        editor_widget_for_path=lambda _path: None,
        surface_for_path=lambda _path: surface,
        advance_buffer_revision=lambda _path: 1,
        apply_detected_indentation=lambda *_args: pytest.fail("indent requires an editor widget"),
        tab_index_for_path=lambda _path: 0,
        refresh_tab_presentation=lambda _path: None,
        has_editor_tabs_widget=lambda: True,
    )
    workflow = EditorSyncWorkflow(editor_manager=manager, host=host)  # type: ignore[arg-type]

    applied = workflow.apply_disk_content(
        tab.file_path,
        "from disk\n",
        source=EditorDiskSyncSource.EXTERNAL_RELOAD,
        last_known_mtime=2.0,
    )

    assert applied is True
    assert surface.restored == [("from disk\n", "external_reload")]
    assert tab.current_content == "from disk\n"
    assert tab.last_known_mtime == 2.0
