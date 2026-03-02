"""Unit tests for per-project editor session persistence."""

from __future__ import annotations

import pytest

from app.core import constants
from app.shell.session_persistence import (
    SessionFileState,
    SessionState,
    load_session_file,
    parse_session_state,
    save_session_file,
    serialize_session_state,
)

pytestmark = pytest.mark.unit


def test_parse_session_state_round_trip_preserves_valid_payload(tmp_path) -> None:  # type: ignore[no-untyped-def]
    file_one = tmp_path / "main.py"
    file_one.write_text("print('one')\n", encoding="utf-8")
    file_two = tmp_path / "utils.py"
    file_two.write_text("print('two')\n", encoding="utf-8")
    state = SessionState(
        open_files=(
            SessionFileState(
                file_path=str(file_one.resolve()),
                cursor_line=3,
                cursor_column=8,
                scroll_position=42,
                breakpoints=(3, 9),
            ),
            SessionFileState(
                file_path=str(file_two.resolve()),
                cursor_line=1,
                cursor_column=1,
                scroll_position=0,
                breakpoints=(),
            ),
        ),
        active_file_path=str(file_two.resolve()),
    )

    payload = serialize_session_state(state)
    parsed = parse_session_state(payload)

    assert parsed == state


def test_parse_session_state_skips_invalid_missing_and_duplicate_entries(tmp_path) -> None:  # type: ignore[no-untyped-def]
    existing_file = tmp_path / "existing.py"
    existing_file.write_text("value = 1\n", encoding="utf-8")
    missing_file = tmp_path / "missing.py"
    payload = {
        "open_files": [
            {"file_path": str(existing_file.resolve()), "cursor_line": 0, "cursor_column": -5, "breakpoints": [4, 4, -2, "x"]},
            {"file_path": str(missing_file.resolve()), "cursor_line": 7},
            {"file_path": "relative.py", "cursor_line": 2},
            {"file_path": str(existing_file.resolve()), "cursor_line": 9},
            {"cursor_line": 2},
            "bad-shape",
        ],
        "active_file_path": str(missing_file.resolve()),
    }

    parsed = parse_session_state(payload)

    assert len(parsed.open_files) == 1
    only_file_state = parsed.open_files[0]
    assert only_file_state.file_path == str(existing_file.resolve())
    assert only_file_state.cursor_line == 1
    assert only_file_state.cursor_column == 1
    assert only_file_state.scroll_position == 0
    assert only_file_state.breakpoints == (4,)
    assert parsed.active_file_path is None


def test_load_session_file_returns_none_when_file_absent(tmp_path) -> None:  # type: ignore[no-untyped-def]
    project_root = tmp_path / "project"
    (project_root / constants.PROJECT_META_DIRNAME).mkdir(parents=True)

    assert load_session_file(str(project_root.resolve())) is None


def test_load_session_file_returns_defaults_for_corrupt_json(tmp_path) -> None:  # type: ignore[no-untyped-def]
    project_root = tmp_path / "project"
    meta_dir = project_root / constants.PROJECT_META_DIRNAME
    meta_dir.mkdir(parents=True)
    session_path = meta_dir / constants.PROJECT_SESSION_FILENAME
    session_path.write_text("{bad json", encoding="utf-8")

    loaded = load_session_file(str(project_root.resolve()))

    assert loaded == SessionState()


def test_save_and_load_session_file_round_trip(tmp_path) -> None:  # type: ignore[no-untyped-def]
    project_root = tmp_path / "project"
    (project_root / constants.PROJECT_META_DIRNAME).mkdir(parents=True)
    source_file = project_root / "app.py"
    source_file.write_text("print('hello')\n", encoding="utf-8")
    session_state = SessionState(
        open_files=(
            SessionFileState(
                file_path=str(source_file.resolve()),
                cursor_line=5,
                cursor_column=2,
                scroll_position=30,
                breakpoints=(2, 5),
            ),
        ),
        active_file_path=str(source_file.resolve()),
    )

    session_path = save_session_file(str(project_root.resolve()), session_state)
    loaded = load_session_file(str(project_root.resolve()))

    assert session_path == (project_root / constants.PROJECT_META_DIRNAME / constants.PROJECT_SESSION_FILENAME).resolve()
    assert loaded == session_state
