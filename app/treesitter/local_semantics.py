"""Locals coloring: which identifiers resolve to a local definition.

A full build walks the whole tree. After an edit, only the statements the edit
touched are rebuilt (``_refresh_local_tokens``). What survives between builds:

* ``_locals_by_row``: the finished local color spans per line. The capture cache
  merges them in, and a viewport requery reads them back by row.
* An outer table: the definitions that live in the module and in classes outside
  any function. A method body resolves names against it. Function-internal
  definitions are rebuilt with their function and are never kept.

A rebuild region is a whole statement: a function with everything in it, a class
header, or any other statement at module or class level. The edit tracking is
conservative. When it cannot tell what moved, it falls back to a full build.
"""

from __future__ import annotations

import re
from bisect import bisect_right
from dataclasses import dataclass
from typing import Any, Protocol, cast

from app.bootstrap.logging_setup import get_subsystem_logger
from app.treesitter.capture_pipeline import _CaptureSpan, _PendingEdit
from app.treesitter.python_tokens import PYTHON_SPECIAL_VARIABLES, SCREAMING_SNAKE_PATTERN
from app.treesitter.ts_api import captures as query_captures, compile_query, matches as query_matches

_LOGGER = get_subsystem_logger("treesitter")

# A rebuild that would touch more than this share of the file is a full build.
_INCREMENTAL_MAX_ROW_SHARE = 0.4

# A class header is these parts and the body. Anything else in the class node,
# such as an error node, makes the whole class one region.
_CLASS_HEADER_PARTS = frozenset({"class", "identifier", "type_parameter", "argument_list", ":", "comment", "block"})


class _LocalSemanticsHost(Protocol):
    TOKEN_STYLES: dict[str, Any]
    _tree: Any | None
    _locals_query: Any | None
    _source_text: str
    _language_key: str


def _host(instance: object) -> _LocalSemanticsHost:
    return cast(_LocalSemanticsHost, instance)


class _OuterDef:
    """A definition in a module or class scope. ``row`` and ``col`` are current."""

    __slots__ = ("name", "token_name", "row", "col", "scope_row")

    def __init__(self, name: str, token_name: str, row: int, col: int, scope_row: int = -1) -> None:
        self.name = name
        self.token_name = token_name
        self.row = row
        self.col = col
        # The row of the class that owns it, or -1 for the module. Only a dropped
        # definition keeps it current, so a move between scopes is noticed.
        self.scope_row = scope_row


class _OuterScope:
    """The module, or a class that is not inside a function."""

    __slots__ = ("row", "col", "defs")

    def __init__(self, row: int = 0, col: int = 0) -> None:
        self.row = row
        self.col = col
        self.defs: dict[str, list[_OuterDef]] = {}


@dataclass
class _RegionScope:
    start: tuple[int, int]
    end: tuple[int, int]
    parent: int
    is_class: bool
    outer: _OuterScope | None = None


@dataclass
class _Region:
    first: int
    last: int
    chain: list[_OuterScope]
    keep_class_at: tuple[int, int] | None = None


_ERROR_QUERIES: dict[int, Any] = {}


class _LocalsFallback(Exception):
    """The incremental pass cannot be trusted. Build everything."""


def _row_sig(spans: list[_CaptureSpan] | None) -> tuple[Any, ...]:
    if not spans:
        return ()
    return tuple(sorted((span.start_col, span.end_col, span.token_name) for span in spans))


def _end_row(node: Any) -> int:
    end = node.end_point
    start_row = node.start_point[0]
    if end[1] == 0 and end[0] > start_row:
        return int(end[0]) - 1
    return int(end[0])


