"""Socket-backed debug transport used by editor and runner."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, IO, Mapping
import socket
import threading

from app.debug.debug_models import DebugTransportConfig
from app.debug.debug_protocol import (
    DEBUG_PROTOCOL_NAME,
    build_debug_command,
    build_hello_message,
    encode_debug_message,
    decode_debug_message,
)


_MessageCallback = Callable[[dict[str, Any]], None]
_ErrorCallback = Callable[[str], None]


@dataclass
class _SocketResources:
    sock: socket.socket
    reader: IO[str]
    writer: IO[str]


class DebugTransportServer:
    """Editor-side loopback server that receives runner debug messages."""

    def __init__(
        self,
        *,
        on_message: _MessageCallback,
        on_error: _ErrorCallback | None = None,
    ) -> None:
        self._on_message = on_message
        self._on_error = on_error
        self._server_socket: socket.socket | None = None
        self._client_resources: _SocketResources | None = None
        self._accept_thread: threading.Thread | None = None
        self._read_thread: threading.Thread | None = None
        self._close_event = threading.Event()
        self._write_lock = threading.Lock()
        self._session_token = ""

    def start(self) -> DebugTransportConfig:
        """Start listening for one runner connection and return manifest config."""

        if self._server_socket is not None:
            raise RuntimeError("Debug transport server already started.")
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind(("127.0.0.1", 0))
        server_socket.listen(1)
        server_socket.settimeout(0.5)
        self._server_socket = server_socket
        self._session_token = build_debug_command("session_token")["command_id"]
        self._accept_thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._accept_thread.start()
        host, port = server_socket.getsockname()
        return DebugTransportConfig(
            protocol=DEBUG_PROTOCOL_NAME,
            host=str(host),
            port=int(port),
            session_token=self._session_token,
        )

    @property
    def is_connected(self) -> bool:
        return self._client_resources is not None

    def send_command(self, command_name: str, arguments: Mapping[str, Any] | None = None) -> str:
        """Send one command to the connected runner."""

        resources = self._client_resources
        if resources is None:
            raise RuntimeError("Debug transport is not connected.")
        payload = build_debug_command(command_name, arguments)
        encoded = encode_debug_message(payload)
        with self._write_lock:
            resources.writer.write(encoded)
            resources.writer.flush()
        return str(payload["command_id"])

    def close(self) -> None:
        """Close listener and any accepted runner connection."""

        self._close_event.set()
        resources = self._client_resources
        self._client_resources = None
        if resources is not None:
            self._close_socket_resources(resources)
        server_socket = self._server_socket
        self._server_socket = None
        if server_socket is not None:
            try:
                server_socket.close()
            except OSError:
                pass
        if self._accept_thread is not None and self._accept_thread.is_alive():
            self._accept_thread.join(timeout=0.5)
        if self._read_thread is not None and self._read_thread.is_alive():
            self._read_thread.join(timeout=0.5)

    def _accept_loop(self) -> None:
        server_socket = self._server_socket
        if server_socket is None:
            return
        while not self._close_event.is_set():
            try:
                client_socket, _addr = server_socket.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            client_socket.settimeout(None)
            reader = client_socket.makefile("r", encoding="utf-8")
            writer = client_socket.makefile("w", encoding="utf-8")
            resources = _SocketResources(sock=client_socket, reader=reader, writer=writer)
            self._client_resources = resources
            self._read_thread = threading.Thread(target=self._read_loop, args=(resources,), daemon=True)
            self._read_thread.start()
            return

    def _read_loop(self, resources: _SocketResources) -> None:
        try:
            for line in resources.reader:
                if self._close_event.is_set():
                    return
                message = decode_debug_message(line)
                if message.get("kind") == "hello":
                    if message.get("protocol") != DEBUG_PROTOCOL_NAME:
                        raise ValueError("Runner connected with incompatible debug protocol.")
                    if message.get("session_token") != self._session_token:
                        raise ValueError("Runner connected with invalid debug session token.")
                self._on_message(message)
        except Exception as exc:
            if not self._close_event.is_set():
                self._emit_error("Debug transport read failed: %s" % (exc,))
        finally:
            self._client_resources = None
            self._close_socket_resources(resources)

    def _emit_error(self, message: str) -> None:
        if self._on_error is not None:
            self._on_error(message)

    @staticmethod
    def _close_socket_resources(resources: _SocketResources) -> None:
        try:
            resources.reader.close()
        except OSError:
            pass
        try:
            resources.writer.close()
        except OSError:
            pass
        try:
            resources.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            resources.sock.close()
        except OSError:
            pass


class RunnerDebugTransportClient:
    """Runner-side client that connects back to the editor debug server."""

    def __init__(
        self,
        config: DebugTransportConfig,
        *,
        engine_name: str,
        on_message: _MessageCallback,
        on_error: _ErrorCallback | None = None,
    ) -> None:
        self._config = config
        self._engine_name = engine_name
        self._on_message = on_message
        self._on_error = on_error
        self._resources: _SocketResources | None = None
        self._read_thread: threading.Thread | None = None
        self._close_event = threading.Event()
        self._write_lock = threading.Lock()

    def connect(self) -> None:
        """Connect to the editor-side server and begin listening."""

        if self._resources is not None:
            raise RuntimeError("Runner debug transport already connected.")
        sock = socket.create_connection(
            (self._config.host, int(self._config.port)),
            timeout=max(1.0, float(self._config.connect_timeout_ms) / 1000.0),
        )
        reader = sock.makefile("r", encoding="utf-8")
        writer = sock.makefile("w", encoding="utf-8")
        self._resources = _SocketResources(sock=sock, reader=reader, writer=writer)
        self.send_message(build_hello_message(session_token=self._config.session_token, engine_name=self._engine_name))
        self._read_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._read_thread.start()

    def send_message(self, payload: Mapping[str, Any]) -> None:
        """Send one raw protocol payload."""

        resources = self._resources
        if resources is None:
            raise RuntimeError("Runner debug transport is not connected.")
        encoded = encode_debug_message(payload)
        with self._write_lock:
            resources.writer.write(encoded)
            resources.writer.flush()

    def close(self) -> None:
        """Close runner-side resources."""

        self._close_event.set()
        resources = self._resources
        self._resources = None
        if resources is not None:
            DebugTransportServer._close_socket_resources(resources)
        if self._read_thread is not None and self._read_thread.is_alive():
            self._read_thread.join(timeout=0.5)

    def _read_loop(self) -> None:
        resources = self._resources
        if resources is None:
            return
        try:
            for line in resources.reader:
                if self._close_event.is_set():
                    return
                self._on_message(decode_debug_message(line))
        except Exception as exc:
            if not self._close_event.is_set() and self._on_error is not None:
                self._on_error("Runner debug transport failed: %s" % (exc,))
