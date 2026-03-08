"""Project-wide text search helpers."""

from __future__ import annotations

import fnmatch
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
import threading
from typing import Callable

from app.project.file_excludes import should_exclude_relative_path


@dataclass(frozen=True)
class SearchMatch:
    """One project search match."""

    relative_path: str
    absolute_path: str
    line_number: int
    line_text: str
    column: int = 0
    match_length: int = 0


@dataclass(frozen=True)
class SearchOptions:
    """Options for project-wide search."""

    case_sensitive: bool = False
    whole_word: bool = False
    regex: bool = False
    include_globs: list[str] | None = None
    exclude_globs: list[str] | None = None


_STRUCTURAL_SKIP_DIRS = {"cbcs"}
_LOGGER = logging.getLogger(__name__)


def _compile_pattern(query: str, options: SearchOptions) -> re.Pattern[str] | None:
    flags = 0 if options.case_sensitive else re.IGNORECASE
    if options.regex:
        try:
            return re.compile(query, flags)
        except re.error:
            return None
    escaped = re.escape(query)
    if options.whole_word:
        escaped = rf"\b{escaped}\b"
    return re.compile(escaped, flags)


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
    if options.exclude_globs:
        if _matches_glob_list(relative_path, options.exclude_globs):
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
    pattern = _compile_pattern(query, opts)
    if pattern is None:
        return []

    root = Path(project_root).expanduser().resolve()
    results: list[SearchMatch] = []
    _active_excludes = exclude_patterns or []

    for current_dir, dir_names, file_names in os.walk(root, topdown=True, followlinks=False):
        if cancel_event is not None and cancel_event.is_set():
            break
        if len(results) >= max_results:
            break

        current_path = Path(current_dir)
        pruned_dir_names: list[str] = []
        for directory_name in sorted(dir_names):
            if directory_name in _STRUCTURAL_SKIP_DIRS:
                continue
            directory_path = current_path / directory_name
            relative_directory_path = directory_path.relative_to(root).as_posix()
            if _active_excludes and should_exclude_relative_path(
                relative_directory_path,
                _active_excludes,
                is_directory=True,
            ):
                continue
            pruned_dir_names.append(directory_name)
        dir_names[:] = pruned_dir_names

        for file_name in sorted(file_names):
            if cancel_event is not None and cancel_event.is_set():
                return results
            if len(results) >= max_results:
                return results

            file_path = current_path / file_name
            rel_path = file_path.relative_to(root).as_posix()
            if _active_excludes and should_exclude_relative_path(rel_path, _active_excludes, is_directory=False):
                continue
            if not _should_include_file(rel_path, opts):
                continue

            try:
                with file_path.open("r", encoding="utf-8") as handle:
                    for line_index, line in enumerate(handle, start=1):
                        if cancel_event is not None and cancel_event.is_set():
                            return results
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


def replace_in_files(
    matches: list[SearchMatch],
    replacement: str,
    query: str,
    *,
    options: SearchOptions | None = None,
) -> int:
    """Replace matched text in files. Returns total replacements made."""
    opts = options or SearchOptions()
    pattern = _compile_pattern(query, opts)
    if pattern is None:
        return 0

    files_to_process: dict[str, list[SearchMatch]] = {}
    for match in matches:
        files_to_process.setdefault(match.absolute_path, []).append(match)

    total_replaced = 0
    for file_path, file_matches in files_to_process.items():
        try:
            path = Path(file_path)
            content = path.read_text(encoding="utf-8")
            new_content = pattern.sub(replacement, content)
            if new_content != content:
                path.write_text(new_content, encoding="utf-8")
                total_replaced += sum(1 for _ in pattern.finditer(content))
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
        on_results: Callable[[list[SearchMatch], str], None] | None = None,
        on_done: Callable[[], None] | None = None,
        exclude_patterns: list[str] | None = None,
    ) -> None:
        self._project_root = str(Path(project_root).expanduser().resolve())
        self._query = query
        self._max_results = max_results
        self._options = options
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
                    self._on_results(matches, self._query)
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