class TreeSitterLocalSemanticsMixin:
    # ---- state ---------------------------------------------------------

    def _reset_local_state(self) -> None:
        self._locals_by_row: dict[int, list[_CaptureSpan]] = {}
        self._lc_module: _OuterScope | None = None
        self._lc_classes: list[_OuterScope] = []
        self._lc_dirty: list[tuple[int, int]] = []
        self._lc_ghosts: list[_OuterDef] = []
        self._lc_ready = False
        self._lc_force_full = False

    def _incremental_locals_supported(self) -> bool:
        return _host(self)._language_key == "python"

    # ---- edit tracking -------------------------------------------------

    def _locals_add_dirty(self, first_row: int, last_row: int) -> None:
        if not self._lc_ready or not self._incremental_locals_supported():
            return
        self._lc_dirty = self._merge_line_ranges([*self._lc_dirty, (first_row, max(first_row, last_row))])

    def _locals_note_edit(self, edit: _PendingEdit) -> None:
        """Map the dirty rows and the outer table through one edit."""
        if not self._lc_ready or self._lc_force_full or not self._incremental_locals_supported():
            return
        start_row, start_col = int(edit.start_point[0]), int(edit.start_point[1])
        old_row, old_col = int(edit.old_end_point[0]), int(edit.old_end_point[1])
        new_row = int(edit.new_end_point[0])
        new_col = int(edit.new_end_point[1])
        delta = new_row - old_row
        mapped: list[tuple[int, int]] = []
        for first, last in self._lc_dirty:
            if last < start_row:
                mapped.append((first, last))
            elif first > old_row:
                mapped.append((first + delta, last + delta))
            else:
                upper = last + delta if last > old_row else new_row
                mapped.append((min(first, start_row), max(new_row, upper)))
        mapped.append((start_row, new_row))
        self._lc_dirty = self._merge_line_ranges(mapped)
        if delta == 0 and start_row == old_row:
            # No line moves. The definitions on this row go with the row when its
            # statement is rebuilt. Only a class keyword that the edit replaced
            # loses its identity.
            for scope in self._lc_classes:
                if scope.row == start_row and start_col <= scope.col < old_col:
                    self._lc_force_full = True
            return
        survivors: list[_OuterScope] = []
        for scope in self._lc_classes:
            position = (scope.row, scope.col)
            if position < (start_row, start_col):
                survivors.append(scope)
            elif position >= (old_row, old_col):
                self._shift_outer_position(scope, old_row, old_col, new_row, new_col)
                survivors.append(scope)
            else:
                self._lc_force_full = True
                return
        module = self._lc_module
        for scope in ([module] if module is not None else []) + survivors:
            owner_row = -1 if scope is module else scope.row
            for name, definitions in list(scope.defs.items()):
                kept: list[_OuterDef] = []
                for definition in definitions:
                    position = (definition.row, definition.col)
                    if position < (start_row, start_col):
                        kept.append(definition)
                    elif position >= (old_row, old_col):
                        self._shift_outer_position(definition, old_row, old_col, new_row, new_col)
                        kept.append(definition)
                    else:
                        definition.scope_row = owner_row
                        self._lc_ghosts.append(definition)
                if len(kept) != len(definitions):
                    if kept:
                        scope.defs[name] = kept
                    else:
                        del scope.defs[name]
        for ghost in self._lc_ghosts:
            if (ghost.row, ghost.col) >= (old_row, old_col):
                self._shift_outer_position(ghost, old_row, old_col, new_row, new_col)
            if ghost.scope_row > old_row:
                ghost.scope_row += new_row - old_row

    @staticmethod
    def _shift_outer_position(item: Any, old_row: int, old_col: int, new_row: int, new_col: int) -> None:
        if item.row == old_row:
            item.col = item.col - old_col + new_col
        item.row += new_row - old_row

    # ---- full build ----------------------------------------------------

    def _rebuild_local_tokens(self) -> None:
        """Build every local span from the tree."""
        self._reset_local_state()
        host = _host(self)
        if host._tree is None or host._locals_query is None:
            return
        lines = host._source_text.split("\n")
        module = _OuterScope()
        self._lc_module = module
        region = _Region(first=0, last=max(0, len(lines) - 1), chain=[module])
        try:
            rows = self._rebuild_local_region(root=host._tree.root_node, region=region, lines=lines)
        except _LocalsFallback:
            self._reset_local_state()
            return
        self._locals_by_row = rows
        self._lc_ghosts = []
        self._lc_ready = True
        if self._incremental_locals_supported():
            self._lc_dirty = self._error_row_ranges(host._tree.root_node)

    # ---- incremental pass ----------------------------------------------

    def _refresh_local_tokens(self) -> set[int]:
        """Bring the local spans up to date. Returns the rows whose spans changed."""
        host = _host(self)
        if host._tree is None or host._locals_query is None:
            return set()
        if not self._lc_ready or self._lc_force_full or not self._incremental_locals_supported():
            return self._full_local_refresh()
        if not self._lc_dirty and not self._lc_ghosts:
            return set()
        # The rows are replaced, never edited, so this keeps the lines the capture
        # cache was last built from, even if the attempt below stops halfway.
        before = dict(self._locals_by_row)
        try:
            return self._incremental_local_refresh()
        except _LocalsFallback:
            return self._full_local_refresh(before)
        except Exception:  # pragma: no cover - defensive path
            _LOGGER.warning("Incremental locals refresh failed. Rebuilding.", exc_info=True)
            return self._full_local_refresh(before)

    def _full_local_refresh(self, before: dict[int, list[_CaptureSpan]] | None = None) -> set[int]:
        old = self._locals_by_row if before is None else before
        self._rebuild_local_tokens()
        changed: set[int] = set()
        for row in set(old) | set(self._locals_by_row):
            if _row_sig(old.get(row)) != _row_sig(self._locals_by_row.get(row)):
                changed.add(row)
        return changed

    def _incremental_local_refresh(self) -> set[int]:
        tree = _host(self)._tree
        assert tree is not None
        root = tree.root_node
        lines = _host(self)._source_text.split("\n")
        line_count = len(lines)
        dirty = self._merge_line_ranges(
            [
                (max(0, first), min(line_count - 1, last))
                for first, last in self._lc_dirty
                if first < line_count
            ]
        )
        budget = line_count * _INCREMENTAL_MAX_ROW_SHARE
        if sum(last - first + 1 for first, last in dirty) > budget:
            raise _LocalsFallback()
        regions = self._plan_local_regions(root, dirty)
        changed: set[int] = set()
        added: list[_OuterDef] = []
        self._apply_local_regions(root, regions, lines, changed, added)
        ripple = self._ripple_rows(added, lines)
        if ripple:
            done = [(region.first, region.last) for region in regions]
            pending = [(row, row) for row in ripple if not any(a <= row <= b for a, b in done)]
            if pending:
                merged = self._merge_line_ranges(pending)
                if sum(last - first + 1 for first, last in merged) > budget:
                    raise _LocalsFallback()
                self._apply_local_regions(root, self._plan_local_regions(root, merged), lines, changed, None)
        self._lc_ghosts = []
        # Lines inside a syntax error stay dirty. An incremental parse can recover
        # from an error differently from one edit to the next without saying so.
        self._lc_dirty = self._error_row_ranges(root)
        return changed

    def _error_row_ranges(self, root: Any) -> list[tuple[int, int]]:
        if not getattr(root, "has_error", False):
            return []
        language = getattr(self, "_language", None)
        if language is None:
            return []
        query = _ERROR_QUERIES.get(id(language))
        if query is None:
            try:
                query = compile_query(language, "(ERROR) @error")
            except Exception:  # pragma: no cover - defensive path
                return []
            _ERROR_QUERIES[id(language)] = query
        try:
            found = query_captures(query, root)
        except Exception:  # pragma: no cover - defensive path
            return []
        nodes = [node for group in found.values() for node in group] if isinstance(found, dict) else [n for n, _ in found]
        return self._merge_line_ranges([(int(node.start_point[0]), _end_row(node)) for node in nodes])

    def _apply_local_regions(
        self,
        root: Any,
        regions: list[_Region],
        lines: list[str],
        changed: set[int],
        added: list[_OuterDef] | None,
    ) -> None:
        for region in regions:
            new_rows = self._rebuild_local_region(root=root, region=region, lines=lines, added=added)
            for row in range(region.first, region.last + 1):
                old_spans = self._locals_by_row.get(row)
                new_spans = new_rows.get(row)
                if _row_sig(old_spans) != _row_sig(new_spans):
                    changed.add(row)
                if new_spans:
                    self._locals_by_row[row] = new_spans
                else:
                    self._locals_by_row.pop(row, None)

    def _ripple_rows(self, added: list[_OuterDef], lines: list[str]) -> list[int]:
        """Rows that mention a name whose outer definition came or went.

        A definition dropped and rebuilt on the same row with the same meaning
        changes nothing for anyone else.
        """
        ghosts = list(self._lc_ghosts)
        unmatched: list[_OuterDef] = []
        for definition in added:
            for index, ghost in enumerate(ghosts):
                if (
                    ghost.name == definition.name
                    and ghost.token_name == definition.token_name
                    and ghost.row == definition.row
                    and ghost.scope_row == definition.scope_row
                ):
                    del ghosts[index]
                    break
            else:
                unmatched.append(definition)
        names = {item.name for item in unmatched} | {item.name for item in ghosts}
        if not names:
            return []
        pattern = re.compile(r"(?<!\w)(?:%s)(?!\w)" % "|".join(re.escape(name) for name in sorted(names)))
        return [row for row, line in enumerate(lines) if pattern.search(line)]

    # ---- planning ------------------------------------------------------

    def _plan_local_regions(self, root: Any, dirty: list[tuple[int, int]]) -> list[_Region]:
        module = self._lc_module
        if module is None or root.type != "module":
            raise _LocalsFallback()
        regions: list[_Region] = []
        self._plan_container(root, 0, max(0, int(root.end_point[0])), [module], dirty, regions)
        return self._merge_regions(regions)

    @staticmethod
    def _merge_regions(regions: list[_Region]) -> list[_Region]:
        """One region for statements that share or touch lines, when they share a chain.

        Two statements can share a line, and a run of comments is a run of
        statements. One query serves the run.
        """
        merged: list[_Region] = []
        for region in sorted(regions, key=lambda item: (item.first, item.last)):
            previous = merged[-1] if merged else None
            if previous is None or region.first > previous.last + 1:
                merged.append(region)
                continue
            same_chain = len(previous.chain) == len(region.chain) and all(
                left is right for left, right in zip(previous.chain, region.chain)
            )
            plain = previous.keep_class_at is None and region.keep_class_at is None
            if same_chain and plain:
                previous.last = max(previous.last, region.last)
            elif region.first <= previous.last:
                raise _LocalsFallback()
            else:
                merged.append(region)
        return merged

    def _plan_container(
        self,
        container: Any,
        first_row: int,
        last_row: int,
        chain: list[_OuterScope],
        dirty: list[tuple[int, int]],
        regions: list[_Region],
    ) -> None:
        pieces = [
            (max(first, first_row), min(last, last_row))
            for first, last in dirty
            if last >= first_row and first <= last_row
        ]
        if not pieces:
            return
        covered: list[tuple[int, int]] = []
        children = list(container.children)
        spans = [(int(child.start_point[0]), _end_row(child)) for child in children]
        chosen = {
            index
            for index, (start, end) in enumerate(spans)
            if any(not (end < first or start > last) for first, last in pieces)
        }
        # A statement that shares a line with a chosen one is rebuilt with it.
        # Rebuilding half of a shared line would drop the other half's colors.
        direct = set(chosen)
        pending = list(chosen)
        while pending:
            index = pending.pop()
            for other in (index - 1, index + 1):
                if 0 <= other < len(spans) and other not in chosen:
                    if not (spans[index][1] < spans[other][0] or spans[index][0] > spans[other][1]):
                        chosen.add(other)
                        pending.append(other)
        for index in sorted(chosen):
            child = children[index]
            start, end = spans[index]
            inner = child
            if child.type == "decorated_definition":
                definition = child.child_by_field_name("definition")
                if definition is not None:
                    inner = definition
            if inner.type == "class_definition" and index in direct:
                body = inner.child_by_field_name("body")
                header_end = int(body.start_point[0]) - 1 if body is not None else -1
                scope = self._find_class_scope(int(inner.start_point[0]), int(inner.start_point[1]))
                plain_header = all(part.type in _CLASS_HEADER_PARTS for part in inner.children)
                body_below = body is not None and int(body.start_point[0]) > int(inner.start_point[0])
                if body_below and scope is not None and plain_header:
                    if any(not (header_end < first or start > last) for first, last in pieces):
                        regions.append(
                            _Region(
                                first=start,
                                last=header_end,
                                chain=list(chain),
                                keep_class_at=(scope.row, scope.col),
                            )
                        )
                    covered.append((start, header_end))
                    body_first = int(body.start_point[0])
                    self._plan_container(body, body_first, end, [scope, *chain], dirty, regions)
                    covered.append((body_first, end))
                    continue
            regions.append(_Region(first=start, last=end, chain=list(chain)))
            covered.append((start, end))
        for first, last in self._subtract_rows(pieces, covered):
            regions.append(_Region(first=first, last=last, chain=list(chain)))
        regions.sort(key=lambda region: region.first)

    @staticmethod
    def _subtract_rows(
        pieces: list[tuple[int, int]],
        covered: list[tuple[int, int]],
    ) -> list[tuple[int, int]]:
        remaining: list[tuple[int, int]] = []
        ordered = sorted(covered)
        for first, last in pieces:
            cursor = first
            for c_first, c_last in ordered:
                if c_last < cursor or c_first > last:
                    continue
                if c_first > cursor:
                    remaining.append((cursor, c_first - 1))
                cursor = max(cursor, c_last + 1)
                if cursor > last:
                    break
            if cursor <= last:
                remaining.append((cursor, last))
        return remaining

    def _find_class_scope(self, row: int, col: int) -> _OuterScope | None:
        for scope in self._lc_classes:
            if scope.row == row and scope.col == col:
                return scope
        return None

    # ---- one region ----------------------------------------------------

    def _drop_outer_rows(self, first_row: int, last_row: int, keep: tuple[int, int] | None) -> None:
        """Forget the outer definitions on these rows. They return as ghosts."""
        survivors: list[_OuterScope] = []
        for scope in self._lc_classes:
            if first_row <= scope.row <= last_row and (scope.row, scope.col) != keep:
                for definitions in scope.defs.values():
                    for item in definitions:
                        item.scope_row = scope.row
                        self._lc_ghosts.append(item)
                scope.defs = {}
            else:
                survivors.append(scope)
        self._lc_classes = survivors
        module = self._lc_module
        for scope in ([module] if module is not None else []) + survivors:
            owner_row = -1 if scope is module else scope.row
            for name, definitions in list(scope.defs.items()):
                kept = [item for item in definitions if not (first_row <= item.row <= last_row)]
                if len(kept) == len(definitions):
                    continue
                for item in definitions:
                    if first_row <= item.row <= last_row:
                        item.scope_row = owner_row
                        self._lc_ghosts.append(item)
                if kept:
                    scope.defs[name] = kept
                else:
                    del scope.defs[name]

    def _rebuild_local_region(
        self,
        *,
        root: Any,
        region: _Region,
        lines: list[str],
        added: list[_OuterDef] | None = None,
    ) -> dict[int, list[_CaptureSpan]]:
        """Rebuild the locals of whole statements. Returns the new spans by row."""
        host = _host(self)
        query = host._locals_query
        first, last = region.first, region.last
        self._drop_outer_rows(first, last, region.keep_class_at)
        if query is None or not region.chain:
            raise _LocalsFallback()
        try:
            matches = query_matches(query, root, start_point=(first, 0), end_point=(last + 1, 0))
        except Exception:  # pragma: no cover - defensive path
            _LOGGER.warning("Failed to evaluate locals query for %s.", host._language_key, exc_info=True)
            raise _LocalsFallback()

        limit_end = (last + 1, 0)
        scope_nodes: list[tuple[tuple[int, int], tuple[int, int], bool]] = []
        pending_defs: list[tuple[Any, str, bool, bool]] = []
        pending_refs: list[Any] = []
        pattern_info: dict[int, tuple[str, bool, bool]] = {}
        for pattern_index, capture_map in matches:
            info = pattern_info.get(pattern_index)
            if info is None:
                settings = self._query_settings(query, pattern_index)
                info = (
                    str(settings.get("local.role", "semantic_variable")),
                    str(settings.get("local.color_definition", "")).lower() == "true",
                    str(settings.get("local.scope_lift", "")).lower() == "true",
                )
                pattern_info[pattern_index] = info
            role, color_definition, scope_lift = info
            for scope_node in capture_map.get("local.scope", []):
                if scope_node.parent is None:
                    continue
                start = scope_node.start_point
                end = scope_node.end_point
                if start[0] < first or end > limit_end:
                    continue
                scope_nodes.append(
                    ((int(start[0]), int(start[1])), (int(end[0]), int(end[1])), scope_node.type == "class_definition")
                )
            for definition_node in capture_map.get("local.definition", []):
                if first <= definition_node.start_point[0] <= last:
                    pending_defs.append((definition_node, role, color_definition, scope_lift))
            for reference_node in capture_map.get("local.reference", []):
                if first <= reference_node.start_point[0] <= last:
                    pending_refs.append(reference_node)

        records = self._build_region_scopes(scope_nodes, first, last)
        starts = [record.start for record in records]
        local_defs: list[dict[str, list[tuple[tuple[int, int], str]]]] = [{} for _ in records]
        spans_by_row: dict[int, dict[tuple[int, int], str]] = {}
        registered: list[tuple[_OuterScope, _OuterDef]] = []
        seen_defs: set[tuple[tuple[int, int], str]] = set()
        byte_to_char = self._byte_col_to_char_col
        line_count = len(lines)

        def identifier(node: Any) -> tuple[str, int, int, tuple[int, int], tuple[int, int]] | None:
            start = node.start_point
            end = node.end_point
            row = int(start[0])
            if row != end[0] or row >= line_count:
                return None
            line = lines[row]
            if line.isascii():
                start_col, end_col = min(int(start[1]), len(line)), min(int(end[1]), len(line))
            else:
                start_col, end_col = byte_to_char(line, int(start[1])), byte_to_char(line, int(end[1]))
            if end_col <= start_col:
                return None
            return (
                line[start_col:end_col],
                start_col,
                end_col,
                (row, int(start[1])),
                (row, int(end[1])),
            )

        def put_span(row: int, start_col: int, end_col: int, token_name: str) -> None:
            spans_by_row.setdefault(row, {}).setdefault((start_col, end_col), token_name)

        colored: list[tuple[int, int, int, str]] = []
        for definition_node, role, color_definition, scope_lift in pending_defs:
            found = identifier(definition_node)
            if found is None:
                continue
            name, start_col, end_col, start_point, end_point = found
            if (start_point, name) in seen_defs:
                continue
            seen_defs.add((start_point, name))
            scope_index = self._innermost_scope(records, starts, start_point, end_point)
            if scope_lift:
                scope_index = records[scope_index].parent
            token_name = self._normalize_local_role(name=name, role=role)
            local_defs[scope_index].setdefault(name, []).append((start_point, token_name))
            if color_definition:
                colored.append((start_point[0], start_col, end_col, token_name))
            outer_target = region.chain[0] if scope_index == 0 else records[scope_index].outer
            if outer_target is not None:
                owner_row = -1 if outer_target is self._lc_module else outer_target.row
                registered.append(
                    (outer_target, _OuterDef(name, token_name, start_point[0], start_point[1], owner_row))
                )
        for definitions_by_name in local_defs:
            for definitions in definitions_by_name.values():
                if len(definitions) > 1:
                    definitions.sort()
        for row, start_col, end_col, token_name in colored:
            put_span(row, start_col, end_col, token_name)

        chain = region.chain
        for reference_node in pending_refs:
            found = identifier(reference_node)
            if found is None:
                continue
            name, start_col, end_col, start_point, end_point = found
            scope_index = self._innermost_scope(records, starts, start_point, end_point)
            token_name = self._resolve_local_name(records, local_defs, chain, scope_index, name, start_point)
            if token_name is not None:
                put_span(start_point[0], start_col, end_col, token_name)

        for outer_scope, outer_def in registered:
            definitions_here = outer_scope.defs.setdefault(outer_def.name, [])
            definitions_here.append(outer_def)
            if len(definitions_here) > 1:
                definitions_here.sort(key=lambda item: (item.row, item.col))
            if added is not None:
                added.append(outer_def)
        for record in records:
            if record.outer is not None:
                self._lc_classes.append(record.outer)

        rows: dict[int, list[_CaptureSpan]] = {}
        for row, by_range in spans_by_row.items():
            rows[row] = [
                _CaptureSpan(
                    token_name=token_name,
                    start_col=start_col,
                    end_col=end_col,
                    capture_name=token_name,
                    origin="locals",
                )
                for (start_col, end_col), token_name in sorted(by_range.items())
            ]
        return rows

    @staticmethod
    def _build_region_scopes(
        scope_nodes: list[tuple[tuple[int, int], tuple[int, int], bool]],
        first: int,
        last: int,
    ) -> list[_RegionScope]:
        records = [_RegionScope(start=(first, 0), end=(last + 1, 0), parent=0, is_class=False)]
        ordered = sorted(set(scope_nodes), key=lambda item: (item[0], (-item[1][0], -item[1][1])))
        stack = [0]
        seen: set[tuple[tuple[int, int], tuple[int, int]]] = set()
        for start, end, is_class in ordered:
            if (start, end) in seen:
                continue
            seen.add((start, end))
            while len(stack) > 1 and records[stack[-1]].end < end:
                stack.pop()
            parent = stack[-1]
            record = _RegionScope(start=start, end=end, parent=parent, is_class=is_class)
            if is_class and (parent == 0 or records[parent].outer is not None):
                record.outer = _OuterScope(row=start[0], col=start[1])
            records.append(record)
            stack.append(len(records) - 1)
        return records

    @staticmethod
    def _innermost_scope(
        records: list[_RegionScope],
        starts: list[tuple[int, int]],
        start_point: tuple[int, int],
        end_point: tuple[int, int],
    ) -> int:
        index = bisect_right(starts, start_point) - 1
        while index > 0:
            record = records[index]
            if record.start <= start_point and end_point <= record.end:
                return index
            index = record.parent
        return 0

    @staticmethod
    def _resolve_local_name(
        records: list[_RegionScope],
        local_defs: list[dict[str, list[tuple[tuple[int, int], str]]]],
        chain: list[_OuterScope],
        scope_index: int,
        name: str,
        reference_point: tuple[int, int],
    ) -> str | None:
        index = scope_index
        while True:
            definitions = local_defs[index].get(name)
            if definitions:
                for position, token_name in reversed(definitions):
                    if position < reference_point:
                        return token_name
            if index == 0:
                break
            index = records[index].parent
        for scope in chain:
            outer_definitions = scope.defs.get(name)
            if outer_definitions:
                for item in reversed(outer_definitions):
                    if (item.row, item.col) < reference_point:
                        return item.token_name
        return None

    @staticmethod
    def _query_settings(query: Any, pattern_index: int) -> dict[str, str]:
        try:
            settings = query.pattern_settings(pattern_index)
        except Exception:
            return {}
        if not isinstance(settings, dict):
            return {}
        return {str(key): str(value) for key, value in settings.items()}

    def _normalize_local_role(self, *, name: str, role: str) -> str:
        if name in PYTHON_SPECIAL_VARIABLES:
            return "builtin"
        normalized = role if role in _host(self).TOKEN_STYLES else "semantic_variable"
        if normalized == "semantic_variable" and SCREAMING_SNAKE_PATTERN.match(name):
            return "semantic_constant"
        return normalized

    def _add_local_semantic_spans(
        self,
        *,
        lines: list[str],
        merged_ranges: list[tuple[int, int]],
        spans_by_line: dict[int, list[_CaptureSpan]],
        seen_by_line: dict[int, dict[tuple[int, int], int]],
    ) -> None:
        del lines
        by_row = self._locals_by_row
        if not by_row:
            return
        for first, last in merged_ranges:
            if last - first > len(by_row):
                rows = sorted(row for row in by_row if first <= row <= last)
            else:
                rows = [row for row in range(first, last + 1) if row in by_row]
            for row in rows:
                for span in by_row[row]:
                    self._append_capture_span(
                        spans_by_line=spans_by_line,
                        seen_by_line=seen_by_line,
                        line_number=row,
                        span=span,
                    )
