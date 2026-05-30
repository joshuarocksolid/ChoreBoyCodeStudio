"""Background worker for loading project filesystem entries off the UI thread."""

from __future__ import annotations

import threading
from typing import Callable

from app.core.errors import AppValidationError
from app.core.models import LoadedProject
from app.project.project_service import open_project_and_track_recent

OpenProjectTask = Callable[[], LoadedProject]
OpenProjectSuccess = Callable[[LoadedProject], None]
OpenProjectError = Callable[[str], None]


class ProjectOpenWorker:
    """Runs ``open_project_and_track_recent`` on a background thread."""

    def __init__(
        self,
        *,
        project_root: str,
        state_root: str | None,
        exclude_patterns: list[str] | None,
        on_success: OpenProjectSuccess | None = None,
        on_error: OpenProjectError | None = None,
        should_commit: Callable[[], bool] | None = None,
    ) -> None:
        self._project_root = project_root
        self._state_root = state_root
        self._exclude_patterns = exclude_patterns
        self._on_success = on_success
        self._on_error = on_error
        self._should_commit = should_commit
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

    def _can_commit(self) -> bool:
        if self._cancel_event.is_set():
            return False
        if self._should_commit is not None and not self._should_commit():
            return False
        return True

    def _run(self) -> None:
        try:
            if not self._can_commit():
                return
            loaded_project = open_project_and_track_recent(
                self._project_root,
                state_root=self._state_root,
                exclude_patterns=self._exclude_patterns,
            )
            if not self._can_commit():
                return
            if self._on_success is not None:
                self._on_success(loaded_project)
        except (AppValidationError, ValueError) as exc:
            if self._on_error is not None:
                self._on_error(str(exc))
        except Exception as exc:  # pragma: no cover - defensive thread guard
            if self._on_error is not None:
                self._on_error(f"Unexpected error: {exc}")
