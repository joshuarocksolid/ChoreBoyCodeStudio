"""Short-lived schema helper. The editor talks frames. It does not import a driver."""

from __future__ import annotations

import os
import threading
import time
import uuid
from typing import Callable, Dict, List, Optional

from app.features.form_builder.engine.data.connections import Connection
from app.features.form_builder.engine.data.schema_cache import installed_root, installed_slug
from app.features.form_builder.engine.ipc.protocol import (
    FrameDecoder,
    HelperProgress,
    NeedSecret,
    ProbeSelect,
    ProvideSecret,
    ReadSchema,
    Response,
    TestConnection,
    encode_frame,
)
from app.features.form_builder.qtside.preview.launch import preview_command, repo_root
from app.features.form_builder.qtside.schema_prompt import project_slug, stored_machine_password
from app.run.process_supervisor import ProcessEvent, ProcessSupervisor

_EXIT = object()
_HELPER_SCRIPT = "run_schema_helper.py"
_CONNECT_TIMEOUT = 10.0
_BATCH_TIMEOUT = 20.0
_COMMAND: Optional[List[str]] = None
_RUNNER: Optional["SchemaRunner"] = None


def set_helper_command(argv: Optional[List[str]]) -> None:
    global _COMMAND
    _COMMAND = list(argv) if argv else None


def set_helper_timeouts(connect: float, batch: float) -> None:
    global _CONNECT_TIMEOUT, _BATCH_TIMEOUT
    _CONNECT_TIMEOUT = float(connect)
    _BATCH_TIMEOUT = float(batch)


def helper_command() -> List[str]:
    if _COMMAND:
        return list(_COMMAND)
    return preview_command(repo_root(), _HELPER_SCRIPT)


def register_schema_runner() -> "SchemaRunner":
    global _RUNNER
    from app.features.form_builder.engine.data.schema_cache import set_schema_runner

    if _RUNNER is None:
        _RUNNER = SchemaRunner()
    set_schema_runner(_RUNNER)
    return _RUNNER


class SchemaRunner:
    """One child at a time. A new call cancels the previous and that caller gets ``cancelled``."""

    def __init__(self) -> None:
        self._supervisor = ProcessSupervisor(on_event=self._on_event)
        self._cond = threading.Condition()
        self._start_lock = threading.Lock()
        self._generation = 0
        self._listen: Optional[int] = None
        self._items: List[object] = []
        self._decoder = FrameDecoder()
        self._connected = False
        self._started = 0.0
        self._connected_at = 0.0
        self._paused_before = 0.0
        self._paused_after = 0.0
        self._connect_timeout = _CONNECT_TIMEOUT
        self._batch_timeout = _BATCH_TIMEOUT
        self._secrets: Dict[tuple, str] = {}

    def schema(
        self,
        project_root: str,
        connection: Connection,
        ask_secret: Callable[[Connection], str],
    ) -> dict:
        return self._exchange("schema", project_root, connection, ask_secret)

    def test(
        self,
        project_root: str,
        connection: Connection,
        ask_secret: Callable[[Connection], str],
    ) -> dict:
        return self._exchange("test", project_root, connection, ask_secret)

    def probe_select(
        self,
        project_root: str,
        connection: Connection,
        sql: str,
        ask_secret: Callable[[Connection], str],
    ) -> dict:
        return self._exchange("probe_select", project_root, connection, ask_secret, sql)

    def cancel(self) -> None:
        with self._cond:
            self._generation += 1
            self._listen = None
            self._cond.notify_all()
        if self._supervisor.is_running():
            self._supervisor.stop()

    def _exchange(
        self,
        kind: str,
        project_root: str,
        connection: Connection,
        ask_secret: Callable[[Connection], str],
        sql: str = "",
    ) -> dict:
        with self._cond:
            self._generation += 1
            generation = self._generation
            self._listen = None
            self._cond.notify_all()
        if self._supervisor.is_running():
            self._supervisor.stop()
        with self._start_lock:
            with self._cond:
                if self._generation != generation:
                    return _cancelled()
            if self._supervisor.is_running():
                self._supervisor.stop()
            with self._cond:
                if self._generation != generation:
                    return _cancelled()
                self._items.clear()
                self._decoder = FrameDecoder()
                self._connected = False
                self._paused_before = 0.0
                self._paused_after = 0.0
                self._connect_timeout = _CONNECT_TIMEOUT
                self._batch_timeout = _BATCH_TIMEOUT
                self._started = time.monotonic()
                self._listen = generation
            try:
                self._supervisor.start(helper_command(), cwd=repo_root(), env=_helper_env())
                self._supervisor.send_input(encode_frame(_request(kind, project_root, connection, sql)))
            except Exception as exc:
                if self._generation == generation and self._supervisor.is_running():
                    self._supervisor.stop()
                if self._generation != generation:
                    return _cancelled()
                lines = str(exc).splitlines()
                return {"ok": False, "kind": "other", "message": lines[0] if lines else "Can't connect."}
        return self._wait(generation, project_root, connection, ask_secret)

    def _wait(
        self,
        generation: int,
        project_root: str,
        connection: Connection,
        ask_secret: Callable[[Connection], str],
    ) -> dict:
        while True:
            if self._generation != generation:
                return _cancelled()
            item = self._pop(0.05)
            if self._generation != generation:
                return _cancelled()
            if item is None:
                if self._timed_out():
                    return self._kill(generation, "took too long")
                continue
            if item is _EXIT:
                late = self._drain_response(generation, 0.3)
                if self._generation != generation:
                    return _cancelled()
                if late is None:
                    return {"ok": False, "kind": "other", "message": "The helper stopped."}
                item = late
            if isinstance(item, HelperProgress) and item.phase == "connected":
                with self._cond:
                    if self._listen == generation:
                        self._connected = True
                        self._connected_at = time.monotonic()
                continue
            if isinstance(item, NeedSecret):
                secret = self._answer(project_root, connection, ask_secret, generation)
                if self._generation != generation:
                    return _cancelled()
                try:
                    self._supervisor.send_input(
                        encode_frame(ProvideSecret("", connection.name, secret))
                    )
                except Exception:
                    if self._generation != generation:
                        return _cancelled()
                    return {"ok": False, "kind": "other", "message": "The helper stopped."}
                continue
            if isinstance(item, Response):
                payload = _result(item)
                if payload.get("kind") == "auth":
                    self._secrets.pop(_key(project_root, connection), None)
                self._finish(generation)
                return payload

    def _answer(
        self,
        project_root: str,
        connection: Connection,
        ask_secret: Callable[[Connection], str],
        generation: int,
    ) -> str:
        key = _key(project_root, connection)
        found = self._secrets.get(key)
        if found:
            return found
        policy = connection.password
        if policy == "machine":
            stored = stored_machine_password(project_root, connection)
            if stored:
                self._secrets[key] = stored
                return stored
        if policy in (None, "", "none"):
            return ""
        began = time.monotonic()
        try:
            secret = ask_secret(connection) or ""
        except Exception:
            secret = ""
        self._pause(generation, time.monotonic() - began)
        if secret:
            self._secrets[key] = secret
        return secret

    def _pause(self, generation: int, elapsed: float) -> None:
        with self._cond:
            if self._listen != generation:
                return
            if self._connected:
                self._paused_after += elapsed
            else:
                self._paused_before += elapsed

    def _timed_out(self) -> bool:
        with self._cond:
            now = time.monotonic()
            if not self._connected:
                return now - self._started - self._paused_before >= self._connect_timeout
            return now - self._connected_at - self._paused_after >= self._batch_timeout

    def _kill(self, generation: int, reason: str) -> dict:
        if self._generation != generation:
            return _cancelled()
        with self._cond:
            if self._listen == generation:
                self._listen = None
        if self._supervisor.is_running():
            self._supervisor.stop()
        if self._generation != generation:
            return _cancelled()
        return {"ok": False, "kind": "unreachable", "message": reason}

    def _finish(self, generation: int) -> None:
        if self._generation != generation:
            return
        with self._cond:
            if self._listen == generation:
                self._listen = None
        if self._supervisor.is_running():
            self._supervisor.stop()

    def _drain_response(self, generation: int, seconds: float) -> Optional[Response]:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if self._generation != generation:
                return None
            item = self._pop(0.02)
            if isinstance(item, Response):
                return item
            if item is None:
                continue
        return None

    def _pop(self, timeout: float) -> object:
        with self._cond:
            if not self._items:
                self._cond.wait(timeout)
            if not self._items:
                return None
            return self._items.pop(0)

    def _on_event(self, event: ProcessEvent) -> None:
        with self._cond:
            if self._listen is None:
                return
            if event.event_type == "output" and event.stream == "stdout" and event.text:
                for message in self._decoder.feed(event.text):
                    self._items.append(message)
                self._cond.notify_all()
            elif event.event_type == "exit":
                self._items.append(_EXIT)
                self._cond.notify_all()


