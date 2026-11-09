"""Style sheet tokens with line and column (UX-STYLE-004). Qt-free.

The tokenizer never raises. It returns every token, including white space and
comments, so a caller can rebuild the exact text, and a list of lexical
problems (an unterminated string or comment). Lines and columns are 1-based.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

#: Token kinds: ``ws``, ``comment``, ``ident``, ``number``, ``string``,
#: ``hash`` (``#`` and the name after it), ``at`` (``@`` and its name) and
#: ``delim`` (any other single character, brackets and braces included).
WS = "ws"
COMMENT = "comment"
IDENT = "ident"
NUMBER = "number"
STRING = "string"
HASH = "hash"
AT = "at"
DELIM = "delim"


@dataclass(frozen=True)
class Token:
    kind: str
    text: str
    start: int
    end: int
    line: int
    column: int

    @property
    def significant(self) -> bool:
        return self.kind not in (WS, COMMENT)


@dataclass(frozen=True)
class LexProblem:
    """``missing`` is the text the sheet lacks: ``*/`` or the quote character."""

    missing: str
    line: int
    column: int


def _is_name_start(ch: str) -> bool:
    return ch.isalpha() or ch == "_" or ord(ch) > 127


def _is_name(ch: str) -> bool:
    return ch.isalnum() or ch in "_-" or ord(ch) > 127


def tokenize(text: str) -> Tuple[Tuple[Token, ...], Tuple[LexProblem, ...]]:
    tokens: List[Token] = []
    problems: List[LexProblem] = []
    length = len(text)
    index = 0
    line = 1
    line_start = 0

    def add(kind: str, start: int, end: int, at_line: int, at_start: int) -> None:
        tokens.append(Token(kind, text[start:end], start, end, at_line, start - at_start + 1))

    while index < length:
        ch = text[index]
        start = index
        at_line = line
        at_start = line_start
        if ch.isspace():
            while index < length and text[index].isspace():
                if text[index] == "\n":
                    line += 1
                    line_start = index + 1
                index += 1
            add(WS, start, index, at_line, at_start)
        elif ch == "/" and text.startswith("/*", index):
            close = text.find("*/", index + 2)
            if close < 0:
                # Qt does not see a comment here: the "/" and "*" are stray
                # characters and the text after them is read as usual.
                problems.append(LexProblem("*/", at_line, start - at_start + 1))
                index += 1
                add(DELIM, start, index, at_line, at_start)
                continue
            stop = close + 2
            for position in range(index, stop):
                if text[position] == "\n":
                    line += 1
                    line_start = position + 1
            index = stop
            add(COMMENT, start, index, at_line, at_start)
        elif ch in "\"'":
            index += 1
            closed = False
            while index < length:
                here = text[index]
                if here == "\\" and index + 1 < length:
                    index += 2
                    continue
                if here == "\n":
                    break
                index += 1
                if here == ch:
                    closed = True
                    break
            if not closed:
                problems.append(LexProblem(ch, at_line, start - at_start + 1))
            add(STRING, start, index, at_line, at_start)
        elif ch == "#" and index + 1 < length and _is_name(text[index + 1]):
            index += 1
            while index < length and _is_name(text[index]):
                index += 1
            add(HASH, start, index, at_line, at_start)
        elif ch == "@" and index + 1 < length and _is_name_start(text[index + 1]):
            index += 1
            while index < length and _is_name(text[index]):
                index += 1
            add(AT, start, index, at_line, at_start)
        elif _is_name_start(ch) or (ch == "-" and index + 1 < length and (_is_name_start(text[index + 1]) or text[index + 1] == "-")):
            index += 1
            while index < length and _is_name(text[index]):
                index += 1
            add(IDENT, start, index, at_line, at_start)
        elif ch.isdigit() or (ch in "+-." and index + 1 < length and (text[index + 1].isdigit() or (ch != "." and text[index + 1] == "." and index + 2 < length and text[index + 2].isdigit()))):
            index += 1
            while index < length and (text[index].isdigit() or text[index] == "."):
                index += 1
            while index < length and (text[index].isalpha() or text[index] == "%"):
                index += 1
            add(NUMBER, start, index, at_line, at_start)
        else:
            index += 1
            add(DELIM, start, index, at_line, at_start)
    return tuple(tokens), tuple(problems)
