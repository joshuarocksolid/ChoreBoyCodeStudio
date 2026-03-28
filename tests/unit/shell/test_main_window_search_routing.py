"""Unit tests for search result navigation routing in MainWindow."""

from __future__ import annotations

from typing import Any, cast

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.shell.main_window import MainWindow

pytestmark = pytest.mark.unit


def test_handle_search_open_file_at_line_uses_permanent_open() -> None:
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    calls: list[tuple[str, int, bool]] = []
    window_any._open_file_at_line = (
        lambda file_path, line_number, preview=False: calls.append((file_path, line_number, preview))
    )

    MainWindow._handle_search_open_file_at_line(window, "/tmp/project/src/main.py", 27)

    assert calls == [("/tmp/project/src/main.py", 27, False)]


def test_handle_search_preview_file_at_line_uses_preview_open() -> None:
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    calls: list[tuple[str, int, bool]] = []
    window_any._open_file_at_line = (
        lambda file_path, line_number, preview=False: calls.append((file_path, line_number, preview))
    )

    MainWindow._handle_search_preview_file_at_line(window, "/tmp/project/src/main.py", 11)

    assert calls == [("/tmp/project/src/main.py", 11, True)]
