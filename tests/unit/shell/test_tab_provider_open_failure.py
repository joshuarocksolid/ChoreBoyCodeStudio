"""A provider that raises while opening a tab falls back to a text editor."""

from __future__ import annotations

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.editors.editor_manager import OpenedTabResult  # noqa: E402
from app.editors.editor_tab import EditorTabState  # noqa: E402
from app.qt.QtWidgets import QLabel, QTabWidget, QWidget  # noqa: E402
from app.shell.editor_tab_factory import EditorTabFactory  # noqa: E402
from app.shell.editor_tab_page import EditorTabPage  # noqa: E402
from app.shell.editor_tabs_coordinator import EditorTabsCoordinator  # noqa: E402
from app.shell.tab_content_providers import (  # noqa: E402
    ProviderDeclined,
    TabContentProviderRegistry,
    TabMatchContext,
)

pytestmark = pytest.mark.unit

_NOTICE = "Couldn't open this view. Opened as text."


class _Provider:
    provider_id = "form"
    priority = 0

    def __init__(self, error: BaseException) -> None:
        self._error = error

    def matches(self, file_path: str, context: TabMatchContext) -> bool:
        del file_path, context
        return True

    def create_surface(self, request: object) -> object:
        del request
        raise self._error


def _open(provider: _Provider, qapp: object) -> tuple[QTabWidget, TabContentProviderRegistry, list[str]]:
    del qapp
    tabs = QTabWidget()
    registry = TabContentProviderRegistry()
    registry.register(provider)  # type: ignore[arg-type]
    logged: list[str] = []

    class _Logger:
        def exception(self, message: str, *args: object) -> None:
            logged.append(message % args if args else message)

    window = type("Window", (), {})()
    window._editor_tabs_widget = tabs  # type: ignore[attr-defined]
    window._tab_content_registry = registry  # type: ignore[attr-defined]
    window._loaded_project = None  # type: ignore[attr-defined]
    window._logger = _Logger()  # type: ignore[attr-defined]
    window._shell_theme_workflow = type("Theme", (), {"resolve_theme_tokens": staticmethod(lambda: None)})()  # type: ignore[attr-defined]
    window._editor_tab_workflow = type(  # type: ignore[attr-defined]
        "Tabs",
        (),
        {
            "refresh_tab_presentation": staticmethod(lambda _path: None),
            "handle_editor_tab_changed": staticmethod(lambda _index: None),
            "update_editor_status_for_path": staticmethod(lambda _path: None),
            "apply_detected_indentation_for_widget": staticmethod(lambda *_args: None),
        },
    )()
    window._external_file_change_workflow = object()  # type: ignore[attr-defined]
    window._editor_tabs_coordinator = EditorTabsCoordinator(window)  # type: ignore[attr-defined]
    window._refresh_save_action_states = lambda: None  # type: ignore[attr-defined]
    tab = EditorTabState(
        file_path="/tmp/project/invoice.ui",
        display_name="invoice.ui",
        original_content="<ui/>\n",
        current_content="<ui/>\n",
        is_preview=False,
    )
    factory = EditorTabFactory(window)

    class _Editor(QWidget):
        def toPlainText(self) -> str:  # noqa: N802
            return "<ui/>\n"

    def _fake_editor(
        opened_result: OpenedTabResult,
        *,
        parent: QWidget,
        theme_tokens: object,
    ) -> QWidget:
        del opened_result, theme_tokens
        editor = _Editor(parent)
        editor.setObjectName("shell.editorTabs.textEditor")
        return editor

    factory._build_bound_source_editor = _fake_editor  # type: ignore[method-assign]
    opened = factory._materialize_opened_editor_tab(
        OpenedTabResult(tab=tab, was_already_open=False),
        started_at=None,
        restore_draft=False,
    )
    assert opened is True
    return tabs, registry, logged


def _notice_text(tabs: QTabWidget) -> str:
    page = tabs.widget(0)
    assert isinstance(page, EditorTabPage)
    labels = page.content().findChildren(QLabel)
    assert len(labels) == 1
    return labels[0].text()


def test_provider_exception_opens_text_with_notice(qapp: object) -> None:
    tabs, registry, logged = _open(_Provider(RuntimeError("canvas failed")), qapp)

    assert _notice_text(tabs) == _NOTICE
    assert registry.surface_for_path("/tmp/project/invoice.ui") is None
    assert logged == ["Tab provider form failed for /tmp/project/invoice.ui"]


def test_provider_declined_keeps_its_own_reason(qapp: object) -> None:
    tabs, registry, logged = _open(_Provider(ProviderDeclined("Not a form.")), qapp)

    assert _notice_text(tabs) == "Not a form."
    assert registry.surface_for_path("/tmp/project/invoice.ui") is None
    assert logged == []
