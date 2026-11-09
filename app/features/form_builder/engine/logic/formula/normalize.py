"""Canonical formula text (CONTRACTS.md section 17.8).

Spacing is redone from the token stream. Strings and numbers are copied from the
source so ``1.10`` and escapes stay put. The result parses to the same ``ast.dump``.
"""

from __future__ import annotations

import io
import tokenize
from typing import List, Optional, Sequence, Tuple


def normalize(text: str) -> str:
    """Return the canonical spelling. Idempotent, and meaning-preserving when it parses."""
    if text.strip() == "":
        return ""
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return text.strip()
    starts = _line_starts(text)
    pieces: List[str] = []
    prev: Optional[str] = None
    depth = 0
    broke = False
    for tok in tokens:
        if tok.type in (tokenize.ENCODING, tokenize.ENDMARKER, tokenize.COMMENT, tokenize.INDENT, tokenize.DEDENT):
            continue
        if tok.type in (tokenize.NL, tokenize.NEWLINE):
            broke = True
            continue
        source = _source(text, starts, tok)
        kind = _classify(source, prev)
        prefix, broke = _break_prefix(broke, depth, pieces)
        if prefix:
            pieces.append(prefix)
        if _space_before(prev, kind) and prefix == "":
            pieces.append(" ")
        elif prefix == " " and not _space_before(prev, kind):
            pieces.pop()
        pieces.append(source)
        if kind == "open":
            depth += 1
        elif kind == "close":
            depth = max(0, depth - 1)
        prev = kind
    return "".join(pieces).strip()


def _break_prefix(broke: bool, depth: int, pieces: Sequence[str]) -> Tuple[str, bool]:
    if not broke:
        return "", False
    if not pieces:
        return "", False
    if depth > 0:
        return "\n    ", False
    return " ", False


def _classify(source: str, prev: Optional[str]) -> str:
    if source in ("(", "["):
        return "open"
    if source in (")", "]"):
        return "close"
    if source == ",":
        return "comma"
    if source == ".":
        return "dot"
    if source == "->":
        return "op"
    if source in ("+", "-") and prev in (None, "open", "op", "comma", "keyword", "unary"):
        return "unary"
    if source in ("+", "-", "*", "/", "==", "!=", "<", "<=", ">", ">=", "and", "or", "not", "if", "else", "in"):
        if source in ("and", "or", "not", "if", "else", "in"):
            return "keyword"
        return "op"
    if source in ("and", "or", "not", "if", "else", "in"):
        return "keyword"
    return "atom"


def _space_before(prev: Optional[str], kind: str) -> bool:
    if kind in ("close", "comma", "dot"):
        return False
    if prev in (None, "open", "dot"):
        return False
    if prev == "unary":
        # A glued ``->`` is one token on 3.11 and two tokens on 3.9.
        return kind == "op"
    if prev == "comma":
        return True
    if kind == "unary":
        return prev in ("atom", "close", "op", "keyword")
    if kind == "open":
        return prev == "keyword"
    if prev == "atom" and kind == "atom":
        return True
    if prev in ("op", "keyword") or kind in ("op", "keyword"):
        return True
    return False


def _source(text: str, starts: Sequence[int], tok: tokenize.TokenInfo) -> str:
    if tok.type in (tokenize.STRING, tokenize.NUMBER):
        start = _abs(starts, tok.start, len(text))
        end = _abs(starts, tok.end, len(text))
        return text[start:end]
    return tok.string


def _line_starts(text: str) -> List[int]:
    starts = [0]
    for index, char in enumerate(text):
        if char == "\n":
            starts.append(index + 1)
    return starts


def _abs(starts: Sequence[int], pos: Tuple[int, int], limit: int) -> int:
    line, col = pos
    if line < 1 or line > len(starts):
        return limit
    return min(limit, starts[line - 1] + col)
