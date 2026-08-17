"""Extract local file paths from a drag-and-drop mime payload."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def local_file_paths_from_mime_data(mime_data: Any) -> list[str]:
    """Return existing local file paths from ``QMimeData``-like urls."""
    if mime_data is None or not mime_data.hasUrls():
        return []
    paths: list[str] = []
    for url in mime_data.urls():
        if not url.isLocalFile():
            continue
        local_path = url.toLocalFile()
        if not local_path:
            continue
        candidate = Path(local_path)
        if candidate.is_file():
            paths.append(str(candidate))
    return paths
