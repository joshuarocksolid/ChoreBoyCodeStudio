"""Themed help viewer dialog with lightweight markdown rendering."""

from __future__ import annotations

import re
from pathlib import Path

from PySide2.QtCore import Qt
from PySide2.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from app.shell.theme_tokens import ShellThemeTokens


def markdown_to_html(text: str, tokens: ShellThemeTokens) -> str:
    """Convert a limited markdown subset to themed HTML.

    Covers: ``#``/``##`` headings, numbered lists, bullet lists, indented
    continuation lines, inline ``backtick`` code, ``**bold**``, and paragraphs.
    """
    lines = text.split("\n")
    html_parts: list[str] = []
    in_ul = False
    in_ol = False

    def _close_lists() -> None:
        nonlocal in_ul, in_ol
        if in_ul:
            html_parts.append("</ul>")
            in_ul = False
        if in_ol:
            html_parts.append("</ol>")
            in_ol = False

    def _inline(t: str) -> str:
        t = t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        t = re.sub(
            r"`([^`]+)`",
            rf'<code style="background:{tokens.badge_bg};padding:1px 5px;'
            rf'border-radius:3px;font-size:12px;">\1</code>',
            t,
        )
        t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
        return t

    i = 0
    while i < len(lines):
        line = lines[i]

        if not line.strip():
            _close_lists()
            i += 1
            continue

        # Headings
        heading_match = re.match(r"^(#{1,3})\s+(.*)", line)
        if heading_match:
            _close_lists()
            level = len(heading_match.group(1))
            heading_text = _inline(heading_match.group(2))
            sizes = {1: "20px", 2: "16px", 3: "14px"}
            margins = {1: "18px 0 10px 0", 2: "16px 0 8px 0", 3: "12px 0 6px 0"}
            border = ""
            if level == 1:
                border = f"border-bottom:1px solid {tokens.border};padding-bottom:6px;"
            html_parts.append(
                f'<h{level} style="font-size:{sizes[level]};'
                f"margin:{margins[level]};{border}\">"
                f"{heading_text}</h{level}>"
            )
            i += 1
            continue

        # Numbered list item (e.g. "1. Text" or "10. Text")
        ol_match = re.match(r"^(\d+)\.\s+(.*)", line)
        if ol_match:
            if in_ul:
                html_parts.append("</ul>")
                in_ul = False
            if not in_ol:
                html_parts.append(
                    '<ol style="margin:4px 0 4px 24px;padding:0;'
                    'line-height:1.7;">'
                )
                in_ol = True
            body = _inline(ol_match.group(2))
            # Collect continuation / sub-item lines
            i += 1
            while i < len(lines) and lines[i].startswith("   ") and lines[i].strip():
                sub = lines[i].strip()
                sub_bullet = re.match(r"^-\s+(.*)", sub)
                if sub_bullet:
                    body += f"<br/>&nbsp;&nbsp;&bull; {_inline(sub_bullet.group(1))}"
                else:
                    body += f"<br/>&nbsp;&nbsp;{_inline(sub)}"
                i += 1
            html_parts.append(f"<li>{body}</li>")
            continue

        # Bullet list item
        ul_match = re.match(r"^-\s+(.*)", line)
        if ul_match:
            if in_ol:
                html_parts.append("</ol>")
                in_ol = False
            if not in_ul:
                html_parts.append(
                    '<ul style="margin:4px 0 4px 24px;padding:0;'
                    'line-height:1.7;list-style:disc;">'
                )
                in_ul = True
            body = _inline(ul_match.group(1))
            # Collect indented continuation lines under bullet
            i += 1
            while i < len(lines) and lines[i].startswith("  ") and lines[i].strip():
                body += f" {_inline(lines[i].strip())}"
                i += 1
            html_parts.append(f"<li>{body}</li>")
            continue

        # Plain paragraph line
        _close_lists()
        html_parts.append(
            f'<p style="margin:4px 0;line-height:1.6;">{_inline(line)}</p>'
        )
        i += 1

    _close_lists()
    return "\n".join(html_parts)


class HelpDialog(QDialog):
    """Resizable themed dialog for displaying help content."""

    def __init__(
        self,
        title: str,
        markdown_text: str,
        tokens: ShellThemeTokens,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setObjectName("shell.helpDialog")
        self.setMinimumSize(400, 300)
        self.resize(700, 550)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # --- header ---
        header = QWidget(self)
        header.setObjectName("shell.helpDialog.header")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(20, 16, 20, 12)
        header_layout.setSpacing(10)

        icon_label = QLabel(self)
        icon_label.setObjectName("shell.helpDialog.icon")
        icon_label.setText("\U0001F4D6")
        icon_label.setFixedWidth(28)
        icon_label.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(icon_label)

        title_label = QLabel(title, self)
        title_label.setObjectName("shell.helpDialog.title")
        header_layout.addWidget(title_label, 1)

        layout.addWidget(header)

        # --- content browser ---
        browser = QTextBrowser(self)
        browser.setObjectName("shell.helpDialog.browser")
        browser.setOpenExternalLinks(True)
        browser.setHtml(
            f'<div style="font-family:sans-serif;font-size:13px;'
            f"color:{tokens.text_primary};\">"
            f"{markdown_to_html(markdown_text, tokens)}</div>"
        )
        layout.addWidget(browser, 1)

        # --- footer with close button ---
        footer = QWidget(self)
        footer.setObjectName("shell.helpDialog.footer")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(20, 10, 20, 14)
        footer_layout.addStretch()

        close_btn = QPushButton("Close", self)
        close_btn.setObjectName("shell.helpDialog.closeBtn")
        close_btn.setFixedWidth(90)
        close_btn.clicked.connect(self.accept)
        close_btn.setDefault(True)
        footer_layout.addWidget(close_btn)

        layout.addWidget(footer)


def show_help_file(
    title: str,
    file_name: str,
    tokens: ShellThemeTokens,
    parent: QWidget | None = None,
) -> None:
    """Load a markdown help file and show it in a themed dialog."""
    from PySide2.QtWidgets import QMessageBox

    help_path = Path(__file__).resolve().parent / file_name
    if not help_path.exists():
        QMessageBox.warning(parent, title, f"Help file not found: {help_path}")
        return
    text = help_path.read_text(encoding="utf-8")
    dlg = HelpDialog(title, text, tokens, parent=parent)
    dlg.exec_()
