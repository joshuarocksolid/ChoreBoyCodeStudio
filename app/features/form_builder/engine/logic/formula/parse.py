"""Guards, Excel fixes, and the allowlist lowering (CONTRACTS.md 17.2 and 17.7).

Guards run before ``ast.parse`` so a long or deep text never reaches the C parser.
Recognisers run on the raw text. A text that does not parse reports only its fixes.
"""

from __future__ import annotations

import ast
import io
import tokenize
from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List, Optional, Sequence, Tuple

from app.features.form_builder.engine.logic.formula.env import FormulaEnv
from app.features.form_builder.engine.logic.formula.nodes import (
    Attr,
    Bin,
    Bool,
    Call,
    Compare,
    Fix,
    FormulaProblem,
    IfElse,
    ListLit,
    Lit,
    Node,
    Ref,
    Span,
    Unary,
    WindowCall,
)
from app.features.form_builder.engine.logic.formula.types import (
    ANY,
    BLANK,
    NUMBER,
    TEXT,
    WHOLE,
    YESNO,
    decimal_from_literal,
    whole_from_literal,
)

_MAX_CHARS = 2000
_MAX_TOKENS = 400
_MAX_BRACKETS = 32
_MAX_DEPTH = 64

_FB103 = "Not available in formulas. Use a method instead."
_FB103_ASSIGN = "Formulas can't change things. Use a Set a field step."
_FB111 = "This formula is too long. Split it, or move it into a method."

_BIN = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/"}
_UNARY = {ast.Not: "not", ast.USub: "-", ast.UAdd: "+"}
_CMP = {
    ast.Eq: "==",
    ast.NotEq: "!=",
    ast.Lt: "<",
    ast.LtE: "<=",
    ast.Gt: ">",
    ast.GtE: ">=",
    ast.In: "in",
    ast.NotIn: "not in",
}
_EXCEL_CALLS = {
    "if": "excel_if",
    "and": "excel_and",
    "or": "excel_or",
    "not": "excel_not",
    "isblank": "excel_isblank",
}
_FIX_RANK = {
    "blank_compare": 0,
    "excel_if": 1,
    "excel_and": 1,
    "excel_or": 1,
    "excel_not": 1,
    "excel_isblank": 1,
    "join_amp": 2,
    "percent": 3,
    "diamond": 3,
    "amp_amp": 3,
    "pipe_pipe": 3,
    "bang": 3,
    "semicolon": 3,
    "leading_equals": 4,
    "compare_equals": 5,
    "bool_true": 6,
    "bool_false": 6,
    "label": 7,
}


@dataclass(frozen=True)
class Parsed:
    """The tree before types are checked. ``failed`` means ``tree`` is None."""

    tree: Optional[Node]
    problems: Tuple[FormulaProblem, ...]
    fixes: Tuple[Fix, ...]
    failed: bool


def apply_fix(text: str, fix: Fix) -> str:
    """Splice one fix. A second call with the same fix does not stack."""
    start = fix.span.start
    end = fix.span.end
    if start < 0 or start > len(text) or end < start:
        return text
    end = min(end, len(text))
    replacement = fix.replacement
    if replacement == "":
        # A deletion is already done when the span no longer holds the "=" it removed.
        if text[start:end].strip(" \t") != "=":
            return text
        return text[:start] + text[end:]
    if text.startswith(replacement, start) and end <= start + len(replacement):
        return text
    return text[:start] + replacement + text[end:]


def parse_text(text: str, env: FormulaEnv) -> Parsed:
    """Guards, fixes, parse, depth, then the allowlist. No check yet."""
    blocked = _guard(text)
    if blocked is not None:
        return Parsed(None, (blocked,), (), True)
    fixes = tuple(_excel_fixes(text, env))
    try:
        parsed = ast.parse(text, mode="eval")
    except SyntaxError as exc:
        if fixes:
            return Parsed(None, _problems_for(fixes), fixes, True)
        return Parsed(None, (_syntax_problem(text, exc),), (), True)
    if _depth(parsed) > _MAX_DEPTH:
        return Parsed(None, (_too_long(text),) + _problems_for(fixes), fixes, True)
    lower = _Lower(text)
    node = lower.expression(parsed.body)
    problems = tuple(lower.problems)
    if node is None:
        return Parsed(None, problems, fixes, True)
    return Parsed(node, problems, fixes, False)


