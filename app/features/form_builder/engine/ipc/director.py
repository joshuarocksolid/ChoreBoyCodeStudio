"""Preview child lifecycle, with no Qt and no process.

The editor pool applies the effects. Tests drive the same object with a fake
clock. One child is shared by every open view. A hang, an unexpected exit, or
three protocol violations is a crash. Crashes back off 0s, 1s, 4s, 15s inside
a 120s window, then the circuit opens until ``retry``.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, replace
from typing import Deque, Dict, List, Optional, Sequence, Tuple, Union
import uuid

from app.features.form_builder.engine.ipc.protocol import (
    PROTOCOL_NAME,
    PROTOCOL_VERSION,
    ChildMessage,
    CloseView,
    CrashReport,
    ErrorReport,
    FrameDecoder,
    Hello,
    HostMessage,
    LoadForm,
    Log,
    NeedSecret,
    NoiseLine,
    Ping,
    ProtocolViolation,
    Ready,
    Response,
    Shutdown,
    UpdateForm,
    ViewClosed,
    encode_frame,
    is_mutation,
)
from app.features.form_builder.engine.ipc.timing import (
    PROTOCOL_VIOLATIONS_BEFORE_RESTART,
    STDERR_TAIL_LINES,
    DirectorConfig,
)

PoolState = str  # "stopped" | "starting" | "ready" | "backoff" | "circuit_open"

Mutation = Union[LoadForm, UpdateForm]


@dataclass(frozen=True)
class SpawnChild:
    pass


@dataclass(frozen=True)
class KillChild:
    pass


@dataclass(frozen=True)
class WriteFrame:
    text: str


@dataclass(frozen=True)
class Deliver:
    message: ChildMessage


@dataclass(frozen=True)
class LogNoise:
    stream: str
    text: str


@dataclass(frozen=True)
class NoteHandshake:
    seconds: float


@dataclass(frozen=True)
class NoteLoad:
    seconds: float


Effect = Union[SpawnChild, KillChild, WriteFrame, Deliver, LogNoise, NoteHandshake, NoteLoad]


@dataclass(frozen=True)
class DirectorStatus:
    state: PoolState
    crashes_in_window: int
    next_restart_in: Optional[float]
    last_error: Optional[str]
    child_alive: bool
    handshake_seconds: Optional[float]
    load_seconds: Optional[float]


@dataclass
class _Sent:
    request_id: str
    deadline: float
    kind: str
    view_id: Optional[str]
    sent_at: float


@dataclass
class _View:
    desired: Optional[LoadForm] = None
    pending: Optional[Mutation] = None
    inflight_id: Optional[str] = None
    inflight: Optional[Mutation] = None
    revision: Optional[int] = None


class PreviewDirector:
    """Decides what the pool should do. It does not spawn or touch a socket."""

    def __init__(self, *, host_pid: int, config: Optional[DirectorConfig] = None) -> None:
        self._config = config or DirectorConfig()
        self._host_pid = host_pid
        self._now = 0.0
        self._state = "stopped"
        self._child_alive = False
        self._saw_ready = False
        self._hello_ok = False
        self._hello_id: Optional[str] = None
        self._mismatch = False
        self._version_mismatch = False
        self._violations = 0
        self._missed_pings = 0
        self._ping_id: Optional[str] = None
        self._ping_sent_at: Optional[float] = None
        self._next_ping_at: Optional[float] = None
        self._spawn_at = 0.0
        self._handshake_deadline: Optional[float] = None
        self._restart_at: Optional[float] = None
        self._stop_deadline: Optional[float] = None
        self._crash_times: List[float] = []
        self._stderr: Deque[str] = deque(maxlen=STDERR_TAIL_LINES)
        self._views: Dict[str, _View] = {}
        self._sent: Dict[str, _Sent] = {}
        self._early: List[HostMessage] = []
        self._decoder = FrameDecoder()
        self._last_error: Optional[str] = None
        self._announced_circuit = False
        self._handshake_seconds: Optional[float] = None
        self._load_seconds: Optional[float] = None
        self._session_token = ""

    @property
    def state(self) -> str:
        return self._state

    def status(self, now: float) -> DirectorStatus:
        self._prune(now)
        next_in = None
        if self._state == "backoff" and self._restart_at is not None:
            next_in = max(0.0, self._restart_at - now)
        public = self._state if self._state in {"stopped", "starting", "ready", "backoff", "circuit_open"} else "stopped"
        return DirectorStatus(
            state=public,
            crashes_in_window=len(self._crash_times),
            next_restart_in=next_in,
            last_error=self._last_error,
            child_alive=self._child_alive,
            handshake_seconds=self._handshake_seconds,
            load_seconds=self._load_seconds,
        )

    def next_wake(self) -> Optional[float]:
        times: List[float] = []
        if self._state == "starting" and self._handshake_deadline is not None:
            times.append(self._handshake_deadline)
        if self._state == "stopping" and self._stop_deadline is not None and self._child_alive:
            times.append(self._stop_deadline)
        if self._state == "backoff" and not self._child_alive and self._restart_at is not None:
            times.append(self._restart_at)
        if self._state == "ready":
            for sent in self._sent.values():
                if sent.kind != "hello":
                    times.append(sent.deadline)
            if self._views and self._next_ping_at is not None:
                times.append(self._next_ping_at)
            if self._ping_id is not None and self._ping_sent_at is not None:
                times.append(self._ping_sent_at + self._config.ping_interval)
        if not times:
            return None
        return min(times)

    def note_form_opened(self, now: float) -> Tuple[Effect, ...]:
        self._now = now
        if self._config.prewarm and self._state == "stopped" and not self._child_alive:
            return tuple(self._begin_start())
        return ()

    def request(self, now: float, message: HostMessage) -> Tuple[Effect, ...]:
        self._now = now
        if isinstance(message, Shutdown):
            return self.shutdown(now)
        if self._state == "circuit_open":
            return tuple(self._refuse_circuit(message))
        if is_mutation(message):
            return tuple(self._mutation(message))  # type: ignore[arg-type]
        if self._state == "ready":
            return tuple(self._send(message))
        if self._state == "stopped":
            self._early.append(message)
            return tuple(self._begin_start())
        if self._state in {"starting", "backoff"}:
            self._early.append(message)
            if self._state == "backoff" and not self._child_alive and self._due_restart():
                return tuple(self._begin_start())
            return ()
        return (self._response(message, ok=False, error="busy", detail=self._last_error),)

    def retry(self, now: float) -> Tuple[Effect, ...]:
        self._now = now
        if self._child_alive:
            return ()
        # A version mismatch exits 3. Spawning the same binary fails the same way.
        if self._version_mismatch:
            return ()
        if self._state == "circuit_open":
            self._crash_times.clear()
            self._announced_circuit = False
            self._last_error = None
            self._state = "stopped"
        if self._state in {"stopped", "backoff"}:
            self._restart_at = None
            return tuple(self._begin_start())
        return ()

    def shutdown(self, now: float) -> Tuple[Effect, ...]:
        self._now = now
        effects: List[Effect] = []
        for sent in list(self._sent.values()):
            if sent.kind != "hello":
                effects.append(
                    Deliver(
                        Response(
                            request_id=sent.request_id,
                            ok=False,
                            error="busy",
                            detail="shutdown",
                        )
                    )
                )
        self._sent.clear()
        self._early.clear()
        self._views.clear()
        self._ping_id = None
        self._next_ping_at = None
        self._restart_at = None
        if not self._child_alive:
            self._state = "stopped"
            self._stop_deadline = None
            return tuple(effects)
        if self._state != "stopping":
            self._state = "stopping"
            frame = Shutdown(request_id=uuid.uuid4().hex)
            effects.append(WriteFrame(encode_frame(frame)))
            self._stop_deadline = now + self._config.shutdown_grace
        return tuple(effects)

    def advance(self, now: float) -> Tuple[Effect, ...]:
        self._now = now
        if self._state == "stopping":
            if self._child_alive and self._stop_deadline is not None and now >= self._stop_deadline:
                self._stop_deadline = None
                return (KillChild(),)
            return ()
        if self._state == "starting" and self._handshake_deadline is not None and now >= self._handshake_deadline:
            return tuple(self._enter_crash(already_dead=False, code=None, reason="handshake timeout"))
        if self._state == "ready":
            expired = [
                sent
                for sent in self._sent.values()
                if sent.kind != "hello" and now >= sent.deadline
            ]
            if expired:
                return tuple(self._enter_crash(already_dead=False, code=None, reason="request timeout"))
            if self._views:
                ping_effects = self._ping_if_due(now)
                if self._state != "ready":
                    return tuple(ping_effects)
                return tuple(ping_effects)
        if self._state == "backoff" and not self._child_alive and self._due_restart():
            return tuple(self._begin_start())
        return ()

    def on_stdout(self, now: float, text: str) -> Tuple[Effect, ...]:
        self._now = now
        effects: List[Effect] = []
        for item in self._decoder.feed(text):
            effects.extend(self._on_item(item))
        return tuple(effects)

    def on_stderr(self, now: float, text: str) -> Tuple[Effect, ...]:
        self._now = now
        for line in text.splitlines():
            cleaned = line[:-1] if line.endswith("\r") else line
            if cleaned:
                self._stderr.append(cleaned)
        return ()

    def on_exit(self, now: float, code: int) -> Tuple[Effect, ...]:
        self._now = now
        self._child_alive = False
        self._ping_id = None
        if self._state == "stopping":
            self._state = "stopped"
            self._stop_deadline = None
            return ()
        if self._mismatch or code == 3:
            self._mismatch = False
            self._version_mismatch = True
            self._state = "circuit_open"
            self._restart_at = None
            self._handshake_deadline = None
            return ()
        effects: List[Effect] = []
        if self._state not in {"backoff", "circuit_open"}:
            if code == 0 and not self._views:
                self._state = "stopped"
                self._handshake_deadline = None
                return ()
            effects.extend(self._enter_crash(already_dead=True, code=code, reason="exit"))
        if self._state == "backoff" and not self._child_alive and self._due_restart():
            effects.extend(self._begin_start())
        return tuple(effects)

    def on_spawn_failed(self, now: float, detail: str) -> Tuple[Effect, ...]:
        self._now = now
        self._child_alive = False
        if self._state == "stopping":
            self._state = "stopped"
            return ()
        return tuple(self._enter_crash(already_dead=True, code=None, reason=detail or "spawn failed"))

    def _refuse_circuit(self, message: HostMessage) -> List[Effect]:
        effects = [self._response(message, ok=False, error="busy", detail="preview circuit open")]
        if not self._announced_circuit:
            self._announced_circuit = True
            self._last_error = "Preview is off after repeated crashes."
            effects.append(
                Deliver(
                    ErrorReport(
                        view_id=None,
                        code="FB605",
                        message=self._last_error,
                        traceback="",
                    )
                )
            )
        return effects

    def _mutation(self, message: Mutation) -> List[Effect]:
        view = self._views.get(message.view_id)
        if view is None:
            view = _View()
            self._views[message.view_id] = view
        if isinstance(message, LoadForm):
            view.desired = message
        effects: List[Effect] = []
        if view.pending is not None:
            effects.append(
                Deliver(
                    Response(
                        request_id=view.pending.request_id,
                        ok=True,
                        result={"coalesced": True},
                    )
                )
            )
        if self._state == "ready" and view.inflight_id is None:
            effects.extend(self._send_mutation(view, message))
            return effects
        view.pending = message
        if self._state == "stopped":
            effects.extend(self._begin_start())
        elif self._state == "backoff" and not self._child_alive and self._due_restart():
            effects.extend(self._begin_start())
        return effects

    def _send_mutation(self, view: _View, message: Mutation) -> List[Effect]:
        view.pending = None
        view.inflight_id = message.request_id
        view.inflight = message
        return self._send(message)

    def _send(self, message: HostMessage) -> List[Effect]:
        kind = "other"
        view_id = getattr(message, "view_id", None)
        if is_mutation(message):
            kind = "mutation"
        elif isinstance(message, CloseView):
            kind = "close"
        elif isinstance(message, Ping):
            kind = "ping"
            self._ping_id = message.request_id
            self._ping_sent_at = self._now
        deadline = self._now + self._config.request_timeout
        if isinstance(message, Hello):
            kind = "hello"
            deadline = self._handshake_deadline or (self._now + self._config.handshake_timeout)
        self._sent[message.request_id] = _Sent(
            request_id=message.request_id,
            deadline=deadline,
            kind=kind,
            view_id=view_id if isinstance(view_id, str) else None,
            sent_at=self._now,
        )
        return [WriteFrame(encode_frame(message))]

    def _begin_start(self) -> List[Effect]:
        if self._child_alive or self._state == "starting":
            return []
        self._state = "starting"
        self._child_alive = True
        self._saw_ready = False
        self._hello_ok = False
        self._mismatch = False
        self._violations = 0
        self._missed_pings = 0
        self._ping_id = None
        self._ping_sent_at = None
        self._decoder = FrameDecoder()
        self._stderr.clear()
        self._spawn_at = self._now
        self._handshake_deadline = self._now + self._config.handshake_timeout
        self._session_token = uuid.uuid4().hex
        hello = Hello(
            request_id=uuid.uuid4().hex,
            protocol=PROTOCOL_NAME,
            version=PROTOCOL_VERSION,
            session_token=self._session_token,
            host_pid=self._host_pid,
        )
        self._hello_id = hello.request_id
        return [SpawnChild(), *self._send(hello)]

    def _become_ready(self) -> List[Effect]:
        self._state = "ready"
        self._handshake_deadline = None
        self._handshake_seconds = self._now - self._spawn_at
        self._next_ping_at = self._now + self._config.ping_interval
        effects: List[Effect] = [NoteHandshake(self._handshake_seconds)]
        early = self._early
        self._early = []
        for message in early:
            if is_mutation(message):
                continue
            effects.extend(self._send(message))
        for view in self._views.values():
            if view.inflight_id is not None:
                continue
            if view.pending is not None:
                effects.extend(self._send_mutation(view, view.pending))
            elif view.desired is not None:
                effects.extend(self._send_mutation(view, replace(view.desired, request_id=uuid.uuid4().hex)))
        return effects

    def _on_item(self, item: object) -> List[Effect]:
        if isinstance(item, NoiseLine):
            return [LogNoise(item.stream, item.text)] if item.text else []
        if isinstance(item, ProtocolViolation):
            self._violations += 1
            effects: List[Effect] = [LogNoise("stdout", item.reason)]
            if self._violations >= PROTOCOL_VIOLATIONS_BEFORE_RESTART and self._state in {"starting", "ready"}:
                effects.extend(self._enter_crash(already_dead=False, code=None, reason="protocol"))
            return effects
        if isinstance(item, Ready):
            self._saw_ready = True
            effects = [Deliver(item)]
            if self._hello_ok and self._state == "starting":
                effects.extend(self._become_ready())
            return effects
        if isinstance(item, Response):
            return self._on_response(item)
        if isinstance(item, (ErrorReport, Log, ViewClosed, CrashReport, NeedSecret)):
            return [Deliver(item)]
        return [LogNoise("stdout", "ignored child frame %s" % type(item).__name__)]

    def _on_response(self, response: Response) -> List[Effect]:
        sent = self._sent.pop(response.request_id, None)
        effects: List[Effect] = [Deliver(response)]
        if sent is None:
            return effects
        if sent.kind == "hello":
            if (not response.ok) or response.error == "protocol_mismatch":
                self._mismatch = True
                self._version_mismatch = True
                self._state = "circuit_open"
                self._announced_circuit = True
                self._handshake_deadline = None
                self._last_error = "The preview protocol version does not match."
                effects.append(
                    Deliver(
                        ErrorReport(
                            view_id=None,
                            code="FB603",
                            message=self._last_error,
                            traceback=response.detail or "",
                        )
                    )
                )
                return effects
            self._hello_ok = True
            if self._saw_ready and self._state == "starting":
                effects.extend(self._become_ready())
            return effects
        if sent.kind == "ping":
            self._missed_pings = 0
            self._ping_id = None
            return effects
        if sent.kind == "mutation":
            view = self._views.get(sent.view_id or "")
            if view is not None and view.inflight_id == response.request_id:
                if response.ok and isinstance(view.inflight, LoadForm):
                    view.revision = view.inflight.revision
                    view.desired = view.inflight
                if response.ok:
                    self._load_seconds = self._now - sent.sent_at
                    effects.append(NoteLoad(self._load_seconds))
                view.inflight_id = None
                view.inflight = None
                if view.pending is not None and self._state == "ready":
                    effects.extend(self._send_mutation(view, view.pending))
            return effects
        if sent.kind == "close" and response.ok and sent.view_id:
            self._views.pop(sent.view_id, None)
            if not self._views:
                self._ping_id = None
                self._next_ping_at = None
        return effects

    def _ping_if_due(self, now: float) -> List[Effect]:
        effects: List[Effect] = []
        if (
            self._ping_id is not None
            and self._ping_sent_at is not None
            and now >= self._ping_sent_at + self._config.ping_interval
        ):
            self._missed_pings += 1
            unanswered = self._ping_id
            self._ping_id = None
            self._sent.pop(unanswered, None)
            if self._missed_pings >= self._config.missed_pings:
                effects.extend(self._enter_crash(already_dead=False, code=None, reason="missed pings"))
                return effects
        if self._ping_id is None and self._next_ping_at is not None and now >= self._next_ping_at:
            effects.extend(self._send(Ping(request_id=uuid.uuid4().hex)))
            self._next_ping_at = now + self._config.ping_interval
        return effects

    def _enter_crash(self, *, already_dead: bool, code: Optional[int], reason: str) -> List[Effect]:
        if self._state in {"backoff", "circuit_open"}:
            if not already_dead and self._child_alive:
                return [KillChild()]
            return []
        if self._state in {"stopping", "stopped"} and not self._child_alive:
            return []
        self._prune(self._now)
        self._crash_times.append(self._now)
        index = len(self._crash_times) - 1
        tail = "\n".join(self._stderr)
        code_text = "none" if code is None else str(code)
        message = "The preview process stopped unexpectedly (exit %s, %s)." % (code_text, reason)
        if tail:
            message = "%s\n%s" % (message, tail)
        self._last_error = message
        effects: List[Effect] = []
        for sent in list(self._sent.values()):
            if sent.kind == "hello":
                continue
            effects.append(
                Deliver(
                    Response(
                        request_id=sent.request_id,
                        ok=False,
                        error="crashed",
                        detail=message,
                    )
                )
            )
        self._sent.clear()
        self._ping_id = None
        self._handshake_deadline = None
        open_views = list(self._views.items())
        for view_id, view in open_views:
            if view.inflight is not None and view.pending is None and isinstance(view.inflight, LoadForm):
                view.pending = view.inflight
            view.inflight_id = None
            view.inflight = None
            effects.append(
                Deliver(ErrorReport(view_id=view_id, code="FB601", message=message, traceback=tail))
            )
        if not open_views:
            effects.append(Deliver(ErrorReport(view_id=None, code="FB601", message=message, traceback=tail)))
        if not already_dead and self._child_alive:
            effects.append(KillChild())
        schedule: Sequence[float] = self._config.backoff
        if index >= len(schedule):
            self._state = "circuit_open"
            self._restart_at = None
            self._announced_circuit = True
            circuit = "Preview is off after repeated crashes."
            self._last_error = circuit
            effects.append(Deliver(ErrorReport(view_id=None, code="FB605", message=circuit, traceback="")))
        else:
            self._state = "backoff"
            self._restart_at = self._now + schedule[index]
        return effects

    def _due_restart(self) -> bool:
        return self._restart_at is not None and self._now >= self._restart_at

    def _prune(self, now: float) -> None:
        cutoff = now - self._config.crash_window
        self._crash_times = [stamp for stamp in self._crash_times if stamp >= cutoff]

    def _response(self, message: HostMessage, *, ok: bool, error: str, detail: Optional[str]) -> Deliver:
        request_id = getattr(message, "request_id", "")
        return Deliver(
            Response(
                request_id=request_id if isinstance(request_id, str) else "",
                ok=ok,
                error=None if ok else error,
                detail=detail,
            )
        )
