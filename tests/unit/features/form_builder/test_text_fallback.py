"""Malformed forms and PySide2 runtimes open .ui as text with a notice."""

from __future__ import annotations

import importlib.util

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.editors.editor_manager import OpenedTabResult  # noqa: E402
from app.editors.editor_tab import EditorTabState  # noqa: E402
from app.features.form_builder.integration.provider import FormTabProvider  # noqa: E402
from app.qt.QtCore import Qt  # noqa: E402
from app.qt.QtWidgets import QLabel, QPushButton, QTabWidget, QWidget  # noqa: E402
from app.shell.editor_tab_factory import PYSIDE2_UI_HINT, EditorTabFactory  # noqa: E402
from app.shell.editor_tab_page import EditorTabPage  # noqa: E402
from app.shell.editor_tabs_coordinator import EditorTabsCoordinator  # noqa: E402
from app.shell.generated_file_workflow import GeneratedFileWorkflow  # noqa: E402
from app.shell.tab_content_providers import TabContentProviderRegistry  # noqa: E402
from app.shell.theme_tokens import tokens_from_palette  # noqa: E402

pytestmark = pytest.mark.unit


def _window(registry: TabContentProviderRegistry) -> tuple[QTabWidget, EditorTabFactory]:
    tabs = QTabWidget()
    window = type("Window", (), {})()
    window._editor_tabs_widget = tabs  # type: ignore[attr-defined]
    window._tab_content_registry = registry  # type: ignore[attr-defined]
    window._loaded_project = None  # type: ignore[attr-defined]
    window._logger = type("Logger", (), {"exception": staticmethod(lambda *_a, **_k: None)})()  # type: ignore[attr-defined]
    window._shell_theme_workflow = type("Theme", (), {"resolve_theme_tokens": staticmethod(lambda: None)})()  # type: ignore[attr-defined]
    window._editor_tab_workflow = type(  # type: ignore[attr-defined]
        "Tabs",
        (),
        {
            "refresh_tab_presentation": staticmethod(lambda _path: None),
            "handle_editor_tab_changed": staticmethod(lambda _index: None),
            "update_editor_status_for_path": staticmethod(lambda _path: None),
            "apply_detected_indentation_for_widget": staticmethod(lambda *_args: None),
            "generated_files": GeneratedFileWorkflow(
                tab_for_path=lambda _path: None,
                refresh_tab_presentation=lambda _path: None,
            ),
        },
    )()
    window._external_file_change_workflow = object()  # type: ignore[attr-defined]
    window._editor_tabs_coordinator = EditorTabsCoordinator(window)  # type: ignore[attr-defined]
    window._refresh_save_action_states = lambda: None  # type: ignore[attr-defined]
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
    return tabs, factory


def _open(factory: EditorTabFactory, path: str, text: str) -> EditorTabPage:
    tab = EditorTabState(
        file_path=path,
        display_name=path.rsplit("/", 1)[-1],
        original_content=text,
        current_content=text,
        is_preview=False,
    )
    opened = factory._materialize_opened_editor_tab(
        OpenedTabResult(tab=tab, was_already_open=False),
        started_at=None,
        restore_draft=False,
    )
    assert opened is True
    page = factory._window._editor_tabs_widget.widget(factory._window._editor_tabs_widget.count() - 1)
    assert isinstance(page, EditorTabPage)
    return page


def test_malformed_ui_opens_as_text_with_a_notice(qapp) -> None:  # type: ignore[no-untyped-def]
    del qapp
    registry = TabContentProviderRegistry()
    registry.register(FormTabProvider())
    _tabs, factory = _window(registry)

    page = _open(factory, "/tmp/project/broken.ui", "<ui>\n")

    labels = [label.text() for label in page.content().findChildren(QLabel)]
    assert labels
    assert "form builder" in labels[0]
    assert "line" in labels[0]
    assert registry.surface_for_path("/tmp/project/broken.ui") is None
    assert callable(page.content().source_editor)


def test_pyside2_ui_hint_shows_once_per_file(qapp, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    del qapp
    if importlib.util.find_spec("PySide2") is None:
        pytest.skip("PySide2 is not installed")
    monkeypatch.setenv("CBCS_QT_API", "pyside2")
    _tabs, factory = _window(TabContentProviderRegistry())
    path = "/tmp/project/invoice.ui"

    first = _open(factory, path, "<ui/>\n")
    hint = first.content().findChild(QLabel, "shell.editorTabs.uiTextHint")
    assert hint is not None
    assert hint.text() == PYSIDE2_UI_HINT
    assert callable(first.content().source_editor)

    hint.hide()
    second = _open(factory, path, "<ui/>\n")
    assert second.content().findChild(QLabel, "shell.editorTabs.uiTextHint") is None


def test_pyside2_hint_follows_theme_and_dismisses(qapp, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    if importlib.util.find_spec("PySide2") is None:
        pytest.skip("PySide2 is not installed")
    monkeypatch.setenv("CBCS_QT_API", "pyside2")
    _tabs, factory = _window(TabContentProviderRegistry())
    page = _open(factory, "/tmp/project/theme.ui", "<ui/>\n")
    hint = page.content()
    notice = hint.findChild(QLabel, "shell.editorTabs.uiTextHint")
    dismiss = hint.findChild(QPushButton, "shell.editorTabs.uiTextHintDismiss")
    assert notice is not None
    assert dismiss is not None
    assert dismiss.focusPolicy() != Qt.NoFocus
    previous = ""
    for mode in ("light", "dark", "high_contrast_light", "high_contrast_dark"):
        tokens = tokens_from_palette(qapp.palette(), force_mode=mode)
        hint.apply_theme(tokens)  # type: ignore[attr-defined]
        # The notice box carries the colours; the text sits inside it.
        sheet = notice.parentWidget().styleSheet()
        assert tokens.panel_bg in sheet
        assert tokens.text_primary in sheet
        assert tokens.text_primary in dismiss.styleSheet()
        assert sheet != previous
        previous = sheet
    dismiss.click()
    assert not notice.isVisibleTo(hint)
    assert not dismiss.isVisibleTo(hint)