def _guard(text: str) -> Optional[FormulaProblem]:
    if len(text) > _MAX_CHARS:
        return _too_long(text)
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return None
    count = 0
    depth = 0
    peak = 0
    for tok in tokens:
        if tok.type in (tokenize.ENCODING, tokenize.ENDMARKER):
            continue
        count += 1
        if tok.string in ("(", "[", "{"):
            depth += 1
            if depth > peak:
                peak = depth
        elif tok.string in (")", "]", "}"):
            depth = max(0, depth - 1)
    if count > _MAX_TOKENS or peak > _MAX_BRACKETS:
        return _too_long(text)
    return None


def _too_long(text: str) -> FormulaProblem:
    return FormulaProblem("FB111", Span(0, len(text)), _FB111)


def _syntax_problem(text: str, exc: SyntaxError) -> FormulaProblem:
    message = (exc.msg or "syntax error").splitlines()[0]
    starts = _line_starts(text)
    line = exc.lineno or 1
    if line < 1 or line > len(starts):
        start = 0
    else:
        offset = exc.offset or 1
        start = starts[line - 1] + max(offset - 1, 0)
    start = min(max(start, 0), len(text))
    end = min(len(text), start + 1) if start < len(text) else start
    return FormulaProblem(
        "FB108",
        Span(start, end),
        "This formula isn't finished: %s" % message,
    )


def _depth(root: ast.AST) -> int:
    peak = 1
    stack = [(root, 1)]
    while stack:
        node, level = stack.pop()
        if level > peak:
            peak = level
        for child in ast.iter_child_nodes(node):
            stack.append((child, level + 1))
    return peak


def _problems_for(fixes: Sequence[Fix]) -> Tuple[FormulaProblem, ...]:
    return tuple(
        FormulaProblem("FB107", fix.span, fix.message, fix.fix_id) for fix in fixes
    )


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


def _overlaps(left: Span, right: Span) -> bool:
    return not (left.end <= right.start or right.end <= left.start)


def _excel_fixes(text: str, env: FormulaEnv) -> List[Fix]:
    found: List[Fix] = []
    found.extend(_scan_excel(text))
    found.extend(_label_fixes(text, env))
    found.sort(key=lambda fix: (_FIX_RANK.get(fix.fix_id, 50), fix.span.start, fix.span.start - fix.span.end))
    chosen: List[Fix] = []
    for fix in found:
        if any(_overlaps(fix.span, kept.span) for kept in chosen):
            continue
        chosen.append(fix)
    chosen.sort(key=lambda fix: (fix.span.start, fix.span.end))
    return chosen


