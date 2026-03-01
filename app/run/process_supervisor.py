"""Editor-side external process supervision for runner execution."""

from __future__ import annotations

from dataclasses import dataclass
import subprocess
import threading
from typing import Callable, Literal, Mapping
from typing import TextIO

from app.core.errors import RunLifecycleError

ProcessState = Literal["idle", "running", "stopping", "exited"]


@dataclass(frozen=True)
class ProcessEvent:
    """Event emitted by process supervisor during run lifecycle."""

    event_type: Literal["output", "exit", "state"]
    stream: Literal["stdout", "stderr"] | None = None
    text: str | None = None
    return_code: int | None = None
    state: ProcessState | None = None
    terminated_by_user: bool = False


class ProcessSupervisor:
    """Launches and supervises one external process at a time."""

    def __init__(self, on_event: Callable[[ProcessEvent], None] | None = None) -> None:
        self._on_event = on_event
        self._process: subprocess.Popen[str] | None = None
        self._state: ProcessState = "idle"
        self._terminated_by_user = False
        self._lock = threading.RLock()
        self._reader_threads: list[threading.Thread] = []
        self._reader_streams: list[TextIO] = []
        self._waiter_thread: threading.Thread | None = None
        self._resources_cleaned = True

    @property
    def state(self) -> ProcessState:
        with self._lock:
            return self._state

    @property
    def process_id(self) -> int | None:
        with self._lock:
            return None if self._process is None else self._process.pid

    def is_running(self) -> bool:
        with self._lock:
            return self._process is not None and self._process.poll() is None

    def start(self, command: list[str], *, cwd: str, env: Mapping[str, str] | None = None) -> int:
        """Start an external process and begin streaming output events."""
        with self._lock:
            if self._process is not None and self._process.poll() is None:
                raise RunLifecycleError("Runner process is already active.")

            try:
                process = subprocess.Popen(
                    command,
                    cwd=cwd,
                    env=None if env is None else dict(env),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                )
            except OSError as exc:
                raise RunLifecycleError(f"Failed to launch runner process: {exc}") from exc

            self._process = process
            self._terminated_by_user = False
            self._resources_cleaned = False
            self._set_state("running")
            self._start_reader_threads(process)
            self._start_waiter_thread(process)
            return process.pid

    def stop(self, *, terminate_timeout_seconds: float = 2.0) -> int | None:
        """Stop active process gracefully, then force kill if needed."""
        with self._lock:
            process = self._process
        if process is None:
            return None

        if process.poll() is not None:
            self._cleanup_process_resources(process)
            self._join_waiter_thread()
            return process.returncode

        with self._lock:
            self._terminated_by_user = True
            self._set_state("stopping")

        process.terminate()
        try:
            process.wait(timeout=terminate_timeout_seconds)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        self._cleanup_process_resources(process)
        self._join_waiter_thread()
        return process.returncode

    def _start_reader_threads(self, process: subprocess.Popen[str]) -> None:
        self._reader_threads = []
        self._reader_streams = []
        for stream_name, stream in (("stdout", process.stdout), ("stderr", process.stderr)):
            if stream is None:
                continue
            self._reader_streams.append(stream)
            reader = threading.Thread(
                target=self._read_stream,
                args=(stream_name, stream),
                daemon=True,
            )
            self._reader_threads.append(reader)
            reader.start()

    def _start_waiter_thread(self, process: subprocess.Popen[str]) -> None:
        self._waiter_thread = threading.Thread(target=self._wait_for_exit, args=(process,), daemon=True)
        self._waiter_thread.start()

    def _read_stream(self, stream_name: Literal["stdout", "stderr"], stream: TextIO) -> None:
        try:
            for chunk in iter(stream.readline, ""):
                self._emit_event(
                    ProcessEvent(
                        event_type="output",
                        stream=stream_name,
                        text=chunk,
                        terminated_by_user=self._terminated_by_user,
                    )
                )
        except (OSError, ValueError):
            # Stream can be force-closed during shutdown/stop cleanup.
            return
        finally:
            try:
                stream.close()
            except OSError:
                pass

    def _wait_for_exit(self, process: subprocess.Popen[str]) -> None:
        return_code = process.wait()
        self._cleanup_process_resources(process)
        with self._lock:
            self._process = None
            self._waiter_thread = None
            self._set_state("exited")
            terminated_by_user = self._terminated_by_user

        self._emit_event(
            ProcessEvent(
                event_type="exit",
                return_code=return_code,
                terminated_by_user=terminated_by_user,
            )
        )

    def _cleanup_process_resources(self, process: subprocess.Popen[str]) -> None:
        with self._lock:
            if self._resources_cleaned:
                return
            self._resources_cleaned = True
            reader_threads = list(self._reader_threads)
            reader_streams = list(self._reader_streams)
            self._reader_threads = []
            self._reader_streams = []

        self._join_reader_threads(reader_threads, timeout_seconds=0.2)

        seen_stream_ids: set[int] = set()
        for stream in [*reader_streams, process.stdout, process.stderr]:
            if stream is None:
                continue
            stream_id = id(stream)
            if stream_id in seen_stream_ids:
                continue
            seen_stream_ids.add(stream_id)
            try:
                stream.close()
            except OSError:
                pass

        self._join_reader_threads(reader_threads, timeout_seconds=0.2)

    def _join_reader_threads(self, threads: list[threading.Thread], *, timeout_seconds: float) -> None:
        current_thread = threading.current_thread()
        for reader in threads:
            if reader is current_thread:
                continue
            reader.join(timeout=timeout_seconds)

    def _join_waiter_thread(self) -> None:
        with self._lock:
            waiter_thread = self._waiter_thread
        if waiter_thread is None:
            return
        if waiter_thread is threading.current_thread():
            return
        waiter_thread.join(timeout=0.5)

    def _set_state(self, state: ProcessState) -> None:
        self._state = state
        self._emit_event(ProcessEvent(event_type="state", state=state, terminated_by_user=self._terminated_by_user))

    def _emit_event(self, event: ProcessEvent) -> None:
        if self._on_event is None:
            return
        self._on_event(event)
