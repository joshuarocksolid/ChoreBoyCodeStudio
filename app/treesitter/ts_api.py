"""Tree-sitter calls that differ between the 0.23 and 0.25+ bindings.

0.23 has ``Parser.set_language``, ``Language.query``, and ``Query.captures``.
0.25+ takes the language in the ``Parser`` constructor, builds a ``Query``
directly, and runs captures through ``QueryCursor``. ``capture_pipeline``
accepts either a ``dict[str, list[node]]`` or ``(node, name)`` pairs.
"""

from __future__ import annotations

from typing import Any


def make_parser(language: Any) -> Any:
    """Return a parser bound to ``language``."""
    import tree_sitter

    parser_type = tree_sitter.Parser
    if hasattr(parser_type, "set_language"):
        parser = parser_type()
        parser.set_language(language)
        return parser
    try:
        return parser_type(language)
    except TypeError:
        parser = parser_type()
        parser.language = language
        return parser


def compile_query(language: Any, source: str) -> Any:
    """Compile ``source`` against ``language``."""
    query_method = getattr(language, "query", None)
    if callable(query_method):
        return query_method(source)
    from tree_sitter import Query

    return Query(language, source)


def captures(
    query: Any,
    node: Any,
    *,
    start_point: tuple[int, int] | None = None,
    end_point: tuple[int, int] | None = None,
) -> Any:
    """Return captures for ``node``.

    Pass a point range through when the binding supports it. Bindings that
    ignore range arguments return every capture, and
    ``capture_pipeline._normalize_captures`` drops the ones outside the lines.
    """
    capture_method = getattr(query, "captures", None)
    if callable(capture_method):
        if start_point is None or end_point is None:
            return capture_method(node)
        try:
            return capture_method(node, start_point=start_point, end_point=end_point)
        except TypeError:
            return capture_method(node)
    from tree_sitter import QueryCursor

    cursor = QueryCursor(query)
    if start_point is not None and end_point is not None:
        cursor.set_point_range(start_point, end_point)
    return cursor.captures(node)


def matches(
    query: Any,
    node: Any,
    *,
    start_point: tuple[int, int] | None = None,
    end_point: tuple[int, int] | None = None,
) -> Any:
    """Return pattern matches for ``node``, limited to the point range when given."""
    match_method = getattr(query, "matches", None)
    if callable(match_method):
        if start_point is None or end_point is None:
            return match_method(node)
        try:
            return match_method(node, start_point=start_point, end_point=end_point)
        except TypeError:
            return match_method(node)
    from tree_sitter import QueryCursor

    cursor = QueryCursor(query)
    if start_point is not None and end_point is not None:
        cursor.set_point_range(start_point, end_point)
    return cursor.matches(node)