def _scan_excel(text: str) -> List[Fix]:
    fixes: List[Fix] = []
    length = len(text)
    depth_stack: List[str] = []
    index = 0
    while index < length:
        char = text[index]
        if char in "\"'":
            index = _skip_string(text, index)
            continue
        if char == "#":
            newline = text.find("\n", index)
            index = length if newline < 0 else newline
            continue
        if char == "(":
            word = _word_before(text, index)
            if word is not None and word[2].lower() in _EXCEL_CALLS:
                close = _matching_paren(text, index)
                if close is not None:
                    fix = _excel_call(text, word, index, close)
                    if fix is not None:
                        fixes.append(fix)
            kind = "call" if word is not None else "group"
            depth_stack.append(kind)
            index += 1
            continue
        if char in "[{":
            depth_stack.append("group")
            index += 1
            continue
        if char in ")]}":
            if depth_stack:
                depth_stack.pop()
            index += 1
            continue
        if text.startswith("==", index):
            fix = _blank_equals(text, index, index + 2)
            if fix is not None:
                fixes.append(fix)
            index += 2
            continue
        if char == "=" and (index == 0 or text[index - 1] not in "!<>"):
            fix = _equals_fix(text, index, depth_stack)
            if fix is not None:
                fixes.append(fix)
            index += 1
            continue
        if text.startswith("<>", index):
            fixes.append(Fix("diamond", Span(index, index + 2), "Use `!=`", "!="))
            index += 2
            continue
        if text.startswith("&&", index):
            fixes.append(Fix("amp_amp", Span(index, index + 2), "Use `and`", "and"))
            index += 2
            continue
        if text.startswith("||", index):
            fixes.append(Fix("pipe_pipe", Span(index, index + 2), "Use `or`", "or"))
            index += 2
            continue
        if char == "!" and not text.startswith("!=", index):
            fixes.append(Fix("bang", Span(index, index + 1), "Use `not`", "not "))
            index += 1
            continue
        if char == ";" :
            fixes.append(Fix("semicolon", Span(index, index + 1), "Separate the values with a comma.", ","))
            index += 1
            continue
        if char == "%" and index > 0 and text[index - 1].isdigit():
            fix = _percent_fix(text, index)
            if fix is not None:
                fixes.append(fix)
            index += 1
            continue
        if char == "&" and not text.startswith("&&", index):
            fix = _join_fix(text, index)
            if fix is not None:
                fixes.append(fix)
            index += 1
            continue
        word = _word_at(text, index)
        if word is not None:
            spelling, end = word
            if spelling in ("TRUE", "true"):
                fixes.append(Fix("bool_true", Span(index, end), "Use `True`", "True"))
            elif spelling in ("FALSE", "false"):
                fixes.append(Fix("bool_false", Span(index, end), "Use `False`", "False"))
            index = end
            continue
        index += 1
    leading = _leading_equals(text)
    if leading is not None:
        fixes.append(leading)
    return fixes


def _leading_equals(text: str) -> Optional[Fix]:
    index = 0
    while index < len(text) and text[index] in " \t":
        index += 1
    if index >= len(text) or text[index] != "=" or text.startswith("==", index):
        return None
    end = index + 1
    while end < len(text) and text[end] in " \t":
        end += 1
    return Fix("leading_equals", Span(index, end), "Formulas don't start with =", "")


def _blank_equals(text: str, index: int, after_op: int) -> Optional[Fix]:
    right = _atom_after(text, after_op)
    left = _atom_before(text, index)
    if left is None or right is None or not _blank_atom(text, right):
        return None
    replacement = "is_blank(%s)" % text[left[0] : left[1]].strip()
    return Fix("blank_compare", Span(left[0], right[1]), "Use `is_blank`", replacement)


def _equals_fix(text: str, index: int, stack: Sequence[str]) -> Optional[Fix]:
    if _is_keyword_equals(text, index, stack):
        return None
    blank = _blank_equals(text, index, index + 1)
    if blank is not None:
        return blank
    return Fix("compare_equals", Span(index, index + 1), "Use `==` to compare", "==")


def _is_keyword_equals(text: str, index: int, stack: Sequence[str]) -> bool:
    if not stack or stack[-1] != "call":
        return False
    word = _word_before(text, index)
    return word is not None and word[1] == index or (
        word is not None and text[word[1] : index].strip() == ""
    )


def _blank_atom(text: str, span: Tuple[int, int]) -> bool:
    piece = text[span[0] : span[1]].strip()
    return piece in ('""', "''", "None")


def _percent_fix(text: str, percent_at: int) -> Optional[Fix]:
    end = percent_at
    start = end - 1
    while start >= 0 and (text[start].isdigit() or text[start] in "._"):
        start -= 1
    start += 1
    # Pull a leading exponent piece only when it is still one number.
    token = text[start:end]
    if not token or not token[0].isdigit():
        return None
    if token.count(".") > 1:
        return None
    try:
        number = Decimal(token.replace("_", ""))
    except Exception:
        return None
    value = number / Decimal(100)
    if "." not in token and "e" not in token.lower():
        rendered = format(value.quantize(Decimal("0.01")), "f")
    else:
        rendered = format(value, "f")
    return Fix("percent", Span(start, percent_at + 1), "Write a decimal, like `0.10`.", rendered)


