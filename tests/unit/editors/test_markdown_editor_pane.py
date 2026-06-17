"""Qt smoke tests for the Markdown editor pane."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.editors.code_editor_widget import CodeEditorWidget  # noqa: E402
from app.editors.markdown_editor_pane import MarkdownEditorPane, MarkdownPreviewMode  # noqa: E402
from app.editors.markdown_preview_styles import build_preview_document_stylesheet  # noqa: E402
from app.shell.theme_tokens import tokens_from_palette  # noqa: E402

pytestmark = pytest.mark.unit


def _tokens(force_mode: str = "light"):
    palette = MagicMock()
    window_color = MagicMock()
    window_color.lightness.return_value = 50 if force_mode == "dark" else 200
    palette.color.return_value = window_color
    return tokens_from_palette(palette, force_mode=force_mode)


@pytest.mark.parametrize(
    "force_mode",
    ["light", "dark", "high_contrast_light", "high_contrast_dark"],
)
def test_markdown_editor_pane_accepts_all_theme_modes(qapp, tmp_path, force_mode: str) -> None:  # type: ignore[no-untyped-def]
    file_path = str(tmp_path / "README.md")
    editor = CodeEditorWidget()
    editor.setPlainText("# Hello")
    editor.apply_theme = MagicMock()
    pane = MarkdownEditorPane(editor, file_path)

    pane.apply_theme(_tokens(force_mode))

    stylesheet = build_preview_document_stylesheet(_tokens(force_mode))
    assert pane.preview_widget().document().defaultStyleSheet() == stylesheet
    assert not pane._source_button.icon().isNull()
    assert not pane._refresh_button.icon().isNull()


def test_markdown_editor_pane_keeps_source_editor_accessible(qapp, tmp_path) -> None:  # type: ignore[no-untyped-def]
    file_path = str(tmp_path / "README.md")
    editor = CodeEditorWidget()
    editor.setPlainText("# Hello")
    editor.apply_theme = MagicMock()

    pane = MarkdownEditorPane(editor, file_path)
    pane.apply_theme(_tokens())

    assert pane.source_editor() is editor
    assert pane.mode() == MarkdownPreviewMode.PREVIEW

    pane.set_mode(MarkdownPreviewMode.SOURCE)

    assert not pane.source_editor().isHidden()
    assert pane.preview_widget().isHidden()


def test_markdown_editor_pane_switches_to_split_mode(qapp, tmp_path) -> None:  # type: ignore[no-untyped-def]
    file_path = str(tmp_path / "README.md")
    editor = CodeEditorWidget()
    editor.setPlainText("# Hello")
    pane = MarkdownEditorPane(editor, file_path)

    pane.set_mode(MarkdownPreviewMode.SPLIT)

    assert pane.mode() == MarkdownPreviewMode.SPLIT
    assert not pane.source_editor().isHidden()
    assert not pane.preview_widget().isHidden()


def test_markdown_editor_pane_apply_theme_schedules_preview_render(qapp, tmp_path) -> None:  # type: ignore[no-untyped-def]
    file_path = str(tmp_path / "README.md")
    editor = CodeEditorWidget()
    editor.setPlainText("# Hello")
    editor.apply_theme = MagicMock()
    pane = MarkdownEditorPane(editor, file_path)
    pane.apply_theme(_tokens("light"))
    pane.render_preview()

    render_spy = MagicMock(wraps=pane._preview.render_markdown)
    pane._preview.render_markdown = render_spy
    pane.apply_theme(_tokens("dark"))

    assert render_spy.called


def test_markdown_editor_pane_large_file_pauses_live_preview(qapp, tmp_path) -> None:  # type: ignore[no-untyped-def]
    file_path = str(tmp_path / "README.md")
    editor = CodeEditorWidget()
    editor.setPlainText("# Big\n" + ("content\n" * 20))
    editor.apply_theme = MagicMock()
    pane = MarkdownEditorPane(editor, file_path, live_preview_threshold_chars=10)

    pane.apply_theme(_tokens("light"))
    pane.render_preview()

    assert "preview paused" in pane.preview_widget().toPlainText().lower()
    assert pane._status_label.text() == "Paused (large file)"
