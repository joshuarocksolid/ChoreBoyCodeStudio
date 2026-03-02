"""Per-project editor session persistence helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from app.bootstrap.paths import PathInput, ensure_directory, project_cbcs_dir
from app.core import constants
from app.persistence.settings_store import load_json_object, save_json_object

SESSION_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class SessionFileState:
    """Serializable editor state for one open file."""

    file_path: str
    cursor_line: int = 1
    cursor_column: int = 1
    scroll_position: int = 0
    breakpoints: tuple[int, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "cursor_line": self.cursor_line,
            "cursor_column": self.cursor_column,
            "scroll_position": self.scroll_position,
            "breakpoints": list(self.breakpoints),
        }


@dataclass(frozen=True)
class SessionState:
    """Serializable open-tab session state for a project."""

    open_files: tuple[SessionFileState, ...] = ()
    active_file_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SESSION_SCHEMA_VERSION,
            "open_files": [file_state.to_dict() for file_state in self.open_files],
            "active_file_path": self.active_file_path,
        }


def serialize_session_state(session_state: SessionState) -> dict[str, Any]:
    """Serialize SessionState into a JSON-compatible payload."""
    return session_state.to_dict()


def parse_session_state(payload: Mapping[str, Any]) -> SessionState:
    """Parse persisted payload into SessionState with safe defaults."""
    raw_open_files = payload.get("open_files")
    if not isinstance(raw_open_files, list):
        return SessionState()

    open_files: list[SessionFileState] = []
    seen_paths: set[str] = set()
    for raw_file_state in raw_open_files:
        file_state = _parse_session_file_state(raw_file_state)
        if file_state is None:
            continue
        if file_state.file_path in seen_paths:
            continue
        seen_paths.add(file_state.file_path)
        open_files.append(file_state)

    active_file_path = payload.get("active_file_path")
    if not isinstance(active_file_path, str) or active_file_path not in seen_paths:
        active_file_path = None
    return SessionState(open_files=tuple(open_files), active_file_path=active_file_path)


def save_session_file(project_root: PathInput, session_state: SessionState) -> Path:
    """Persist project session state to <project>/.cbcs/session.json."""
    path = _project_session_path(project_root)
    ensure_directory(path.parent)
    return save_json_object(path, serialize_session_state(session_state))


def load_session_file(project_root: PathInput) -> SessionState | None:
    """Load persisted project session state; return None when absent."""
    path = _project_session_path(project_root)
    if not path.is_file():
        return None
    payload = load_json_object(path, default={})
    return parse_session_state(payload)


def _project_session_path(project_root: PathInput) -> Path:
    return project_cbcs_dir(project_root) / constants.PROJECT_SESSION_FILENAME


def _parse_session_file_state(raw_file_state: Any) -> SessionFileState | None:
    if not isinstance(raw_file_state, Mapping):
        return None
    raw_file_path = raw_file_state.get("file_path")
    file_path = _parse_existing_file_path(raw_file_path)
    if file_path is None:
        return None
    cursor_line = _parse_positive_int(raw_file_state.get("cursor_line"), default=1)
    cursor_column = _parse_positive_int(raw_file_state.get("cursor_column"), default=1)
    scroll_position = _parse_non_negative_int(raw_file_state.get("scroll_position"), default=0)
    breakpoints = _parse_breakpoints(raw_file_state.get("breakpoints"))
    return SessionFileState(
        file_path=file_path,
        cursor_line=cursor_line,
        cursor_column=cursor_column,
        scroll_position=scroll_position,
        breakpoints=breakpoints,
    )


def _parse_existing_file_path(raw_value: Any) -> str | None:
    if not isinstance(raw_value, str) or not raw_value.strip():
        return None
    candidate = Path(raw_value).expanduser()
    if not candidate.is_absolute():
        return None
    resolved = candidate.resolve()
    if not resolved.is_file():
        return None
    return str(resolved)


def _parse_positive_int(raw_value: Any, *, default: int) -> int:
    if not isinstance(raw_value, int):
        return default
    return max(1, raw_value)


def _parse_non_negative_int(raw_value: Any, *, default: int) -> int:
    if not isinstance(raw_value, int):
        return default
    return max(0, raw_value)


def _parse_breakpoints(raw_value: Any) -> tuple[int, ...]:
    if not isinstance(raw_value, list):
        return ()
    parsed: list[int] = []
    seen: set[int] = set()
    for entry in raw_value:
        if not isinstance(entry, int) or entry < 1:
            continue
        if entry in seen:
            continue
        seen.add(entry)
        parsed.append(entry)
    return tuple(parsed)
