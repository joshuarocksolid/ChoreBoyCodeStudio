"""Shared fixtures for MainWindow shell integration tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator

import pytest

from app.shell.main_window import MainWindow
from testing.main_window_shutdown import shutdown_main_window_for_test
from testing.main_window_test_helpers import (
    ensure_shell_qapplication,
    prepare_main_window_for_test,
    wait_for,
)

__all__ = ["ensure_shell_qapplication", "prepare_main_window_for_test", "wait_for"]


@pytest.fixture
def shell_qapp(monkeypatch: pytest.MonkeyPatch) -> Any:
    return ensure_shell_qapplication(monkeypatch)


@pytest.fixture
def main_window_for_test(
    shell_qapp: Any,
    tmp_path: Path,
) -> Iterator[MainWindow]:
    """Construct a patched MainWindow and tear it down after the test."""
    window = MainWindow(state_root=str(tmp_path.resolve()))
    prepare_main_window_for_test(window, app=shell_qapp)
    try:
        yield window
    finally:
        shutdown_main_window_for_test(window, shell_qapp)
