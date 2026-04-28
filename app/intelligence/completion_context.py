"""Completion context classification and cache-validity helpers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import re


class CompletionSyntacticContext(str, Enum):
    """Syntactic shape of a completion request."""

    IDENTIFIER = "identifier"
    DOTTED_MEMBER = "dotted_member"
    IMPORT_FROM_MEMBER = "import_from_member"
    IMPORT_MODULE = "import_module"
    CALL = "call"
    STRING_OR_COMMENT = "string_or_comment"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class CompletionReplacementRange:
    """Buffer range replaced when a completion is accepted."""

    start: int
    end: int


@dataclass(frozen=True)
class CompletionValidFor:
    """Cache validity key for filtering a previous completion result."""

    syntactic_context: CompletionSyntacticContext
    replacement_start: int
    base_expression: str = ""
    module_name: str = ""

    def matches(self, context: "CompletionContext") -> bool:
        """Return whether cached items can be filtered for ``context``."""

        return (
            self.syntactic_context == context.syntactic_context
            and self.replacement_start == context.replacement_range.start
            and self.base_expression == context.base_expression
            and self.module_name == context.module_name
        )


@dataclass(frozen=True)
class CompletionContext:
    """Normalized completion query facts shared by providers and UI policy."""

    language: str
    file_path: str
    project_root: str | None
    source_text: str
    cursor_position: int
    buffer_revision: int | None
    trigger_kind: str
    trigger_character: str
    trigger_is_manual: bool
    min_prefix_chars: int
    max_results: int
    syntactic_context: CompletionSyntacticContext
    prefix: str
    replacement_range: CompletionReplacementRange
    valid_for: CompletionValidFor
    fingerprint: str
    base_expression: str = ""
    module_name: str = ""
    trusted_runtime_module: str = ""

    @property
    def should_offer_automatic_results(self) -> bool:
        """Return whether automatic completion should run for this context."""

        if self.syntactic_context == CompletionSyntacticContext.STRING_OR_COMMENT:
            return False
        if self.trigger_is_manual:
            return True
        if self.syntactic_context in {
            CompletionSyntacticContext.DOTTED_MEMBER,
            CompletionSyntacticContext.IMPORT_FROM_MEMBER,
            CompletionSyntacticContext.IMPORT_MODULE,
        }:
            return True
        return len(self.prefix) >= max(1, int(self.min_prefix_chars))


_IDENTIFIER_PREFIX_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*$")
_DOTTED_NAME = r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*"
_DOTTED_MEMBER_CONTEXT_PATTERN = re.compile(r"(" + _DOTTED_NAME + r")\.([A-Za-z_][A-Za-z0-9_]*)?$")
_IMPORT_FROM_CONTEXT_PATTERN = re.compile(
    r"\bfrom\s+(" + _DOTTED_NAME + r")\s+import\s+([A-Za-z_][A-Za-z0-9_]*)?$"
)
_IMPORT_MODULE_CONTEXT_PATTERN = re.compile(
    r"\bimport\s+(" + _DOTTED_NAME + r")\.([A-Za-z_][A-Za-z0-9_]*)?$"
)

_TRUSTED_RUNTIME_ROOTS = frozenset({"FreeCAD", "PySide2", "QtCore", "QtGui", "QtWidgets"})


def build_completion_context(
    *,
    source_text: str,
    cursor_position: int,
    current_file_path: str,
    project_root: str | None,
    trigger_is_manual: bool,
    min_prefix_chars: int,
    max_results: int,
    trigger_kind: str = "invoked",
    trigger_character: str = "",
    buffer_revision: int | None = None,
    language: str = "python",
) -> CompletionContext:
    """Classify the cursor position into a provider-friendly context."""

    safe_position = max(0, min(cursor_position, len(source_text)))
    prefix_text = source_text[:safe_position]
    line_prefix = _current_line_prefix(prefix_text)

    if _is_likely_string_or_comment(line_prefix):
        return _context(
            language=language,
            file_path=current_file_path,
            project_root=project_root,
            source_text=source_text,
            cursor_position=safe_position,
            buffer_revision=buffer_revision,
            trigger_kind=trigger_kind,
            trigger_character=trigger_character,
            trigger_is_manual=trigger_is_manual,
            min_prefix_chars=min_prefix_chars,
            max_results=max_results,
            syntactic_context=CompletionSyntacticContext.STRING_OR_COMMENT,
            prefix="",
            replacement_start=safe_position,
            base_expression="",
            module_name="",
        )

    import_from = _IMPORT_FROM_CONTEXT_PATTERN.search(line_prefix)
    if import_from is not None:
        module_name = import_from.group(1)
        prefix = import_from.group(2) or ""
        return _context(
            language=language,
            file_path=current_file_path,
            project_root=project_root,
            source_text=source_text,
            cursor_position=safe_position,
            buffer_revision=buffer_revision,
            trigger_kind=trigger_kind,
            trigger_character=trigger_character,
            trigger_is_manual=trigger_is_manual,
            min_prefix_chars=min_prefix_chars,
            max_results=max_results,
            syntactic_context=CompletionSyntacticContext.IMPORT_FROM_MEMBER,
            prefix=prefix,
            replacement_start=safe_position - len(prefix),
            base_expression=module_name,
            module_name=module_name,
        )

    import_module = _IMPORT_MODULE_CONTEXT_PATTERN.search(line_prefix)
    if import_module is not None:
        module_name = import_module.group(1)
        prefix = import_module.group(2) or ""
        return _context(
            language=language,
            file_path=current_file_path,
            project_root=project_root,
            source_text=source_text,
            cursor_position=safe_position,
            buffer_revision=buffer_revision,
            trigger_kind=trigger_kind,
            trigger_character=trigger_character,
            trigger_is_manual=trigger_is_manual,
            min_prefix_chars=min_prefix_chars,
            max_results=max_results,
            syntactic_context=CompletionSyntacticContext.IMPORT_MODULE,
            prefix=prefix,
            replacement_start=safe_position - len(prefix),
            base_expression=module_name,
            module_name=module_name,
        )

    dotted_member = _DOTTED_MEMBER_CONTEXT_PATTERN.search(prefix_text)
    if dotted_member is not None:
        base_expression = dotted_member.group(1)
        prefix = dotted_member.group(2) or ""
        return _context(
            language=language,
            file_path=current_file_path,
            project_root=project_root,
            source_text=source_text,
            cursor_position=safe_position,
            buffer_revision=buffer_revision,
            trigger_kind=trigger_kind,
            trigger_character=trigger_character,
            trigger_is_manual=trigger_is_manual,
            min_prefix_chars=min_prefix_chars,
            max_results=max_results,
            syntactic_context=CompletionSyntacticContext.DOTTED_MEMBER,
            prefix=prefix,
            replacement_start=safe_position - len(prefix),
            base_expression=base_expression,
            module_name=base_expression,
        )

    if line_prefix.endswith("("):
        return _context(
            language=language,
            file_path=current_file_path,
            project_root=project_root,
            source_text=source_text,
            cursor_position=safe_position,
            buffer_revision=buffer_revision,
            trigger_kind=trigger_kind,
            trigger_character=trigger_character,
            trigger_is_manual=trigger_is_manual,
            min_prefix_chars=min_prefix_chars,
            max_results=max_results,
            syntactic_context=CompletionSyntacticContext.CALL,
            prefix="",
            replacement_start=safe_position,
            base_expression="",
            module_name="",
        )

    prefix = extract_identifier_prefix(source_text, safe_position)
    return _context(
        language=language,
        file_path=current_file_path,
        project_root=project_root,
        source_text=source_text,
        cursor_position=safe_position,
        buffer_revision=buffer_revision,
        trigger_kind=trigger_kind,
        trigger_character=trigger_character,
        trigger_is_manual=trigger_is_manual,
        min_prefix_chars=min_prefix_chars,
        max_results=max_results,
        syntactic_context=CompletionSyntacticContext.IDENTIFIER if prefix else CompletionSyntacticContext.UNKNOWN,
        prefix=prefix,
        replacement_start=safe_position - len(prefix),
        base_expression="",
        module_name="",
    )


def extract_identifier_prefix(source_text: str, cursor_position: int) -> str:
    """Return identifier prefix immediately before the cursor."""

    safe_position = max(0, min(cursor_position, len(source_text)))
    match = _IDENTIFIER_PREFIX_PATTERN.search(source_text[:safe_position])
    if match is None:
        return ""
    return match.group(0)


def context_matches_prefix(label: str, prefix: str) -> bool:
    """Return whether ``label`` should remain in a prefix-filtered result."""

    if not prefix:
        return True
    return label.lower().startswith(prefix.lower())


def _context(
    *,
    language: str,
    file_path: str,
    project_root: str | None,
    source_text: str,
    cursor_position: int,
    buffer_revision: int | None,
    trigger_kind: str,
    trigger_character: str,
    trigger_is_manual: bool,
    min_prefix_chars: int,
    max_results: int,
    syntactic_context: CompletionSyntacticContext,
    prefix: str,
    replacement_start: int,
    base_expression: str,
    module_name: str,
) -> CompletionContext:
    replacement = CompletionReplacementRange(start=max(0, replacement_start), end=cursor_position)
    trusted_runtime_module = _trusted_runtime_module(module_name or base_expression)
    valid_for = CompletionValidFor(
        syntactic_context=syntactic_context,
        replacement_start=replacement.start,
        base_expression=base_expression,
        module_name=module_name,
    )
    fingerprint = _fingerprint(
        language,
        file_path,
        buffer_revision,
        syntactic_context.value,
        str(replacement.start),
        base_expression,
        module_name,
    )
    return CompletionContext(
        language=language,
        file_path=file_path,
        project_root=project_root,
        source_text=source_text,
        cursor_position=cursor_position,
        buffer_revision=buffer_revision,
        trigger_kind=trigger_kind,
        trigger_character=trigger_character,
        trigger_is_manual=trigger_is_manual,
        min_prefix_chars=min_prefix_chars,
        max_results=max_results,
        syntactic_context=syntactic_context,
        prefix=prefix,
        replacement_range=replacement,
        valid_for=valid_for,
        fingerprint=fingerprint,
        base_expression=base_expression,
        module_name=module_name,
        trusted_runtime_module=trusted_runtime_module,
    )


def _current_line_prefix(prefix_text: str) -> str:
    line_start = prefix_text.rfind("\n") + 1
    return prefix_text[line_start:]


def _is_likely_string_or_comment(line_prefix: str) -> bool:
    comment_index = line_prefix.find("#")
    single_quotes = line_prefix.count("'") - line_prefix.count("\\'")
    double_quotes = line_prefix.count('"') - line_prefix.count('\\"')
    return comment_index >= 0 or single_quotes % 2 == 1 or double_quotes % 2 == 1


def _trusted_runtime_module(module_name: str) -> str:
    if not module_name:
        return ""
    root = module_name.split(".")[0]
    if root in _TRUSTED_RUNTIME_ROOTS:
        return module_name
    return ""


def _fingerprint(*parts: object) -> str:
    raw = "\0".join("" if part is None else str(part) for part in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()
