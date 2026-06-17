"""Token-driven stylesheets for the Markdown preview widget."""

from __future__ import annotations

from app.shell.theme_tokens import ShellThemeTokens


def _heading_color(tokens: ShellThemeTokens) -> str:
    return tokens.syntax_markdown_heading or tokens.text_primary


def _code_color(tokens: ShellThemeTokens) -> str:
    return tokens.syntax_markdown_code or tokens.text_primary


def _emphasis_color(tokens: ShellThemeTokens) -> str:
    return tokens.syntax_markdown_emphasis or tokens.text_primary


def _strong_color(tokens: ShellThemeTokens) -> str:
    return tokens.syntax_markdown_strong or tokens.text_primary


def build_preview_widget_stylesheet(tokens: ShellThemeTokens) -> str:
    """Return widget-level QSS for the Markdown preview browser."""
    scrollbar_handle = tokens.border
    scrollbar_hover = tokens.text_muted
    return f"""
QTextBrowser#shell\\.markdownPreview\\.browser {{
    background: {tokens.editor_bg};
    color: {tokens.text_primary};
    border: none;
    padding: 20px 28px;
    selection-background-color: {tokens.tree_selected_bg};
}}
QTextBrowser#shell\\.markdownPreview\\.browser QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 0;
}}
QTextBrowser#shell\\.markdownPreview\\.browser QScrollBar::handle:vertical {{
    background: {scrollbar_handle};
    min-height: 24px;
    border-radius: 4px;
}}
QTextBrowser#shell\\.markdownPreview\\.browser QScrollBar::handle:vertical:hover {{
    background: {scrollbar_hover};
}}
QTextBrowser#shell\\.markdownPreview\\.browser QScrollBar::add-line:vertical,
QTextBrowser#shell\\.markdownPreview\\.browser QScrollBar::sub-line:vertical {{
    height: 0;
}}
QTextBrowser#shell\\.markdownPreview\\.browser QScrollBar::add-page:vertical,
QTextBrowser#shell\\.markdownPreview\\.browser QScrollBar::sub-page:vertical {{
    background: transparent;
}}
"""


def build_preview_document_stylesheet(tokens: ShellThemeTokens) -> str:
    """Return document-level CSS applied via QTextDocument.setDefaultStyleSheet()."""
    heading = _heading_color(tokens)
    code_color = _code_color(tokens)
    emphasis = _emphasis_color(tokens)
    strong = _strong_color(tokens)
    return f"""
body {{
    color: {tokens.text_primary};
    background-color: {tokens.editor_bg};
    font-family: sans-serif;
    font-size: 14px;
    line-height: 1.6;
    margin: 0 0 24px 0;
    max-width: 860px;
}}
h1, h2, h3, h4, h5, h6 {{
    color: {heading};
    font-weight: 700;
}}
h1 {{
    font-size: 28px;
    margin: 0 0 16px 0;
    border-bottom: 1px solid {tokens.border};
    padding-bottom: 8px;
}}
h2 {{
    font-size: 22px;
    margin: 24px 0 12px 0;
    border-bottom: 1px solid {tokens.border};
    padding-bottom: 6px;
}}
h3 {{
    font-size: 18px;
    margin: 20px 0 10px 0;
}}
h4 {{
    font-size: 16px;
    margin: 16px 0 8px 0;
}}
h5 {{
    font-size: 14px;
    margin: 14px 0 6px 0;
}}
h6 {{
    font-size: 13px;
    margin: 12px 0 6px 0;
    color: {tokens.text_muted};
}}
p {{
    margin: 0 0 12px 0;
}}
em {{
    color: {emphasis};
    font-style: italic;
}}
strong, b {{
    color: {strong};
    font-weight: 700;
}}
a {{
    color: {tokens.accent};
    text-decoration: none;
}}
hr {{
    border: none;
    border-top: 1px solid {tokens.border};
    margin: 24px 0;
}}
ul, ol {{
    margin: 0 0 12px 0;
    padding-left: 24px;
}}
li {{
    margin: 4px 0;
}}
li ul, li ol {{
    margin: 4px 0 4px 0;
}}
code {{
    background-color: {tokens.badge_bg};
    color: {code_color};
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 12px;
    font-family: monospace;
}}
pre {{
    background-color: {tokens.badge_bg};
    color: {code_color};
    border: 1px solid {tokens.border};
    border-radius: 6px;
    padding: 12px 14px;
    margin: 12px 0;
    font-family: monospace;
    white-space: pre-wrap;
}}
pre code {{
    background-color: transparent;
    color: inherit;
    padding: 0;
    border-radius: 0;
    font-size: inherit;
}}
blockquote {{
    color: {tokens.text_muted};
    border-left: 3px solid {tokens.border};
    margin: 12px 0;
    padding: 4px 0 4px 16px;
}}
table {{
    border-collapse: collapse;
    margin: 12px 0;
    width: 100%;
}}
th {{
    background-color: {tokens.row_alt_bg};
    font-weight: 700;
    text-align: left;
}}
th, td {{
    padding: 8px 12px;
    border-bottom: 1px solid {tokens.border};
}}
img {{
    max-width: 100%;
    height: auto;
    margin: 8px 0;
    border: 1px solid {tokens.border};
    border-radius: 4px;
}}
"""


def build_preview_paused_html(
    tokens: ShellThemeTokens,
    *,
    character_count: int,
    threshold: int,
) -> str:
    """Return themed HTML for the large-file preview paused message."""
    heading = _heading_color(tokens)
    return f"""
<div style="font-family:sans-serif;color:{tokens.text_primary};
            background:{tokens.editor_bg};padding:20px;max-width:860px;">
  <h2 style="color:{heading};font-size:22px;margin:0 0 12px 0;">Preview paused</h2>
  <p style="margin:0 0 12px 0;">This file is large, so live preview is paused to keep the editor responsive.</p>
  <p style="margin:0 0 12px 0;">
    <b>Characters:</b> {character_count:,}<br/>
    <b>Live preview limit:</b> {threshold:,}
  </p>
  <p style="margin:0;">Use <b>Refresh</b> to render it manually.</p>
</div>
"""
