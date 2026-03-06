"""Unit tests for the help dialog markdown converter and widget."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.shell.theme_tokens import tokens_from_palette  # noqa: E402
from app.ui.help.help_dialog import HelpDialog, markdown_to_html  # noqa: E402

pytestmark = pytest.mark.unit


def _dark_tokens():
    palette = MagicMock()
    window_color = MagicMock()
    window_color.lightness.return_value = 50
    palette.color.return_value = window_color
    return tokens_from_palette(palette, force_mode="dark")


def _light_tokens():
    palette = MagicMock()
    window_color = MagicMock()
    window_color.lightness.return_value = 200
    palette.color.return_value = window_color
    return tokens_from_palette(palette, force_mode="light")


class TestMarkdownToHtml:
    """Tests for the lightweight markdown-to-HTML converter."""

    def test_h1_heading(self) -> None:
        html = markdown_to_html("# Hello World", _dark_tokens())
        assert "<h1" in html
        assert "Hello World" in html

    def test_h2_heading(self) -> None:
        html = markdown_to_html("## Section", _light_tokens())
        assert "<h2" in html
        assert "Section" in html

    def test_h3_heading(self) -> None:
        html = markdown_to_html("### Sub", _dark_tokens())
        assert "<h3" in html
        assert "Sub" in html

    def test_inline_code(self) -> None:
        html = markdown_to_html("Use `Ctrl+S` to save.", _dark_tokens())
        assert "<code" in html
        assert "Ctrl+S" in html

    def test_bold(self) -> None:
        html = markdown_to_html("Press **F5** now.", _light_tokens())
        assert "<b>F5</b>" in html

    def test_bullet_list(self) -> None:
        md = "- First\n- Second\n- Third"
        html = markdown_to_html(md, _dark_tokens())
        assert "<ul" in html
        assert html.count("<li>") == 3
        assert "First" in html
        assert "Third" in html

    def test_numbered_list(self) -> None:
        md = "1. Open file.\n2. Edit code.\n3. Save."
        html = markdown_to_html(md, _light_tokens())
        assert "<ol" in html
        assert html.count("<li>") == 3
        assert "Open file." in html

    def test_numbered_list_with_continuation(self) -> None:
        md = "1. Check status.\n   Look at the bar.\n   It should be green."
        html = markdown_to_html(md, _dark_tokens())
        assert "<ol" in html
        assert "Check status." in html
        assert "Look at the bar." in html
        assert "It should be green." in html

    def test_numbered_list_with_sub_bullets(self) -> None:
        md = "2. Create a project.\n   - New: `File > New`\n   - Open: `File > Open`"
        html = markdown_to_html(md, _light_tokens())
        assert "Create a project." in html
        assert "&bull;" in html
        assert "File &gt; New" in html

    def test_paragraph(self) -> None:
        html = markdown_to_html("Hello world.", _dark_tokens())
        assert "<p" in html
        assert "Hello world." in html

    def test_empty_input(self) -> None:
        html = markdown_to_html("", _dark_tokens())
        assert html.strip() == ""

    def test_mixed_content(self) -> None:
        md = "# Title\n\nSome text.\n\n- bullet one\n- bullet two\n\n1. first\n2. second"
        html = markdown_to_html(md, _light_tokens())
        assert "<h1" in html
        assert "<p" in html
        assert "<ul" in html
        assert "<ol" in html

    def test_html_entities_escaped(self) -> None:
        html = markdown_to_html("Use <script> & stuff.", _dark_tokens())
        assert "&lt;script&gt;" in html
        assert "&amp;" in html

    def test_bullet_with_continuation(self) -> None:
        md = "- `Utility Script`\n  Best for quick automation."
        html = markdown_to_html(md, _light_tokens())
        assert "<ul" in html
        assert "Utility Script" in html
        assert "Best for quick automation." in html

    def test_lists_close_between_types(self) -> None:
        md = "- bullet\n\n1. numbered"
        html = markdown_to_html(md, _dark_tokens())
        assert "</ul>" in html
        assert "<ol" in html


class TestHelpDialogSmoke:
    """Smoke test that HelpDialog can be instantiated without crashing."""

    def test_instantiate_with_dark_tokens(self, qapp) -> None:  # type: ignore[no-untyped-def]
        tokens = _dark_tokens()
        dlg = HelpDialog("Test", "# Hello\n\nWorld.", tokens)
        assert dlg.windowTitle() == "Test"
        assert dlg.objectName() == "shell.helpDialog"

    def test_instantiate_with_light_tokens(self, qapp) -> None:  # type: ignore[no-untyped-def]
        tokens = _light_tokens()
        dlg = HelpDialog("Shortcuts", "- **F5**: Run", tokens)
        assert dlg.windowTitle() == "Shortcuts"


@pytest.fixture()
def qapp():
    """Provide a QApplication instance for widget smoke tests."""
    from PySide2.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app
