"""Unit tests for Python console history persistence helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.shell.python_console_history import load_python_console_history, save_python_console_history

pytestmark = pytest.mark.unit


def test_load_python_console_history_returns_empty_for_missing_file(tmp_path: Path) -> None:
    history = load_python_console_history(tmp_path / "missing.json", max_entries=5)
    assert history == []


def test_save_and_load_python_console_history_round_trips_entries(tmp_path: Path) -> None:
    history_path = tmp_path / "python_console_history.json"
    save_python_console_history(history_path, ["a = 1", "print(a)"], max_entries=10)

    loaded = load_python_console_history(history_path, max_entries=10)

    assert loaded == ["a = 1", "print(a)"]


def test_save_python_console_history_trims_to_max_entries(tmp_path: Path) -> None:
    history_path = tmp_path / "python_console_history.json"
    save_python_console_history(history_path, ["1", "2", "3"], max_entries=2)

    loaded = load_python_console_history(history_path, max_entries=5)

    assert loaded == ["2", "3"]
