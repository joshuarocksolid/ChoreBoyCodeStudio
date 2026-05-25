"""Unit tests for debug transport lifecycle."""

from __future__ import annotations

import socket
import time

import pytest

from app.run.run_service import RunService  # noqa: F401 - establish import order before transport
from app.debug.debug_protocol import build_hello_message, encode_debug_message
from app.debug.debug_transport import DebugTransportServer, RunnerDebugTransportClient

pytestmark = pytest.mark.unit


def _wait_until(predicate, *, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("Condition not met within timeout")


def test_debug_transport_server_rejects_send_when_disconnected() -> None:
    server = DebugTransportServer(on_message=lambda _message: None)
    config = server.start()
    try:
        with pytest.raises(RuntimeError, match="not connected"):
            server.send_command("continue")
    finally:
        server.close()
    assert config.port > 0


def test_debug_transport_server_eof_invokes_error_callback() -> None:
    errors: list[str] = []
    server = DebugTransportServer(on_message=lambda _message: None, on_error=errors.append)
    config = server.start()
    client_sock = socket.create_connection(("127.0.0.1", config.port), timeout=2.0)
    try:
        _wait_until(lambda: server.is_connected)
        client_sock.close()
        _wait_until(lambda: bool(errors))
    finally:
        server.close()
    assert any("disconnect" in message.lower() for message in errors)


def test_debug_transport_server_close_is_idempotent() -> None:
    server = DebugTransportServer(on_message=lambda _message: None)
    server.start()
    server.close()
    server.close()


def test_debug_transport_server_rejects_invalid_hello_token() -> None:
    errors: list[str] = []
    server = DebugTransportServer(on_message=lambda _message: None, on_error=errors.append)
    config = server.start()
    try:
        sock = socket.create_connection(("127.0.0.1", config.port), timeout=2.0)
        writer = sock.makefile("w", encoding="utf-8")
        writer.write(
            encode_debug_message(
                build_hello_message(session_token="wrong-token", engine_name="test")
            )
        )
        writer.flush()
        writer.close()
        sock.close()
        _wait_until(lambda: bool(errors))
    finally:
        server.close()
    assert errors
