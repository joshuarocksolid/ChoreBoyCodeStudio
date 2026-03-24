"""Minimal INI/.desktop syntax highlighter for packaging-oriented config files."""

from __future__ import annotations

import re

from app.editors.syntax_engine import TokenStyle, ThemedSyntaxHighlighter

_COMMENT_PATTERN = re.compile(r"^\s*[#;].*$")
_SECTION_PATTERN = re.compile(r"^(\s*)(\[)([^\]\n]+)(\])(\s*)$")
_KEY_VALUE_PATTERN = re.compile(r"^(\s*)([^=\s][^=]*?)(\s*)(=)(\s*)(.*)$")
_NUMBER_PATTERN = re.compile(r"^[+-]?(?:\d+(?:\.\d+)?)$")
_BOOLEAN_PATTERN = re.compile(r"^(?:true|false|yes|no|on|off)$", re.IGNORECASE)


class IniSyntaxHighlighter(ThemedSyntaxHighlighter):
    """Simple line-based highlighter used when no practical Tree-sitter INI wheel exists."""

    TOKEN_STYLES = {
        "comment": TokenStyle("comment", italic=True),
        "section": TokenStyle("class", bold=True),
        "key": TokenStyle("json_key"),
        "value": TokenStyle("string"),
        "number": TokenStyle("number"),
        "boolean": TokenStyle("json_literal"),
        "punctuation": TokenStyle("punctuation"),
    }

    _language_key = "ini"
    _language_display_name = "INI / Desktop Entry"

    def language_key(self) -> str:
        return self._language_key

    def language_display_name(self) -> str:
        return self._language_display_name

    def highlightBlock(self, text: str) -> None:  # noqa: N802
        if not text:
            return
        if _COMMENT_PATTERN.match(text):
            self._apply_token("comment", 0, len(text))
            return

        section_match = _SECTION_PATTERN.match(text)
        if section_match is not None:
            self._apply_token("punctuation", section_match.start(2), section_match.end(2))
            self._apply_token("section", section_match.start(3), section_match.end(3))
            self._apply_token("punctuation", section_match.start(4), section_match.end(4))
            return

        key_value_match = _KEY_VALUE_PATTERN.match(text)
        if key_value_match is None:
            return

        self._apply_token("key", key_value_match.start(2), key_value_match.end(2))
        self._apply_token("punctuation", key_value_match.start(4), key_value_match.end(4))

        value_text = key_value_match.group(6)
        value_start = key_value_match.start(6)
        value_end = key_value_match.end(6)
        if value_end <= value_start:
            return
        token_name = self._classify_value(value_text)
        self._apply_token(token_name, value_start, value_end)

    def describe_position(self, line_number: int, column: int) -> str:
        document = self.document()
        if document is None:
            return "Language: INI / Desktop Entry\nNo document is attached."
        block = document.findBlockByNumber(max(0, line_number))
        if not block.isValid():
            return "Language: INI / Desktop Entry\nCursor is outside the document."
        text = block.text()
        token_name = self._token_name_for_column(text, max(0, column))
        lines = [
            "Language: INI / Desktop Entry",
            "Engine: regex fallback highlighter",
            "Token: %s" % (token_name or "plain_text"),
            "Line: %s" % (line_number + 1),
            "Column: %s" % (column + 1),
        ]
        if token_name is not None:
            token_format = self._format(token_name if token_name != "section" else "section")
            color_name = None if token_format is None else token_format.foreground().color().name().lower()
            if color_name:
                lines.append(f"Color: {color_name}")
        return "\n".join(lines)

    def _apply_token(self, token_name: str, start: int, end: int) -> None:
        if end <= start:
            return
        token_format = self._format(token_name)
        if token_format is None:
            return
        self.setFormat(start, end - start, token_format)

    @staticmethod
    def _classify_value(value_text: str) -> str:
        stripped = value_text.strip()
        if not stripped:
            return "value"
        if _NUMBER_PATTERN.match(stripped):
            return "number"
        if _BOOLEAN_PATTERN.match(stripped):
            return "boolean"
        return "value"

    def _token_name_for_column(self, text: str, column: int) -> str | None:
        if not text:
            return None
        if _COMMENT_PATTERN.match(text):
            return "comment" if 0 <= column < len(text) else None

        section_match = _SECTION_PATTERN.match(text)
        if section_match is not None:
            if section_match.start(2) <= column < section_match.end(2):
                return "punctuation"
            if section_match.start(3) <= column < section_match.end(3):
                return "section"
            if section_match.start(4) <= column < section_match.end(4):
                return "punctuation"
            return None

        key_value_match = _KEY_VALUE_PATTERN.match(text)
        if key_value_match is None:
            return None
        if key_value_match.start(2) <= column < key_value_match.end(2):
            return "key"
        if key_value_match.start(4) <= column < key_value_match.end(4):
            return "punctuation"
        if key_value_match.start(6) <= column < key_value_match.end(6):
            return self._classify_value(key_value_match.group(6))
        return None
