"""Pure text-editing helper functions shared by editor widgets/tests."""

from __future__ import annotations

import ast
import difflib
import importlib
import re
from dataclasses import dataclass


FLAT_PYTHON_CONFIDENCE_HIGH = "high"
FLAT_PYTHON_CONFIDENCE_MEDIUM = "medium"
FLAT_PYTHON_CONFIDENCE_LOW = "low"

_BLOCK_START_RE = re.compile(
    r"^(?:async\s+def|def|class|if|for|while|try|with)\b.*:\s*(?:#.*)?$"
)
_CLAUSE_RE = re.compile(r"^(?:elif\b.*|else|except\b.*|finally)\s*:\s*(?:#.*)?$")
_IF_CLAUSE_RE = re.compile(r"^(?:elif\b.*|else)\s*:\s*(?:#.*)?$")
_TRY_CLAUSE_RE = re.compile(r"^(?:except\b.*|finally)\s*:\s*(?:#.*)?$")
_TERMINAL_RE = re.compile(r"^(?:return|pass|raise|break|continue)\b")
_TOP_LEVEL_RESET_RE = re.compile(r"^(?:async\s+def|def|class|import|from)\b")
_PYTHON_SIGNAL_RE = re.compile(
    r"^(?:async\s+def|def|class|if|for|while|try|with|elif|else|except|finally|return|pass|raise|break|continue|import|from)\b"
)
_LINE_NUMBER_PREFIX_RE = re.compile(r"^\s*\d{1,5}(?:[.)\]:|-]?\s+)(.+)$")
_PROMPT_PREFIX_RE = re.compile(r"^\s*(?:>>>|\.\.\.)\s?(.+)$")


@dataclass(frozen=True)
class FlatPythonIndentRepairResult:
    """Result from best-effort repair of PDF-flattened Python indentation."""

    text: str
    changed: bool
    confidence: str
    parse_ok: bool
    reason: str = ""


def indent_lines(text: str, *, indent_text: str = "    ") -> str:
    """Indent every non-empty line in text."""
    lines = text.splitlines()
    return "\n".join(f"{indent_text}{line}" if line.strip() else line for line in lines)


def outdent_lines(text: str, *, indent_text: str = "    ") -> str:
    """Outdent lines by one indentation unit when present."""
    lines = text.splitlines()
    outdented: list[str] = []
    for line in lines:
        if line.startswith(indent_text):
            outdented.append(line[len(indent_text) :])
        elif line.startswith("\t"):
            outdented.append(line[1:])
        elif line.startswith(" "):
            outdented.append(line[1:])
        else:
            outdented.append(line)
    return "\n".join(outdented)


def toggle_comment_lines(text: str, *, comment_prefix: str = "#") -> str:
    """Toggle Python line comments for multi-line selection."""
    lines = text.splitlines()
    non_empty = [line for line in lines if line.strip()]
    if not non_empty:
        return text
    should_uncomment = all(line.startswith("#") for line in non_empty)

    transformed: list[str] = []
    for line in lines:
        if not line.strip():
            transformed.append(line)
            continue
        if should_uncomment:
            transformed.append(line[1:] if line.startswith("#") else line)
        else:
            transformed.append(f"{comment_prefix}{line}")
    return "\n".join(transformed)


def next_line_indentation(line_prefix: str, *, indent_text: str = "    ") -> str:
    """Compute indentation for a newline after ``line_prefix``."""
    leading = line_prefix[: len(line_prefix) - len(line_prefix.lstrip(" \t"))]
    stripped = line_prefix.rstrip()
    if stripped.endswith(":"):
        return f"{leading}{indent_text}"
    return leading


def looks_like_flat_python_paste(text: str) -> bool:
    """Return whether text appears to be a flattened multi-line Python paste."""
    normalized = _normalize_pasted_python_text(text)
    lines = _strip_consistent_pdf_prefixes(normalized.split("\n"))
    non_empty = [line for line in lines if line.strip()]
    if len(non_empty) < 2:
        return False

    content_lines = _strip_common_margin(lines)
    content_non_empty = [line for line in content_lines if line.strip()]
    if not content_non_empty:
        return False
    if _looks_intentionally_indented(content_non_empty):
        return False

    block_openers = 0
    python_signals = 0
    for line in content_non_empty:
        stripped = line.strip()
        if _BLOCK_START_RE.match(stripped) or _CLAUSE_RE.match(stripped):
            block_openers += 1
        if _PYTHON_SIGNAL_RE.match(stripped):
            python_signals += 1
    if block_openers <= 0:
        return False
    return python_signals >= 2 or len(content_non_empty) <= 4


