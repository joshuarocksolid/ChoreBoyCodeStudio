"""Project-wide text search helpers."""

from __future__ import annotations

import fnmatch
import logging
from dataclasses import dataclass
from pathlib import Path
import threading
from typing import Callable

from app.editors.search_service import SearchOptions, compile_search_pattern
from app.project.file_excludes import EffectiveExcludes, merge_search_exclude_globs
from app.project.file_inventory import iter_text_file_paths


@dataclass(frozen=True)
class SearchMatch:
    """One project search match."""

    relative_path: str
    absolute_path: str
    line_number: int
    line_text: str
    column: int = 0
    match_length: int = 0


_LOGGER = logging.getLogger(__name__)
MAX_SEARCH_LINE_CHARS = 20_000


def _matches_glob_list(relative_path: str, globs: list[str]) -> bool:
    for pattern in globs:
        pattern = pattern.strip()
        if not pattern:
            continue
        if fnmatch.fnmatch(relative_path, pattern):
            return True
        name = relative_path.rsplit("/", 1)[-1]
        if fnmatch.fnmatch(name, pattern):
            return True
    return False


def _should_include_file(relative_path: str, options: SearchOptions) -> bool:
    if options.include_globs:
        if not _matches_glob_list(relative_path, options.include_globs):
            return False
    return True


def find_in_files(
    project_root: str | Path,
    query: str,
    *,
    max_results: int = 200,
    cancel_event: threading.Event | None = None,
    options: SearchOptions | None = None,
    exclude_patterns: list[str] | None = None,
) -> list[SearchMatch]:
    """Search text files under project root for query."""
    if not query.strip():
        return []

    opts = options or SearchOptions()
    pattern = compile_search_pattern(query, opts)
    if pattern is None:
        return []

    root = Path(project_root).expanduser().resolve()
    results: list[SearchMatch] = []
    effective = EffectiveExcludes.merge(exclude_patterns or ())
    effective = merge_search_exclude_globs(effective, opts.exclude_globs)

    for file_path, rel_path in iter_text_file_paths(
        root,
        exclude_patterns=effective.as_list(),
    ):
        if cancel_event is not None and cancel_event.is_set():
            return results
        if len(results) >= max_results:
            return results
        if not _should_include_file(rel_path, opts):
            continue

        try:
            with file_path.open("r", encoding="utf-8") as handle:
                for line_index, line in enumerate(handle, start=1):
                    if cancel_event is not None and cancel_event.is_set():
                        return results
                    if len(line) > MAX_SEARCH_LINE_CHARS:
                        continue
                    for m in pattern.finditer(line):
                        results.append(
                            SearchMatch(
                                relative_path=rel_path,
                                absolute_path=str(file_path.resolve()),
                                line_number=line_index,
                                line_text=line.rstrip("\n"),
                                column=m.start(),
                                match_length=m.end() - m.start(),
                            )
                        )
                        if len(results) >= max_results:
                            return results
        except (UnicodeDecodeError, OSError):
            continue
    return results


def _apply_match_replacements(
    lines: list[str],
    line_matches: list[SearchMatch],
    replacement: str,
) -> int:
    """Replace explicit match spans on one file's line list. Returns replacement count."""
    by_line: dict[int, list[SearchMatch]] = {}
    for match in line_matches:
        by_line.setdefault(match.line_number, []).append(match)

    replaced = 0
    for line_number, matches_on_line in by_line.items():
        line_index = line_number - 1
        if line_index < 0 or line_index >= len(lines):
            continue

        line = lines[line_index]
        line_body = line.rstrip("\n\r")
        newline_suffix = line[len(line_body) :]

        for match in sorted(matches_on_line, key=lambda item: item.column, reverse=True):
            column = match.column
            length = match.match_length
            if length <= 0 or column < 0 or column + length > len(line_body):
                continue
            line_body = line_body[:column] + replacement + line_body[column + length :]
            replaced += 1

        lines[line_index] = line_body + newline_suffix
    return replaced


def replace_in_files(
    matches: list[SearchMatch],
    replacement: str,
    query: str,
    *,
    options: SearchOptions | None = None,
) -> int:
    """Replace matched text at ``SearchMatch`` spans only. Returns replacements made."""
    if not matches:
        return 0

    opts = options or SearchOptions()
    if compile_search_pattern(query, opts) is None:
        return 0

    files_to_process: dict[str, list[SearchMatch]] = {}
    for match in matches:
        files_to_process.setdefault(match.absolute_path, []).append(match)

    total_replaced = 0
    for file_path, file_matches in files_to_process.items():
        try:
            path = Path(file_path)
            content = path.read_text(encoding="utf-8")
            lines = content.splitlines(keepends=True)
            replaced = _apply_match_replacements(lines, file_matches, replacement)
            if replaced == 0:
                continue
            new_content = "".join(lines)
            if new_content != content:
                path.write_text(new_content, encoding="utf-8")
                total_replaced += replaced
        except (OSError, UnicodeDecodeError):
            continue
    return total_replaced


class SearchWorker:
    """Background search worker with cancellation support."""

    def __init__(
        self,
        *,
        project_root: str | Path,
        query: str,
        max_results: int = 200,
        options: SearchOptions | None = None,
        search_generation: int = 0,
        on_results: Callable[[list[SearchMatch], str, int], None] | None = None,
        on_done: Callable[[], None] | None = None,
        exclude_patterns: list[str] | None = None,
    ) -> None:
        self._project_root = str(Path(project_root).expanduser().resolve())
        self._query = query
        self._max_results = max_results
        self._options = options
        self._search_generation = search_generation
        self._on_results = on_results
        self._on_done = on_done
        self._exclude_patterns = exclude_patterns
        self._cancel_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def cancel(self) -> None:
        self._cancel_event.set()

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _run(self) -> None:
        try:
            if self._cancel_event.is_set():
                return
            matches = find_in_files(
                self._project_root,
                self._query,
                max_results=self._max_results,
                cancel_event=self._cancel_event,
                options=self._options,
                exclude_patterns=self._exclude_patterns,
            )
            if not self._cancel_event.is_set() and self._on_results is not None:
                try:
                    self._on_results(matches, self._query, self._search_generation)
                except Exception:
                    _LOGGER.exception("Search worker on_results callback failed.")
        except Exception:
            _LOGGER.exception("Search worker failed while collecting results.")
        finally:
            if self._on_done is not None:
                try:
                    self._on_done()
                except Exception:
                    _LOGGER.exception("Search worker on_done callback failed.")
