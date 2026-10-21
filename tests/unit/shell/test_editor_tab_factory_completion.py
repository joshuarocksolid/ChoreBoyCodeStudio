"""The editor tab factory applies the completion mode, not the old flags."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.shell.editor_tab_factory import EditorTabFactory

pytestmark = pytest.mark.unit


class _RecordingEditor:
    def __init__(self) -> None:
        self.mode = ""
        self.min_chars = 0

    def setObjectName(self, _name: str) -> None:
        return None

    def set_editor_preferences(self, **_kwargs: object) -> None:
        return None

    def set_completion_preferences(self, *, mode: str, min_chars: int) -> None:
        self.mode = mode
        self.min_chars = min_chars

    def apply_theme(self, _tokens: object) -> None:
        return None


def _window(mode: str) -> SimpleNamespace:
    return SimpleNamespace(
        _editor_tab_width=4,
        _editor_font_family="monospace",
        _editor_indent_style="spaces",
        _editor_indent_size=4,
        _editor_hover_tooltip_enabled=True,
        _editor_auto_reindent_flat_python_paste=False,
        _completion_min_chars=3,
        _shell_preferences_runtime=SimpleNamespace(completion_mode=lambda: mode),
        _editor_tab_workflow=SimpleNamespace(
            effective_font_size=lambda: 12,
            apply_runtime_intelligence_preferences_to_editor=lambda _widget: None,
        ),
        _shell_theme_workflow=SimpleNamespace(resolve_theme_tokens=lambda: None),
    )


@pytest.mark.parametrize("mode", ["off", "manual", "typing"])
def test_tab_factory_honors_each_completion_mode(mode: str) -> None:
    editor = _RecordingEditor()
    EditorTabFactory(_window(mode))._configure_editor_widget(editor)  # type: ignore[arg-type]
    assert editor.mode == mode
    assert editor.min_chars == 3
