"""Unit tests for markdown tab registry rename and unwrap behavior."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.editors.code_editor_widget import CodeEditorWidget  # noqa: E402
from app.editors.markdown_editor_pane import MarkdownEditorPane  # noqa: E402
from app.editors.markdown_rendering import is_markdown_path  # noqa: E402
from app.shell.markdown_tab_registry import MarkdownTabRegistry  # noqa: E402

pytestmark = pytest.mark.unit


def test_rekey_from_markdown_to_non_markdown_unwraps_pane(qapp) -> None:  # type: ignore[no-untyped-def]
    panes_by_path: dict[str, MarkdownEditorPane] = {}
    registry = MarkdownTabRegistry(panes_by_path)
    editor = CodeEditorWidget()
    pane = MagicMock(spec=MarkdownEditorPane)
    pane.source_editor.return_value = editor
    readme_path = "/tmp/README.md"
    registry.register(readme_path, pane)

    unwrapped: list[tuple[MarkdownEditorPane, CodeEditorWidget]] = []

    def on_unwrap(markdown_pane: MarkdownEditorPane, source_editor: CodeEditorWidget) -> None:
        unwrapped.append((markdown_pane, source_editor))

    registry.rekey_for_widget(
        editor,
        "/tmp/README.txt",
        is_markdown_path=is_markdown_path,
        on_unwrap=on_unwrap,
    )

    assert panes_by_path == {}
    assert unwrapped == [(pane, editor)]
    pane.deleteLater.assert_called_once()


def test_rekey_stays_registered_when_still_markdown(qapp) -> None:  # type: ignore[no-untyped-def]
    panes_by_path: dict[str, MarkdownEditorPane] = {}
    registry = MarkdownTabRegistry(panes_by_path)
    editor = CodeEditorWidget()
    pane = MagicMock(spec=MarkdownEditorPane)
    pane.source_editor.return_value = editor
    registry.register("/tmp/notes.md", pane)

    registry.rekey_for_widget(
        editor,
        "/tmp/NOTES.md",
        is_markdown_path=is_markdown_path,
    )

    assert list(panes_by_path.keys()) == ["/tmp/NOTES.md"]
    pane.set_file_path.assert_called_once_with("/tmp/NOTES.md")
