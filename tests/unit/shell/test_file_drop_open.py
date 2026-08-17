"""Unit tests for local file paths extracted from drop mime data."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.shell.file_drop_open import local_file_paths_from_mime_data

pytestmark = pytest.mark.unit


def test_local_file_paths_from_mime_data_keeps_existing_files(tmp_path: Path) -> None:
    existing = tmp_path / "probe.py"
    existing.write_text("print(1)\n", encoding="utf-8")
    missing = tmp_path / "gone.py"
    folder = tmp_path / "subdir"
    folder.mkdir()
    mime = SimpleNamespace(
        hasUrls=lambda: True,
        urls=lambda: [
            SimpleNamespace(isLocalFile=lambda: True, toLocalFile=lambda: str(existing)),
            SimpleNamespace(isLocalFile=lambda: True, toLocalFile=lambda: str(missing)),
            SimpleNamespace(isLocalFile=lambda: True, toLocalFile=lambda: str(folder)),
            SimpleNamespace(isLocalFile=lambda: False, toLocalFile=lambda: "https://example.com/x.py"),
        ],
    )

    assert local_file_paths_from_mime_data(mime) == [str(existing)]


def test_local_file_paths_from_mime_data_empty_without_urls() -> None:
    mime = SimpleNamespace(hasUrls=lambda: False, urls=lambda: [])

    assert local_file_paths_from_mime_data(mime) == []
    assert local_file_paths_from_mime_data(None) == []
