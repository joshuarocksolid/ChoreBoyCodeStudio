"""Editor-side external process supervision for runner execution."""

from __future__ import annotations

from dataclasses import dataclass
import os
import signal
import subprocess
import threading
from typing import IO, Callable, Literal, Mapping, Sequence

from app.core.errors import RunLifecycleError

ProcessState = Literal["idle", "running", "stopping", "exited"]


@dataclass(frozen=True)
class ProcessEvent:
    """Event emitted by process supervisor during run lifecycle."""

    event_type: Literal["output", "exit", "state", "debug"]
    stream: Literal["stdout", "stderr"] | None = None
    text: str | None = None
    return_code: int | None = None
    state: ProcessState | None = None
    terminated_by_user: bool = False
    payload: object | None = None


@dataclass
class _ProcessResources:
    reader_threads: list[threading.Thread]
    reader_streams: list[IO[str]]
    cleaned: bool = False


class ProcessSupervisor:
    """Launches and supervises one external process at a time."""

    def __init__(self, on_event: Callable[[ProcessEvent], None] | None = None) -> None:
        self._on_event = on_event
        self._process: subprocess.Popen[str] | None = None
        self._state: ProcessState = "idle"
        self._terminated_by_user = False
        self._lock = threading.RLock()
        self._process_resources: dict[int, _ProcessResources] = {}
        self._waiter_thread: threading.Thread | None = None

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
        state_event: ProcessEvent
        with self._lock:
            if self._process is not None and self._process.poll() is None:
                raise RunLifecycleError("Runner process is already active.")

            try:
                process = subprocess.Popen(
                    command,
                    cwd=cwd,
                    env=None if env is None else dict(env),
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                    start_new_session=True,
                )
            except OSError as exc:
                raise RunLifecycleError(f"Failed to launch runner process: {exc}") from exc

            self._process = process
            self._terminated_by_user = False
            self._process_resources[process.pid] = _ProcessResources(reader_threads=[], reader_streams=[])
            self._state = "running"
            state_event = self._build_state_event("running")
            process_id = process.pid

        self._emit_event(state_event)
        self._start_reader_threads(process=process)
        self._start_waiter_thread(process)
        return process_id

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

        state_event: ProcessEvent
        with self._lock:
            self._terminated_by_user = True
            self._state = "stopping"
            state_event = self._build_state_event("stopping")

        self._emit_event(state_event)

        try:
            pgid = os.getpgid(process.pid)
        except OSError:
            pgid = None

        if pgid is not None:
            try:
                os.killpg(pgid, signal.SIGTERM)
            except OSError:
                try:
                    process.terminate()
                except OSError:
                    pass
        else:
            try:
                process.terminate()
            except OSError:
                pass
        try:
            process.wait(timeout=terminate_timeout_seconds)
        except subprocess.TimeoutExpired:
            if pgid is not None:
                try:
                    os.killpg(pgid, signal.SIGKILL)
                except OSError:
                    try:
                        process.kill()
                    except OSError:
                        pass
            else:
                try:
                    process.kill()
                except OSError:
                    pass
            process.wait()
        self._cleanup_process_resources(process)
        self._join_waiter_thread()
        return process.returncode

    def pause(self) -> bool:
        """Request an interrupt signal for active process."""
        with self._lock:
            process = self._process
        if process is None or process.poll() is not None:
            return False
        try:
            process.send_signal(signal.SIGINT)
        except OSError as exc:
            raise RunLifecycleError(f"Failed to pause runner process: {exc}") from exc
        return True

    def send_input(self, text: str) -> None:
        """Send text to active process stdin."""
        with self._lock:
            process = self._process
        if process is None or process.poll() is not None:
            raise RunLifecycleError("Cannot send input because runner process is not active.")
        if process.stdin is None:
            raise RunLifecycleError("Runner process stdin is unavailable.")
        try:
            process.stdin.write(text)
            process.stdin.flush()
        except OSError as exc:
            raise RunLifecycleError(f"Failed to write to runner stdin: {exc}") from exc

    def _start_reader_threads(self, *, process: subprocess.Popen[str]) -> None:
        with self._lock:
            resources = self._process_resources.get(process.pid)
        if resources is None:
            return
        reader_threads: list[threading.Thread] = []
        reader_streams: list[IO[str]] = []
        for stream_name, stream in (("stdout", process.stdout), ("stderr", process.stderr)):
            if stream is None:
                continue
            reader_streams.append(stream)
            reader = threading.Thread(
                target=self._read_stream,
                args=(stream_name, stream),
                daemon=True,
            )
            reader_threads.append(reader)
            reader.start()
        with self._lock:
            current_resources = self._process_resources.get(process.pid)
            if current_resources is None:
                self._join_reader_threads(reader_threads, timeout_seconds=0.2)
                self._close_streams(reader_streams)
                return
            current_resources.reader_threads.extend(reader_threads)
            current_resources.reader_streams.extend(reader_streams)

    def _start_waiter_thread(self, process: subprocess.Popen[str]) -> None:
        self._waiter_thread = threading.Thread(target=self._wait_for_exit, args=(process,), daemon=True)
        self._waiter_thread.start()

    def _read_stream(self, stream_name: Literal["stdout", "stderr"], stream: IO[str]) -> None:
        try:
            for chunk in iter(stream.readline, ""):
                with self._lock:
                    terminated_by_user = self._terminated_by_user
                self._emit_event(
                    ProcessEvent(
                        event_type="output",
                        stream=stream_name,
                        text=chunk,
                        terminated_by_user=terminated_by_user,
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
            if self._process is not process:
                return
            self._process = None
            self._waiter_thread = None
            self._state = "exited"
            terminated_by_user = self._terminated_by_user
            state_event = self._build_state_event("exited")
            exit_event = ProcessEvent(
                event_type="exit",
                return_code=return_code,
                terminated_by_user=terminated_by_user,
            )
        self._emit_event(state_event)
        self._emit_event(exit_event)

    def _build_state_event(self, state: ProcessState) -> ProcessEvent:
        return ProcessEvent(
            event_type="state",
            state=state,
            terminated_by_user=self._terminated_by_user,
        )

    def _cleanup_process_resources(self, process: subprocess.Popen[str]) -> None:
        with self._lock:
            resources = self._process_resources.get(process.pid)
            if resources is None or resources.cleaned:
                return
            resources.cleaned = True
            reader_threads = list(resources.reader_threads)
            reader_streams = list(resources.reader_streams)

        self._join_reader_threads(reader_threads, timeout_seconds=0.2)

        self._close_streams([*reader_streams, process.stdout, process.stderr, process.stdin])

        self._join_reader_threads(reader_threads, timeout_seconds=0.2)
        with self._lock:
            self._process_resources.pop(process.pid, None)

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

    def _emit_event(self, event: ProcessEvent) -> None:
        if self._on_event is None:
            return
        try:
            self._on_event(event)
        except Exception:
            # Event callbacks are observer side-effects; never crash supervisor threads.
            return

    @staticmethod
    def _close_streams(streams: Sequence[IO[str] | None]) -> None:
        seen_stream_ids: set[int] = set()
        for stream in streams:
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