def _join_fix(text: str, amp_at: int) -> Optional[Fix]:
    left = _atom_before(text, amp_at)
    right = _atom_after(text, amp_at + 1)
    if left is None or right is None:
        return None
    left_text = text[left[0] : left[1]].strip()
    right_text = text[right[0] : right[1]].strip()
    if not left_text or not right_text:
        return None
    replacement = "text(%s) + text(%s)" % (left_text, right_text)
    return Fix("join_amp", Span(left[0], right[1]), "Join text with `+`", replacement)


def _excel_call(
    text: str,
    word: Tuple[int, int, str],
    open_at: int,
    close_at: int,
) -> Optional[Fix]:
    key = word[2].lower()
    args = _split_args(text, open_at, close_at)
    if args is None:
        return None
    stripped = [text[start:end].strip() for start, end in args]
    if any(piece == "" for piece in stripped):
        return None
    if key == "if":
        if len(stripped) != 3:
            return None
        replacement = "%s if %s else %s" % (stripped[1], stripped[0], stripped[2])
        message = "Write `x if c else y`"
        fix_id = "excel_if"
    elif key == "and":
        if len(stripped) < 2:
            return None
        replacement = " and ".join(stripped)
        message = "Use `and`, `or`, `not`"
        fix_id = "excel_and"
    elif key == "or":
        if len(stripped) < 2:
            return None
        replacement = " or ".join(stripped)
        message = "Use `and`, `or`, `not`"
        fix_id = "excel_or"
    elif key == "not":
        if len(stripped) != 1:
            return None
        replacement = "not %s" % stripped[0]
        message = "Use `and`, `or`, `not`"
        fix_id = "excel_not"
    else:
        if len(stripped) != 1:
            return None
        replacement = "is_blank(%s)" % stripped[0]
        message = "Use `is_blank`"
        fix_id = "excel_isblank"
    return Fix(fix_id, Span(word[0], close_at + 1), message, replacement)


def _label_fixes(text: str, env: FormulaEnv) -> List[Fix]:
    displays = []
    for obj, facts in env.widgets.items():
        if facts.display and facts.display != obj:
            displays.append((facts.display, obj))
    if not displays:
        return []
    fixes: List[Fix] = []
    try:
        tokens = tokenize.generate_tokens(io.StringIO(text).readline)
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return []
    starts = _line_starts(text)
    for tok in tokens:
        if tok.type != tokenize.NAME:
            continue
        for display, obj in displays:
            if tok.string != display:
                continue
            start = _abs(starts, tok.start, len(text))
            end = _abs(starts, tok.end, len(text))
            fixes.append(Fix("label", Span(start, end), "These are labels", obj))
            break
    return fixes


def _word_at(text: str, index: int) -> Optional[Tuple[str, int]]:
    if index > 0 and (text[index - 1].isalnum() or text[index - 1] == "_"):
        return None
    if not (text[index].isalpha() or text[index] == "_"):
        return None
    end = index + 1
    while end < len(text) and (text[end].isalnum() or text[end] == "_"):
        end += 1
    return text[index:end], end


def _word_before(text: str, index: int) -> Optional[Tuple[int, int, str]]:
    cursor = index
    while cursor > 0 and text[cursor - 1] in " \t\n":
        cursor -= 1
    end = cursor
    while cursor > 0 and (text[cursor - 1].isalnum() or text[cursor - 1] == "_"):
        cursor -= 1
    if cursor == end:
        return None
    return cursor, end, text[cursor:end]


def _atom_before(text: str, index: int) -> Optional[Tuple[int, int]]:
    cursor = index
    while cursor > 0 and text[cursor - 1] in " \t":
        cursor -= 1
    if cursor == 0:
        return None
    if text[cursor - 1] in ")]":
        open_at = _matching_open(text, cursor - 1)
        if open_at is None:
            return None
        return open_at, cursor
    if text[cursor - 1] in "\"'":
        return _string_span_ending(text, cursor)
    end = cursor
    while cursor > 0 and (text[cursor - 1].isalnum() or text[cursor - 1] in "_."):
        cursor -= 1
    if cursor == end:
        return None
    return cursor, end


