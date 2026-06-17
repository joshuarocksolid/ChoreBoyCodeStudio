"""Shared search pattern options and regex compiler for inline and project search."""

from __future__ import annotations

import re
from dataclasses import dataclass

DEFAULT_MAX_REGEX_QUERY_CHARS = 512


@dataclass(frozen=True)
class SearchPatternOptions:
    """Unified find/search option toggles for inline and project search."""

    case_sensitive: bool = False
    whole_word: bool = False
    regex: bool = False
    include_globs: list[str] | None = None
    exclude_globs: list[str] | None = None


FindOptions = SearchPatternOptions
SearchOptions = SearchPatternOptions


def compile_search_pattern(
    query: str,
    options: SearchPatternOptions,
    *,
    max_regex_chars: int = DEFAULT_MAX_REGEX_QUERY_CHARS,
) -> re.Pattern[str] | None:
    """Compile a search regex from query text and option toggles."""
    flags = 0 if options.case_sensitive else re.IGNORECASE
    if options.regex and len(query) > max_regex_chars:
        return None
    if options.regex:
        try:
            return re.compile(query, flags)
        except re.error:
            return None
    escaped = re.escape(query)
    if options.whole_word:
        escaped = rf"\b{escaped}\b"
    return re.compile(escaped, flags)
