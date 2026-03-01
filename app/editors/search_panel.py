"""Project-wide text search helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import threading
from typing import Callable


@dataclass(frozen=True)
class SearchMatch:
    """One project search match."""

    relative_path: str
    absolute_path: str
    line_number: int
    line_text: str


def find_in_files(
    project_root: str | Path,
    query: str,
    *,
    max_results: int = 200,
    cancel_event: threading.Event | None = None,
) -> list[SearchMatch]:
    """Search text files under project root for query substring."""
    if not query.strip():
        return []

    root = Path(project_root).expanduser().resolve()
    results: list[SearchMatch] = []

    for file_path in sorted(root.rglob("*")):
        if cancel_event is not None and cancel_event.is_set():
            break
        if len(results) >= max_results:
            break
        if not file_path.is_file():
            continue
        if ".cbcs" in file_path.parts or "__pycache__" in file_path.parts:
            continue
        try:
            with file_path.open("r", encoding="utf-8") as handle:
                for line_index, line in enumerate(handle, start=1):
                    if cancel_event is not None and cancel_event.is_set():
                        return results
                    if query not in line:
                        continue
                    results.append(
                        SearchMatch(
                            relative_path=file_path.relative_to(root).as_posix(),
                            absolute_path=str(file_path.resolve()),
                            line_number=line_index,
                            line_text=line.rstrip("\n"),
                        )
                    )
                    if len(results) >= max_results:
                        return results
        except (UnicodeDecodeError, OSError):
            continue
    return results


class SearchWorker:
    """Background search worker with cancellation support."""

    def __init__(
        self,
        *,
        project_root: str | Path,
        query: str,
        max_results: int = 200,
        on_results: Callable[[list[SearchMatch], str], None] | None = None,
        on_done: Callable[[], None] | None = None,
    ) -> None:
        self._project_root = str(Path(project_root).expanduser().resolve())
        self._query = query
        self._max_results = max_results
        self._on_results = on_results
        self._on_done = on_done
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
        if self._cancel_event.is_set():
            if self._on_done is not None:
                self._on_done()
            return
        matches = find_in_files(
            self._project_root,
            self._query,
            max_results=self._max_results,
            cancel_event=self._cancel_event,
        )
        if not self._cancel_event.is_set() and self._on_results is not None:
            self._on_results(matches, self._query)
        if self._on_done is not None:
            self._on_done()