def repair_flat_python_indentation(
    text: str,
    *,
    indent_text: str = "    ",
    base_indent: str = "",
) -> FlatPythonIndentRepairResult:
    """Best-effort repair for Python snippets whose indentation was flattened."""
    normalized = _normalize_pasted_python_text(text)
    had_trailing_newline = normalized.endswith("\n")
    original_lines = normalized.split("\n")
    if had_trailing_newline:
        original_lines = original_lines[:-1]

    stripped_prefix_lines = _strip_consistent_pdf_prefixes(original_lines)
    flat_lines = _strip_common_margin(stripped_prefix_lines)
    if not looks_like_flat_python_paste(normalized):
        parse_ok = _python_parse_ok(_strip_base_indent(normalized, base_indent))
        return FlatPythonIndentRepairResult(
            text=normalized,
            changed=normalized != text,
            confidence=FLAT_PYTHON_CONFIDENCE_LOW,
            parse_ok=parse_ok,
            reason="not a flat Python paste",
        )

    repaired_lines = _reindent_flat_python_lines(
        flat_lines,
        indent_text=indent_text,
        base_indent=base_indent,
    )
    repaired = "\n".join(repaired_lines)
    if had_trailing_newline:
        repaired += "\n"

    parse_target = _strip_base_indent(repaired, base_indent)
    parse_ok = _python_parse_ok(parse_target)
    confidence = FLAT_PYTHON_CONFIDENCE_HIGH if parse_ok else FLAT_PYTHON_CONFIDENCE_LOW
    reason = "parseable repair" if parse_ok else "repair did not parse"

    if not parse_ok:
        original_errors = _parso_error_count(_strip_base_indent(normalized, base_indent))
        repaired_errors = _parso_error_count(parse_target)
        if original_errors is not None and repaired_errors is not None and repaired_errors < original_errors:
            confidence = FLAT_PYTHON_CONFIDENCE_MEDIUM
            reason = "repair reduced parser errors"

    return FlatPythonIndentRepairResult(
        text=repaired,
        changed=repaired != normalized,
        confidence=confidence,
        parse_ok=parse_ok,
        reason=reason,
    )


def _normalize_pasted_python_text(text: str) -> str:
    normalized = text.replace("\u2029", "\n").replace("\r\n", "\n").replace("\r", "\n")
    return normalized.replace("\ufeff", "").replace("\u00a0", " ")


def _strip_consistent_pdf_prefixes(lines: list[str]) -> list[str]:
    non_empty = [line for line in lines if line.strip()]
    if len(non_empty) < 2:
        return list(lines)

    for pattern in (_PROMPT_PREFIX_RE, _LINE_NUMBER_PREFIX_RE):
        if all(pattern.match(line) for line in non_empty):
            stripped: list[str] = []
            for line in lines:
                if not line.strip():
                    stripped.append(line)
                    continue
                match = pattern.match(line)
                stripped.append(match.group(1) if match is not None else line)
            return stripped
    return list(lines)


def _strip_common_margin(lines: list[str]) -> list[str]:
    non_empty = [line for line in lines if line.strip()]
    if not non_empty:
        return list(lines)
    prefixes = [line[: len(line) - len(line.lstrip(" \t"))] for line in non_empty]
    common = prefixes[0]
    for prefix in prefixes[1:]:
        common = _common_whitespace_prefix(common, prefix)
        if not common:
            break
    if not common:
        return list(lines)
    return [line[len(common) :] if line.startswith(common) else line for line in lines]


def _common_whitespace_prefix(left: str, right: str) -> str:
    limit = min(len(left), len(right))
    index = 0
    while index < limit and left[index] == right[index] and left[index] in " \t":
        index += 1
    return left[:index]


