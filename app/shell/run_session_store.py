"""Single source of truth for active shell run-session metadata."""

from __future__ import annotations

from dataclasses import dataclass

from app.run.run_service import RunSession


@dataclass(frozen=True)
class ActiveRunSession:
    """Immutable snapshot of the active run session visible to shell UI."""

    mode: str
    run_id: str
    log_path: str
    entry_file: str = ""


class RunSessionStore:
    """Holds active session metadata (mode, run_id, log path) for shell consumers."""

    def __init__(self) -> None:
        self._active: ActiveRunSession | None = None

    @property
    def active_session(self) -> ActiveRunSession | None:
        return self._active

    @property
    def active_session_mode(self) -> str | None:
        if self._active is None:
            return None
        return self._active.mode

    @property
    def log_path(self) -> str | None:
        if self._active is None:
            return None
        return self._active.log_path

    def start_from_session(self, session: RunSession) -> None:
        """Record metadata for a newly started run session."""
        self._active = ActiveRunSession(
            mode=session.mode,
            run_id=session.run_id,
            log_path=session.log_file_path,
            entry_file=session.entry_file,
        )

    def clear(self) -> None:
        """Clear active session metadata after stop/exit/shutdown."""
        self._active = None
