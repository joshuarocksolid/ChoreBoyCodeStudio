"""Project-wide text search helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SearchMatch:
    """One project search match."""

    relative_path: str
    absolute_path: str
    line_number: int
    line_text: str


def find_in_files(project_root: str | Path, query: str, *, max_results: int = 200) -> list[SearchMatch]:
    """Search text files under project root for query substring."""
    if not query.strip():
        return []

    root = Path(project_root).expanduser().resolve()
    results: list[SearchMatch] = []

    for file_path in sorted(root.rglob("*")):
        if len(results) >= max_results:
            break
        if not file_path.is_file():
            continue
        if ".cbcs" in file_path.parts:
            continue
        try:
            lines = file_path.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            continue

        for line_index, line in enumerate(lines, start=1):
            if query not in line:
                continue
            results.append(
                SearchMatch(
                    relative_path=file_path.relative_to(root).as_posix(),
                    absolute_path=str(file_path.resolve()),
                    line_number=line_index,
                    line_text=line,
                )
            )
            if len(results) >= max_results:
                break
    return results