def _atom_after(text: str, index: int) -> Optional[Tuple[int, int]]:
    cursor = index
    while cursor < len(text) and text[cursor] in " \t":
        cursor += 1
    if cursor >= len(text):
        return None
    if text[cursor] in "\"'":
        end = _skip_string(text, cursor)
        return cursor, end
    if text[cursor] in "([":
        close = _matching_paren(text, cursor) if text[cursor] == "(" else _matching_any(text, cursor)
        if close is None:
            return None
        return cursor, close + 1
    end = cursor
    while end < len(text) and (text[end].isalnum() or text[end] in "_."):
        end += 1
    if end == cursor:
        return None
    return cursor, end


def _skip_string(text: str, index: int) -> int:
    if text.startswith('"""', index) or text.startswith("'''", index):
        quote = text[index : index + 3]
        cursor = index + 3
        while cursor < len(text):
            if text.startswith("\\", cursor):
                cursor += 2
                continue
            if text.startswith(quote, cursor):
                return cursor + 3
            cursor += 1
        return len(text)
    quote = text[index]
    cursor = index + 1
    while cursor < len(text):
        if text[cursor] == "\\":
            cursor += 2
            continue
        if text[cursor] == quote:
            return cursor + 1
        if text[cursor] == "\n":
            return cursor
        cursor += 1
    return len(text)


def _string_span_ending(text: str, end: int) -> Optional[Tuple[int, int]]:
    # end is just after the closing quote. Walk back only for a one-line string.
    if end <= 0 or text[end - 1] not in "\"'":
        return None
    quote = text[end - 1]
    cursor = end - 2
    while cursor >= 0 and text[cursor] != quote and text[cursor] != "\n":
        if text[cursor] == "\\" and cursor > 0:
            cursor -= 2
            continue
        cursor -= 1
    if cursor < 0 or text[cursor] != quote:
        return None
    return cursor, end


def _matching_paren(text: str, open_at: int) -> Optional[int]:
    return _matching_any(text, open_at)


def _matching_any(text: str, open_at: int) -> Optional[int]:
    pairs = {"(": ")", "[": "]", "{": "}"}
    closing = pairs.get(text[open_at])
    if closing is None:
        return None
    depth = 0
    index = open_at
    while index < len(text):
        char = text[index]
        if char in "\"'":
            index = _skip_string(text, index)
            continue
        if char == text[open_at]:
            depth += 1
        elif char == closing:
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return None


def _matching_open(text: str, close_at: int) -> Optional[int]:
    pairs = {")": "(", "]": "[", "}": "{"}
    opening = pairs.get(text[close_at])
    if opening is None:
        return None
    depth = 0
    index = close_at
    while index >= 0:
        char = text[index]
        if char == text[close_at]:
            depth += 1
        elif char == opening:
            depth -= 1
            if depth == 0:
                return index
        index -= 1
    return None


def _split_args(text: str, open_at: int, close_at: int) -> Optional[List[Tuple[int, int]]]:
    args: List[Tuple[int, int]] = []
    depth = 0
    start = open_at + 1
    index = open_at
    while index <= close_at:
        char = text[index]
        if char in "\"'":
            index = _skip_string(text, index)
            continue
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
            if depth == 0 and index == close_at:
                args.append((start, index))
                return args
        elif char == "," and depth == 1:
            args.append((start, index))
            start = index + 1
        index += 1
    return None


