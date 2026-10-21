"""Rename keeps a markdown surface, and leaves it when the new path is plain text."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.shell.project_tree_ui_workflow import ProjectTreeUiWorkflow  # noqa: E402
from app.shell.tab_content_providers import TabContentProviderRegistry, TabMatchContext  # noqa: E402

pytestmark = pytest.mark.unit


class _Widget:
    def __init__(self) -> None:
        self.language_path: str | None = None

    def set_language_for_path(self, path: str) -> None:
        self.language_path = path


class _Surface:
    def __init__(self, editor: _Widget) -> None:
        self._editor = editor
        self.changed: list[str] = []
        self.released = 0

    def source_editor(self) -> _Widget:
        return self._editor

    def file_path_changed(self, new_path: str) -> None:
        self.changed.append(new_path)

    def release(self) -> None:
        self.released += 1


class _Provider:
    provider_id = "markdown"
    priority = 0

    def matches(self, file_path: str, context: TabMatchContext) -> bool:
        del context
        return file_path.endswith(".md")


class _Host:
    def __init__(self, registry: TabContentProviderRegistry) -> None:
        self._registry = registry
        self.replaced: list[tuple[str, object]] = []

    def tab_content_registry(self) -> TabContentProviderRegistry:
        return self._registry

    def loaded_project(self) -> None:
        return None

    def editor_tabs_coordinator(self) -> SimpleNamespace:
        return SimpleNamespace(
            replace_tab_content_widget=lambda path, widget: self.replaced.append((path, widget))
        )


def test_rename_to_markdown_rekeys_the_surface(tmp_path: Path) -> None:
    editor = _Widget()
    surface = _Surface(editor)
    old_path = str((tmp_path / "README.md").resolve())
    new_path = str((tmp_path / "NOTES.md").resolve())
    registry = TabContentProviderRegistry()
    registry.register(_Provider())
    registry.bind(old_path, surface)  # type: ignore[arg-type]
    host = _Host(registry)
    workflow = ProjectTreeUiWorkflow(host)  # type: ignore[arg-type]

    workflow.rekey_tab_content(old_path, new_path)

    assert surface.changed == [new_path]
    assert registry.surface_for_path(new_path) is surface
    assert surface.released == 0
    assert host.replaced == []


def test_rename_to_text_reparents_the_source_editor_and_releases_the_surface(tmp_path: Path) -> None:
    editor = _Widget()
    surface = _Surface(editor)
    old_path = str((tmp_path / "README.md").resolve())
    new_path = str((tmp_path / "README.txt").resolve())
    registry = TabContentProviderRegistry()
    registry.bind(old_path, surface)  # type: ignore[arg-type]
    host = _Host(registry)
    workflow = ProjectTreeUiWorkflow(host)  # type: ignore[arg-type]

    workflow.rekey_tab_content(old_path, new_path)

    assert host.replaced == [(new_path, editor)]
    assert registry.surface_for_path(old_path) is None
    assert surface.released == 1
    assert surface.changed == []
