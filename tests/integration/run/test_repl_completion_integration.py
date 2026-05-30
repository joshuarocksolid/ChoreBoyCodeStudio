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


def test_repl_control_complete_import_statement_when_jedi_available() -> None:
    from app.intelligence.jedi_runtime import initialize_jedi_runtime

    jedi_status = initialize_jedi_runtime()
    if not jedi_status.is_available:
        pytest.skip(f"Jedi runtime unavailable: {jedi_status.message}")

    namespace: dict[str, object] = {}
    port = _free_port()
    config = ReplControlConfig(
        protocol=REPL_CONTROL_PROTOCOL,
        session_token="integration-token-import",
        host="127.0.0.1",
        port=port,
        connect_timeout_ms=1000,
    )
    server = ReplControlServer(config=config, namespace=namespace)
    server.start()

    try:
        line_buffer = "from Free"
        complete_payload = {
            "protocol": REPL_CONTROL_PROTOCOL,
            "session_token": "integration-token-import",
            "method": "complete",
            "line_buffer": line_buffer,
            "cursor_offset": len(line_buffer),
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
        labels = {item.label for item in complete_envelope.items}
        assert "FreeCAD" in labels
    finally:
        server.stop()


def test_repl_control_complete_from_freecad_dot_when_freecad_importable() -> None:
    try:
        import FreeCAD  # noqa: F401
    except ImportError:
        pytest.skip("FreeCAD is not importable in this runtime")

    namespace: dict[str, object] = {"__name__": "__console__", "__package__": None}
    port = _free_port()
    config = ReplControlConfig(
        protocol=REPL_CONTROL_PROTOCOL,
        session_token="integration-token-freecad-dot",
        host="127.0.0.1",
        port=port,
        connect_timeout_ms=1000,
    )
    server = ReplControlServer(config=config, namespace=namespace)
    server.start()

    try:
        line_buffer = "from FreeCAD."
        complete_payload = {
            "protocol": REPL_CONTROL_PROTOCOL,
            "session_token": "integration-token-freecad-dot",
            "method": "complete",
            "line_buffer": line_buffer,
            "cursor_offset": len(line_buffer),
            "trigger_kind": "trigger_character",
            "trigger_character": ".",
            "max_results": 20,
        }
        with socket.create_connection(("127.0.0.1", port), timeout=1.0) as sock:
            sock.sendall(dumps_message(complete_payload))
            complete_response = _read_json_line(sock)
        assert complete_response.get("ok") is True
        complete_result = complete_response.get("result")
        assert isinstance(complete_result, dict)
        complete_envelope = envelope_from_dict(complete_result)
        labels = {item.label for item in complete_envelope.items}
        assert labels
        assert "ActiveDocument" in labels or "Console" in labels
        assert complete_envelope.degradation_reason == "repl_runtime_inspection"
    finally:
        server.stop()
