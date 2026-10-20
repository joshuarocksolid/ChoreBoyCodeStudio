"""Where the cursor sits for completion, and when the list may open by itself."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Tuple

from app.intelligence.completion_mode import COMPLETION_MODE_TYPING

SITE_MEMBER = "member"
SITE_NAME = "name"
SITE_NONE = "none"

BLOCKED_STRING = "string"
BLOCKED_COMMENT = "comment"
BLOCKED_NUMERIC_DOT = "numeric_dot"
BLOCKED_NUMBER = "number"

TYPING_NAME_MIN_CHARS = 2

_IDENTIFIER_TAIL = re.compile(r"[A-Za-z_][A-Za-z0-9_]*$")
_WORD_TAIL = re.compile(r"[A-Za-z0-9_]*$")
_CODE_SCAN = re.compile(r"[\"'#]")
_STRING_END = {
    '"': re.compile(r'\\.|"|\n', re.S),
    "'": re.compile(r"\\.|'|\n", re.S),
    '"""': re.compile(r'\\.|"""', re.S),
    "'''": re.compile(r"\\.|'''", re.S),
}


@dataclass(frozen=True)
class CompletionSite:
    """The identifier being completed at the cursor.

    ``anchor`` is where the identifier starts; ``prefix`` is what was typed
    from there to the cursor. ``key`` is stable while the user types inside one
    expression and changes as soon as they leave it.
    """

    kind: str
    anchor: int
    prefix: str
    blocked: str = ""
    line_head: str = ""

    @property
    def key(self) -> Tuple[str, int, str]:
        return (self.kind, self.anchor, self.line_head)

    @property
    def is_open_able(self) -> bool:
        return self.kind != SITE_NONE and not self.blocked


def text_state_at_end(text: str) -> str:
    """Return ``code``, ``string`` or ``comment`` for the end of Python ``text``."""

    index = 0
    quote = ""
    while True:
        if not quote:
            found = _CODE_SCAN.search(text, index)
            if found is None:
                return "code"
            start = found.start()
            ch = text[start]
            if ch == "#":
                newline = text.find("\n", start)
                if newline < 0:
                    return BLOCKED_COMMENT
                index = newline + 1
                continue
            if text.startswith(ch * 3, start):
                quote = ch * 3
                index = start + 3
            else:
                quote = ch
                index = start + 1
            continue
        closing = _STRING_END[quote].search(text, index)
        if closing is None:
            return BLOCKED_STRING
        token = closing.group(0)
        index = closing.end()
        if token.startswith("\\"):
            continue
        quote = ""


def is_numeric_dot(line_before_cursor: str) -> bool:
    """Return True for ``1.``, ``x = 2_000.`` and similar fraction starts."""

    if not line_before_cursor.endswith("."):
        return False
    digits = _WORD_TAIL.search(line_before_cursor[:-1])
    word = digits.group(0) if digits is not None else ""
    return bool(word) and word[0].isdigit()


def completion_site(text: str, cursor: int, *, check_strings: bool = True) -> CompletionSite:
    """Classify the cursor position in Python ``text``.

    ``check_strings`` scans ``text`` from the start for strings and comments.
    Callers skip it while a list is already open, because any quote or ``#``
    typed since then has closed the list.
    """

    cursor = max(0, min(cursor, len(text)))
    line_start = text.rfind("\n", 0, cursor) + 1
    word = _WORD_TAIL.search(text, line_start, cursor)
    word_text = word.group(0) if word is not None else ""
    anchor = cursor - len(word_text)
    head = text[line_start:anchor]
    state = text_state_at_end(text[:cursor]) if check_strings else "code"
    if state != "code":
        return CompletionSite(SITE_NONE, anchor, word_text, blocked=state, line_head=head)
    if word_text and word_text[0].isdigit():
        return CompletionSite(SITE_NONE, anchor, word_text, blocked=BLOCKED_NUMBER, line_head=head)
    if head.endswith("."):
        if is_numeric_dot(head):
            return CompletionSite(SITE_NONE, anchor, word_text, blocked=BLOCKED_NUMERIC_DOT, line_head=head)
        receiver = _IDENTIFIER_TAIL.search(head[:-1].rstrip())
        if receiver is None and not head[:-1].rstrip().endswith((")", "]")):
            return CompletionSite(SITE_NONE, anchor, word_text, line_head=head)
        return CompletionSite(SITE_MEMBER, anchor, word_text, line_head=head)
    return CompletionSite(SITE_NAME, anchor, word_text, line_head=head)


def should_open_while_typing(mode: str, site: CompletionSite, inserted_text: str) -> bool:
    """Return True when typing ``inserted_text`` should open the list by itself."""

    if mode != COMPLETION_MODE_TYPING or not site.is_open_able:
        return False
    if inserted_text == ".":
        return site.kind == SITE_MEMBER and not site.prefix
    if not (inserted_text.isalnum() or inserted_text == "_"):
        return False
    return site.kind == SITE_NAME and len(site.prefix) == TYPING_NAME_MIN_CHARS


__all__ = [
    "BLOCKED_COMMENT",
    "BLOCKED_NUMBER",
    "BLOCKED_NUMERIC_DOT",
    "BLOCKED_STRING",
    "CompletionSite",
    "SITE_MEMBER",
    "SITE_NAME",
    "SITE_NONE",
    "TYPING_NAME_MIN_CHARS",
    "completion_site",
    "is_numeric_dot",
    "should_open_while_typing",
    "text_state_at_end",
]
