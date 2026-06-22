"""Unit tests for debug transport lifecycle."""

from __future__ import annotations

import socket
import threading
import time

import pytest

from app.run.run_service import RunService  # noqa: F401 - establish import order before transport
from app.debug.debug_protocol import (
    build_debug_event,
    build_hello_message,
    encode_debug_message,
)
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


def test_debug_transport_server_close_suppresses_error_callback() -> None:
    """Intentional server close must not emit a spurious disconnect error (CC-06)."""
    errors: list[str] = []
    server = DebugTransportServer(on_message=lambda _message: None, on_error=errors.append)
    config = server.start()
    client = _connect_runner_client(server, config)
    try:
        server.close()
        time.sleep(0.1)
    finally:
        client.close()
    assert not errors


def test_debug_transport_server_rejects_invalid_hello_protocol() -> None:
    errors: list[str] = []
    server = DebugTransportServer(on_message=lambda _message: None, on_error=errors.append)
    config = server.start()
    try:
        sock = socket.create_connection(("127.0.0.1", config.port), timeout=2.0)
        writer = sock.makefile("w", encoding="utf-8")
        writer.write(
            encode_debug_message(
                {
                    "kind": "hello",
                    "protocol": "wrong_protocol",
                    "session_token": config.session_token,
                    "engine_name": "test",
                }
            )
        )
        writer.flush()
        writer.close()
        sock.close()
        _wait_until(lambda: bool(errors))
    finally:
        server.close()
    assert any("incompatible" in message.lower() for message in errors)


def test_debug_transport_server_eof_error_callback_invoked_once() -> None:
    errors: list[str] = []
    server = DebugTransportServer(on_message=lambda _message: None, on_error=errors.append)
    config = server.start()
    client_sock = socket.create_connection(("127.0.0.1", config.port), timeout=2.0)
    try:
        _wait_until(lambda: server.is_connected)
        client_sock.close()
        _wait_until(lambda: bool(errors))
        time.sleep(0.1)
    finally:
        server.close()
    assert len(errors) == 1
    assert "disconnect" in errors[0].lower()


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


def _connect_runner_client(
    server: DebugTransportServer,
    config,
    *,
    on_message=None,
    on_error=None,
) -> RunnerDebugTransportClient:
    client = RunnerDebugTransportClient(
        config,
        engine_name="test",
        on_message=on_message or (lambda _message: None),
        on_error=on_error,
    )
    client.connect()
    _wait_until(lambda: server.is_connected)
    return client


def test_runner_client_close_suppresses_error_callback() -> None:
    errors: list[str] = []
    server = DebugTransportServer(on_message=lambda _message: None)
    config = server.start()
    client = _connect_runner_client(server, config, on_error=errors.append)
    client.close()
    time.sleep(0.1)
    server.close()
    assert not errors


def test_runner_client_rejects_send_when_disconnected() -> None:
    server = DebugTransportServer(on_message=lambda _message: None)
    config = server.start()
    client = RunnerDebugTransportClient(
        config,
        engine_name="test",
        on_message=lambda _message: None,
    )
    try:
        with pytest.raises(RuntimeError, match="not connected"):
            client.send_message(build_hello_message(session_token="unused", engine_name="test"))
    finally:
        server.close()


def test_runner_client_eof_invokes_error_callback() -> None:
    errors: list[str] = []
    server = DebugTransportServer(on_message=lambda _message: None)
    config = server.start()
    client = _connect_runner_client(server, config, on_error=errors.append)
    try:
        server.close()
        _wait_until(lambda: bool(errors))
    finally:
        client.close()
    assert any("disconnect" in message.lower() or "failed" in message.lower() for message in errors)


def test_debug_transport_send_after_peer_disconnect_raises() -> None:
    server = DebugTransportServer(on_message=lambda _message: None)
    config = server.start()
    client = _connect_runner_client(server, config)
    client.close()
    _wait_until(lambda: not server.is_connected)
    try:
        with pytest.raises(RuntimeError, match="not connected"):
            server.send_command("continue")
    finally:
        server.close()


def test_debug_transport_happy_path_connect_event_command_close() -> None:
    received_events: list[dict] = []
    received_commands: list[dict] = []

    def _on_server_message(message: dict) -> None:
        if message.get("kind") == "event":
            received_events.append(message)

    server = DebugTransportServer(on_message=_on_server_message)
    config = server.start()
    client = RunnerDebugTransportClient(
        config,
        engine_name="test",
        on_message=received_commands.append,
    )
    client.connect()
    _wait_until(lambda: server.is_connected)
    try:
        client.send_message(build_debug_event("paused", {"reason": "breakpoint"}))
        _wait_until(lambda: len(received_events) == 1)
        assert received_events[0]["event"] == "paused"

        server.send_command("continue")
        _wait_until(lambda: len(received_commands) == 1)
        assert received_commands[0]["command"] == "continue"
        assert received_commands[0]["kind"] == "command"
    finally:
        client.close()
        server.close()


def test_debug_transport_concurrent_send_while_peer_disconnects() -> None:
    errors: list[str] = []
    server = DebugTransportServer(on_message=lambda _message: None, on_error=errors.append)
    config = server.start()
    client_sock = socket.create_connection(("127.0.0.1", config.port), timeout=2.0)
    writer = client_sock.makefile("w", encoding="utf-8")
    writer.write(
        encode_debug_message(
            build_hello_message(session_token=config.session_token, engine_name="test")
        )
    )
    writer.flush()
    _wait_until(lambda: server.is_connected)

    send_errors: list[BaseException] = []

    def spam_send() -> None:
        for _ in range(100):
            try:
                server.send_command("continue")
            except BaseException as exc:  # noqa: BLE001 - stress test captures all send failures
                send_errors.append(exc)
                return
            time.sleep(0.001)

    sender = threading.Thread(target=spam_send, daemon=True)
    sender.start()
    time.sleep(0.05)
    client_sock.close()
    sender.join(timeout=2.0)
    try:
        server.close()
        server.close()
    finally:
        pass
    assert sender.is_alive() is False


def test_runner_client_concurrent_send_while_server_closes() -> None:
    errors: list[str] = []
    server = DebugTransportServer(on_message=lambda _message: None)
    config = server.start()
    client = _connect_runner_client(server, config, on_error=errors.append)
    send_errors: list[BaseException] = []

    def spam_send() -> None:
        for _ in range(100):
            try:
                client.send_message(build_debug_event("heartbeat"))
            except BaseException as exc:  # noqa: BLE001 - stress test captures all send failures
                send_errors.append(exc)
                return
            time.sleep(0.001)

    sender = threading.Thread(target=spam_send, daemon=True)
    sender.start()
    time.sleep(0.05)
    server.close()
    sender.join(timeout=2.0)
    client.close()
    assert sender.is_alive() is False