class _Lower:
    """Turn an allowlisted expression into a tree. Rejected nodes become problems."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.starts = _line_starts(text)
        self.problems: List[FormulaProblem] = []
        self._numbers = self._collect(tokenize.NUMBER)
        self._strings = self._collect(tokenize.STRING)

    def _collect(self, kind: int) -> Dict[int, str]:
        found: Dict[int, str] = {}
        try:
            tokens = tokenize.generate_tokens(io.StringIO(self.text).readline)
        except (tokenize.TokenError, IndentationError, SyntaxError):
            return found
        for tok in tokens:
            if tok.type != kind:
                continue
            start = _abs(self.starts, tok.start, len(self.text))
            end = _abs(self.starts, tok.end, len(self.text))
            found[start] = self.text[start:end]
        return found

    def expression(self, node: ast.AST) -> Optional[Node]:
        return self._node(node, False)

    def _span(self, node: ast.AST) -> Span:
        lineno = getattr(node, "lineno", None)
        if not isinstance(lineno, int):
            return Span(0, 0)
        end_lineno = getattr(node, "end_lineno", None) or lineno
        col = getattr(node, "col_offset", 0) or 0
        end_col = getattr(node, "end_col_offset", None)
        start_line = self._line(lineno)
        start = self.starts[min(lineno, len(self.starts)) - 1] + _byte_to_char(start_line, col)
        if not isinstance(end_col, int):
            return Span(start, start)
        end_line = self._line(end_lineno)
        end = self.starts[min(end_lineno, len(self.starts)) - 1] + _byte_to_char(end_line, end_col)
        start = min(max(start, 0), len(self.text))
        end = min(max(end, start), len(self.text))
        return Span(start, end)

    def _line(self, lineno: int) -> str:
        if lineno < 1 or lineno > len(self.starts):
            return ""
        start = self.starts[lineno - 1]
        end = self.starts[lineno] if lineno < len(self.starts) else len(self.text)
        return self.text[start:end].rstrip("\n")

    def _reject(self, node: ast.AST, message: str = _FB103, code: str = "FB103") -> None:
        self.problems.append(FormulaProblem(code, self._span(node), message))

    def _node(self, node: ast.AST, allow_list: bool) -> Optional[Node]:
        if isinstance(node, ast.BinOp):
            op = _BIN.get(type(node.op))
            left = self._node(node.left, False)
            right = self._node(node.right, False)
            if op is None:
                self._reject(node)
                return None
            if left is None or right is None:
                return None
            return Bin(self._span(node), ANY, op, left, right)
        if isinstance(node, ast.UnaryOp):
            op = _UNARY.get(type(node.op))
            child = self._node(node.operand, False)
            if op is None:
                self._reject(node)
                return None
            if child is None:
                return None
            return Unary(self._span(node), ANY, op, child)
        if isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                op = "and"
            elif isinstance(node.op, ast.Or):
                op = "or"
            else:
                self._reject(node)
                return None
            values: List[Node] = []
            for item in node.values:
                child = self._node(item, False)
                if child is None:
                    return None
                values.append(child)
            return Bool(self._span(node), ANY, op, tuple(values))
        if isinstance(node, ast.Compare):
            return self._compare(node)
        if isinstance(node, ast.IfExp):
            test = self._node(node.test, False)
            yes = self._node(node.body, False)
            no = self._node(node.orelse, False)
            if test is None or yes is None or no is None:
                return None
            return IfElse(self._span(node), ANY, test, yes, no)
        if isinstance(node, ast.Call):
            return self._call(node)
        if isinstance(node, ast.Name):
            return Ref(self._span(node), ANY, node.id)
        if isinstance(node, ast.Attribute):
            return self._attr(node)
        if isinstance(node, ast.Constant):
            return self._constant(node)
        if isinstance(node, (ast.List, ast.Tuple)):
            if not allow_list:
                self._reject(node)
                return None
            return self._list(node)
        if isinstance(node, ast.NamedExpr):
            self._reject(node, _FB103_ASSIGN)
            return None
        self._reject(node)
        return None

    def _compare(self, node: ast.Compare) -> Optional[Node]:
        first = self._node(node.left, False)
        if first is None:
            return None
        pairs: List[Tuple[str, Node]] = []
        for op, comp in zip(node.ops, node.comparators):
            symbol = _CMP.get(type(op))
            allow = isinstance(op, (ast.In, ast.NotIn))
            if symbol is None:
                self._reject(node)
                return None
            child = self._node(comp, allow)
            if child is None:
                return None
            if allow and not isinstance(child, ListLit):
                self._reject(comp)
                return None
            pairs.append((symbol, child))
        return Compare(self._span(node), ANY, first, tuple(pairs))

    def _call(self, node: ast.Call) -> Optional[Node]:
        if node.keywords:
            for keyword in node.keywords:
                self._reject(keyword)
            return None
        args: List[Node] = []
        for arg in node.args:
            if isinstance(arg, ast.Starred):
                self._reject(arg)
                return None
            child = self._node(arg, False)
            if child is None:
                return None
            args.append(child)
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "window"
            and not isinstance(func.value, ast.Attribute)
        ):
            return WindowCall(self._span(node), ANY, func.attr, tuple(args))
        if isinstance(func, ast.Name):
            return Call(self._span(node), ANY, func.id, tuple(args))
        self._reject(node)
        return None

    def _attr(self, node: ast.Attribute) -> Optional[Node]:
        names: List[str] = []
        current: ast.AST = node
        while isinstance(current, ast.Attribute):
            names.append(current.attr)
            current = current.value
        names.reverse()
        if not isinstance(current, ast.Name):
            self._reject(node)
            return None
        if len(names) > 2:
            self._reject(
                node,
                "%s has no %s." % (current.id, ".".join(names)),
                "FB114",
            )
            return None
        base = Ref(self._span(current), ANY, current.id)
        sub = names[1] if len(names) == 2 else None
        return Attr(self._span(node), ANY, base, names[0], sub)

    def _constant(self, node: ast.Constant) -> Optional[Node]:
        span = self._span(node)
        value = node.value
        if isinstance(value, bool):
            return Lit(span, YESNO, value)
        if value is None:
            return Lit(span, BLANK, None)
        if isinstance(value, str):
            source = self._strings.get(span.start, "")
            if "\n" in source or "\r" in source:
                self._reject(node)
                return None
            return Lit(span, TEXT, value)
        if isinstance(value, int):
            return self._number(node, span)
        if isinstance(value, float):
            return self._number(node, span)
        self._reject(node)
        return None

    def _number(self, node: ast.AST, span: Span) -> Optional[Node]:
        source = self._numbers.get(span.start)
        if source is None:
            for start, token in self._numbers.items():
                if span.start <= start < span.end:
                    source = token
                    break
        if source is None:
            self._reject(node)
            return None
        if _forbidden_number(source):
            self._reject(node)
            return None
        float_token = "." in source or "e" in source.lower() or "E" in source
        if float_token:
            try:
                literal = decimal_from_literal(source)
            except Exception:
                self._reject(node)
                return None
            return Lit(span, NUMBER, literal)
        try:
            literal_int = whole_from_literal(source)
        except Exception:
            self._reject(node)
            return None
        return Lit(span, WHOLE, literal_int)

    def _list(self, node: ast.AST) -> Optional[Node]:
        elts = getattr(node, "elts")
        items: List[Node] = []
        for elt in elts:
            allowed = isinstance(elt, ast.Constant) or (
                isinstance(elt, ast.UnaryOp) and isinstance(elt.op, (ast.UAdd, ast.USub))
            )
            if not allowed:
                self._reject(elt)
                return None
            child = self._node(elt, False)
            if child is None:
                return None
            if isinstance(elt, ast.UnaryOp) and not isinstance(child, Unary):
                self._reject(elt)
                return None
            items.append(child)
        return ListLit(self._span(node), ANY, tuple(items))


def _byte_to_char(line: str, byte_off: int) -> int:
    raw = line.encode("utf-8")
    clipped = raw[: max(0, byte_off)]
    while True:
        try:
            return len(clipped.decode("utf-8"))
        except UnicodeDecodeError:
            if not clipped:
                return 0
            clipped = clipped[:-1]


def _forbidden_number(source: str) -> bool:
    token = source.lower().replace("_", "")
    if token.endswith("j"):
        return True
    return token.startswith("0x") or token.startswith("0o") or token.startswith("0b")
