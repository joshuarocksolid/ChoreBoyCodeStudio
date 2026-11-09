"""Replacing a preview must release a lazy surface that never built an editor."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.editors.editor_manager import EditorManager  # noqa: E402
from app.qt.QtWidgets import QTabWidget, QWidget  # noqa: E402
from app.shell.editor_tab_factory import EditorTabFactory  # noqa: E402
from app.shell.editor_tab_lifecycle_workflow import EditorTabLifecycleWorkflow  # noqa: E402
from app.shell.editor_tab_workflow_mixins import EditorTabLifecycleDelegates  # noqa: E402
from app.shell.editor_tabs_coordinator import EditorTabsCoordinator  # noqa: E402
from app.shell.editor_workspace_controller import EditorWorkspaceController  # noqa: E402
from app.shell.tab_content_providers import TabContentProviderRegistry, TabMatchContext  # noqa: E402

pytestmark = pytest.mark.unit


class _LazySurface(QWidget):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.released = 0

    def source_editor(self) -> None:
        return None

    def content_source(self) -> None:
        return None

    def widget(self) -> QWidget:
        return self

    def release(self) -> None:
        self.released += 1


class _LazyProvider:
    provider_id = "lazy-preview"
    priority = 0

    def __init__(self) -> None:
        self.surfaces: list[_LazySurface] = []

    def matches(self, file_path: str, context: TabMatchContext) -> bool:
        del context
        return file_path.endswith(".ui")

    def create_surface(self, request: object) -> _LazySurface:
        parent = getattr(request, "parent")
        surface = _LazySurface(parent)
        self.surfaces.append(surface)
        return surface


class _Host:
    def __init__(
        self,
        tabs: QTabWidget,
        registry: TabContentProviderRegistry,
        workspace: EditorWorkspaceController,
    ) -> None:
        self._tabs = tabs
        self._registry = registry
        self._workspace = workspace
        self._indents: dict[str, object] = {}

    def editor_tabs_widget(self) -> QTabWidget:
        return self._tabs

    def workspace_controller(self) -> EditorWorkspaceController:
        return self._workspace

    def tab_content_registry(self) -> TabContentProviderRegistry:
        return self._registry

    def indent_source_by_path(self) -> dict[str, object]:
        return self._indents

    def status_controller(self) -> None:
        return None

    def local_history_forget_source(self, file_path: str) -> None:
        del file_path

    def debug_execution_editor(self) -> None:
        return None

    def clear_debug_execution_indicator(self) -> None:
        return None

    def refresh_save_action_states(self) -> None:
        return None

    def refresh_run_action_states(self) -> None:
        return None


class _Workflow(EditorTabLifecycleDelegates):
    def __init__(
        self,
        lifecycle: EditorTabLifecycleWorkflow,
        coordinator: EditorTabsCoordinator,
        manager: EditorManager,
    ) -> None:
        self._lifecycle_workflow = lifecycle
        self._editor_tabs_coordinator = coordinator
        self._manager = manager

    def update_editor_status_for_path(self, file_path: str) -> None:
        del file_path

    def apply_detected_indentation_for_widget(self, *_args: object) -> None:
        return None

    def handle_editor_tab_changed(self, tab_index: int) -> None:
        del tab_index

    def path_for_buffer_id(self, buffer_id: str) -> str | None:
        tab = self._manager.get_tab_by_id(buffer_id)
        return None if tab is None else tab.file_path


def test_second_preview_releases_the_lazy_surface_so_the_first_path_can_reopen(
    tmp_path: Path,
    qapp: object,
) -> None:
    del qapp
    first = tmp_path / "a.ui"
    second = tmp_path / "b.ui"
    first.write_text("<ui a/>\n", encoding="utf-8")
    second.write_text("<ui b/>\n", encoding="utf-8")
    first_path = str(first.resolve())
    second_path = str(second.resolve())

    manager = EditorManager()
    tabs = QTabWidget()
    registry = TabContentProviderRegistry()
    provider = _LazyProvider()
    registry.register(provider)  # type: ignore[arg-type]
    workspace = EditorWorkspaceController(lambda: manager)
    window = type("Window", (), {})()
    window._editor_manager = manager  # type: ignore[attr-defined]
    window._editor_tabs_widget = tabs  # type: ignore[attr-defined]
    window._editor_enable_preview = True  # type: ignore[attr-defined]
    window._tab_content_registry = registry  # type: ignore[attr-defined]
    window._loaded_project = None  # type: ignore[attr-defined]
    window._shell_theme_workflow = type("Theme", (), {"resolve_theme_tokens": staticmethod(lambda: None)})()  # type: ignore[attr-defined]
    window._external_file_change_workflow = type(  # type: ignore[attr-defined]
        "Conflicts",
        (),
        {
            "reload_from_disk": staticmethod(lambda _path: None),
            "compare_with_disk": staticmethod(lambda _path: None),
            "save_buffer_as": staticmethod(lambda _path: None),
        },
    )()
    window._refresh_save_action_states = lambda: None  # type: ignore[attr-defined]
    window._logger = type("Logger", (), {"info": staticmethod(lambda *_args, **_kwargs: None)})()  # type: ignore[attr-defined]
    coordinator = EditorTabsCoordinator(window)
    window._editor_tabs_coordinator = coordinator  # type: ignore[attr-defined]
    lifecycle = EditorTabLifecycleWorkflow(
        host=_Host(tabs, registry, workspace),  # type: ignore[arg-type]
        editor_manager=manager,
        editor_tabs_coordinator=coordinator,
        save_workflow=type("Save", (), {})(),
        debug_control_workflow=type("Debug", (), {})(),
        markdown_workflow=type("Markdown", (), {})(),
        tab_workflow=type("Tabs", (), {})(),
    )
    window._editor_tab_workflow = _Workflow(lifecycle, coordinator, manager)  # type: ignore[attr-defined]
    factory = EditorTabFactory(window)

    assert factory.open_file_in_editor(first_path, preview=True, restore_draft=False) is True
    assert factory.open_file_in_editor(second_path, preview=True, restore_draft=False) is True

    assert provider.surfaces[0].released == 1
    assert registry.surface_for_path(first_path) is None
    assert factory.open_file_in_editor(first_path, preview=True, restore_draft=False) is True
    assert registry.surface_for_path(first_path) is provider.surfaces[-1]
    assert registry.surface_for_path(second_path) is None
    assert provider.surfaces[1].released == 1
