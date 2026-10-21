"""Opening a sourced preview must not take focus from the project tree."""

from __future__ import annotations

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.editors.editor_manager import OpenedTabResult  # noqa: E402
from app.editors.editor_tab import EditorTabState  # noqa: E402
from app.qt.QtWidgets import QTabWidget, QWidget  # noqa: E402
from app.shell.editor_tab_factory import EditorTabFactory  # noqa: E402
from app.shell.tab_content_providers import TabContentProviderRegistry, TabMatchContext  # noqa: E402

pytestmark = pytest.mark.unit


class _Surface:
    def __init__(self, parent: QWidget) -> None:
        self._widget = QWidget(parent)
        self.focused = 0

    def widget(self) -> QWidget:
        return self._widget

    def content_source(self) -> None:
        return None

    def source_editor(self) -> None:
        return None

    def focus_primary(self) -> None:
        self.focused += 1


class _Provider:
    provider_id = "markdown"
    priority = 0

    def __init__(self) -> None:
        self.surface: _Surface | None = None

    def matches(self, file_path: str, context: TabMatchContext) -> bool:
        del context
        return file_path.endswith(".md")

    def create_surface(self, request: object) -> _Surface:
        parent = getattr(request, "parent")
        self.surface = _Surface(parent)
        return self.surface


def test_opening_a_markdown_surface_does_not_focus_it(qapp: object) -> None:
    del qapp
    tabs = QTabWidget()
    registry = TabContentProviderRegistry()
    provider = _Provider()
    registry.register(provider)  # type: ignore[arg-type]
    presented: list[str] = []
    window = type("Window", (), {})()
    window._editor_tabs_widget = tabs  # type: ignore[attr-defined]
    window._tab_content_registry = registry  # type: ignore[attr-defined]
    window._loaded_project = None  # type: ignore[attr-defined]
    window._shell_theme_workflow = type("Theme", (), {"resolve_theme_tokens": staticmethod(lambda: object())})()  # type: ignore[attr-defined]
    window._editor_tab_workflow = type(  # type: ignore[attr-defined]
        "Tabs",
        (),
        {
            "refresh_tab_presentation": staticmethod(lambda path: presented.append(path)),
            "handle_editor_tab_changed": staticmethod(lambda _index: None),
            "update_editor_status_for_path": staticmethod(lambda _path: None),
        },
    )()
    window._refresh_save_action_states = lambda: None  # type: ignore[attr-defined]
    tab = EditorTabState(
        file_path="/tmp/project/README.md",
        display_name="README.md",
        original_content="# hi\n",
        current_content="# hi\n",
        is_preview=True,
    )
    opened = OpenedTabResult(tab=tab, was_already_open=False)

    opened_ok = EditorTabFactory(window)._materialize_opened_editor_tab(  # type: ignore[arg-type]
        opened,
        started_at=None,
        restore_draft=False,
    )

    assert opened_ok is True
    assert provider.surface is not None
    assert provider.surface.focused == 0
    assert presented == [tab.file_path]