def _request(kind: str, project_root: str, connection: Connection, sql: str) -> object:
    request_id = uuid.uuid4().hex
    payload = _connection_payload(connection)
    root = os.path.abspath(project_root) if project_root else ""
    slug = installed_slug() if root and root == installed_root() else project_slug(root)
    if kind == "test":
        return TestConnection(request_id, payload, root, slug)
    if kind == "probe_select":
        return ProbeSelect(request_id, payload, sql, root, slug)
    return ReadSchema(request_id, payload, root, slug)


def _connection_payload(connection: Connection) -> Dict[str, object]:
    payload: Dict[str, object] = {
        "name": connection.name,
        "title": connection.title,
        "engine": connection.engine,
    }
    for key, value in (
        ("file", connection.file),
        ("host", connection.host),
        ("port", connection.port),
        ("database", connection.database),
        ("user", connection.user),
        ("password", connection.password),
        ("schema", connection.schema),
        ("setup", connection.setup),
    ):
        if value is not None:
            payload[key] = value
    if connection.try_show_sql_only:
        payload["tryShowSqlOnly"] = True
    return payload


def _helper_env() -> Dict[str, str]:
    env = dict(os.environ)
    # The test DSN and libpq password vars must not ride along. The secret arrives as provide_secret.
    for key in ("CBCS_PG93_DSN", "PGPASSWORD", "PGPASSFILE"):
        env.pop(key, None)
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    root = repo_root()
    current = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = root if not current else root + os.pathsep + current
    return env


def _result(response: Response) -> dict:
    result = response.result
    if isinstance(result, dict):
        return result
    if response.ok:
        return {"ok": True}
    return {"ok": False, "kind": "other", "message": response.error or "Can't connect."}


def _cancelled() -> dict:
    return {"ok": False, "kind": "cancelled", "message": ""}


def _key(project_root: str, connection: Connection) -> tuple:
    return (os.path.abspath(project_root) if project_root else "", connection.name)


__all__ = [
    "SchemaRunner",
    "helper_command",
    "register_schema_runner",
    "set_helper_command",
    "set_helper_timeouts",
]
