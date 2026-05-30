"""Integration tests for REPL control completion and introspection transport."""

from __future__ import annotations

import socket
from typing import Any

import pytest

from app.run.run_manifest import ReplControlConfig
from app.runner.repl_control import ReplControlServer
from app.runner.repl_protocol import REPL_CONTROL_PROTOCOL, dumps_message, envelope_from_dict, loads_message

pytestmark = pytest.mark.integration


def _read_json_line(sock: socket.socket) -> dict[str, Any]:
    chunks: list[bytes] = []
    while True:
        chunk = sock.recv(4096)
        if not chunk:
            break
        chunks.append(chunk)
        if b"\n" in chunk:
            break
    raw = b"".join(chunks).split(b"\n", 1)[0] + b"\n"
    return loads_message(raw)


def _free_port() -> int:
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    port = int(probe.getsockname()[1])
    probe.close()
    return port


def test_repl_control_complete_and_introspect_round_trip() -> None:
    namespace: dict[str, object] = {"sample_value": 123}
    port = _free_port()
    config = ReplControlConfig(
        protocol=REPL_CONTROL_PROTOCOL,
        session_token="integration-token",
        host="127.0.0.1",
        port=port,
        connect_timeout_ms=1000,
    )
    server = ReplControlServer(config=config, namespace=namespace)
    server.start()

    try:
        complete_payload = {
            "protocol": REPL_CONTROL_PROTOCOL,
            "session_token": "integration-token",
            "method": "complete",
            "line_buffer": "sample_",
            "cursor_offset": len("sample_"),
            "trigger_kind": "typing",
            "trigger_character": "",
            "max_results": 20,
        }
        with socket.create_connection(("127.0.0.1", port), timeout=1.0) as sock:
            sock.sendall(dumps_message(complete_payload))
            complete_response = _read_json_line(sock)
        assert complete_response.get("ok") is True
        complete_result = complete_response.get("result")
        assert isinstance(complete_result, dict)
        complete_envelope = envelope_from_dict(complete_result)
        assert any(item.label == "sample_value" for item in complete_envelope.items)

        introspect_payload = {
            "protocol": REPL_CONTROL_PROTOCOL,
            "session_token": "integration-token",
            "method": "introspect",
            "target_path": "PySide2.QtCore",
            "member_prefix": "",
            "include_private": False,
            "max_results": 20,
        }
        with socket.create_connection(("127.0.0.1", port), timeout=1.0) as sock:
            sock.sendall(dumps_message(introspect_payload))
            introspect_response = _read_json_line(sock)
        assert introspect_response.get("ok") is True
        introspect_result = introspect_response.get("result")
        assert isinstance(introspect_result, dict)
        introspect_envelope = envelope_from_dict(introspect_result)
        assert introspect_envelope.items
    finally:
        server.stop()