def _looks_intentionally_indented(non_empty_lines: list[str]) -> bool:
    leading_lengths = [len(line) - len(line.lstrip(" \t")) for line in non_empty_lines]
    indented = [length for length in leading_lengths if length > 0]
    if not indented:
        return False
    if len(set(leading_lengths)) == 1:
        return False
    if 0 in leading_lengths:
        return True
    return len(indented) >= max(2, len(non_empty_lines) // 3)


def _reindent_flat_python_lines(
    lines: list[str],
    *,
    indent_text: str,
    base_indent: str,
) -> list[str]:
    stack: list[str] = []
    repaired: list[str] = []
    previous_blank = False
    previous_terminal = False

    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped:
            repaired.append("")
            previous_blank = True
            continue

        if previous_blank and _TOP_LEVEL_RESET_RE.match(stripped):
            stack = []

        clause_kind = _clause_kind(stripped)
        if clause_kind is not None:
            stack = _stack_for_clause(stack, clause_kind)
        elif previous_terminal and stack:
            stack = stack[:-1]

        repaired.append(f"{base_indent}{indent_text * len(stack)}{stripped}")

        if stripped.endswith(":"):
            stack.append(_block_kind(stripped))
            previous_terminal = False
        else:
            previous_terminal = bool(_TERMINAL_RE.match(stripped))
        previous_blank = False

    return repaired


def _clause_kind(stripped: str) -> str | None:
    if _IF_CLAUSE_RE.match(stripped):
        return "if"
    if _TRY_CLAUSE_RE.match(stripped):
        return "try"
    return None


def _stack_for_clause(stack: list[str], clause_kind: str) -> list[str]:
    for index in range(len(stack) - 1, -1, -1):
        if stack[index] == clause_kind or (clause_kind == "if" and stack[index] == "loop"):
            return stack[:index]
    return stack[:-1] if stack else []


def _block_kind(stripped: str) -> str:
    if stripped.startswith(("if ", "if(", "elif ", "elif(")):
        return "if"
    if stripped.startswith(("for ", "for(", "while ", "while(")):
        return "loop"
    if stripped.startswith(("try:", "except", "finally")):
        return "try"
    return "block"


def _strip_base_indent(text: str, base_indent: str) -> str:
    if not base_indent:
        return text
    lines = text.split("\n")
    return "\n".join(line[len(base_indent) :] if line.startswith(base_indent) else line for line in lines)


def _python_parse_ok(text: str) -> bool:
    try:
        ast.parse(text)
    except SyntaxError:
        return False
    return True


def _parso_error_count(text: str) -> int | None:
    try:
        parso = importlib.import_module("parso")
        grammar = parso.load_grammar()
        module = grammar.parse(text, error_recovery=True)
        return sum(1 for _issue in grammar.iter_errors(module))
    except Exception:
        return None


def smart_backspace_columns(line_text: str, cursor_column: int, *, indent_text: str = "    ") -> int:
    """Return how many columns smart-backspace should remove."""
    if cursor_column <= 0:
        return 0
    prefix = line_text[:cursor_column]
    if not prefix:
        return 0
    if prefix.strip():
        return 0

    if indent_text == "\t":
        return 1 if prefix.endswith("\t") else 0

    if "\t" in prefix:
        return 0
    unit = max(1, len(indent_text))
    remove_count = len(prefix) % unit
    if remove_count == 0:
        remove_count = unit
    if not prefix.endswith(" " * remove_count):
        return 0
    return remove_count


def map_offset_through_text_change(original_text: str, updated_text: str, offset: int) -> int:
    """Map a character offset from ``original_text`` into ``updated_text``."""
    if offset <= 0:
        return 0
    if offset >= len(original_text):
        return len(updated_text)

    safe_offset = max(0, min(offset, len(original_text)))
    matcher = difflib.SequenceMatcher(a=original_text, b=updated_text, autojunk=False)
    for tag, original_start, original_end, updated_start, updated_end in matcher.get_opcodes():
        if safe_offset < original_start:
            delta = safe_offset - original_start
            return max(0, updated_start + delta)
        if tag == "equal":
            if safe_offset <= original_end:
                return updated_start + (safe_offset - original_start)
            continue
        if safe_offset <= original_end:
            return updated_end
    return len(updated_text)
