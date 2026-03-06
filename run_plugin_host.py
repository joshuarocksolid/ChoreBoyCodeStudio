from __future__ import annotations

import argparse
import sys
from typing import Any

from app.plugins.host_runtime import load_runtime_command_handlers
from app.plugins.rpc_protocol import build_response, decode_message, encode_message


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="run_plugin_host.py")
    parser.add_argument("--state-root", dest="state_root", default=None)
    args = parser.parse_args(argv)

    handlers = load_runtime_command_handlers(state_root=args.state_root)
    _write_stdout({"type": "ready", "command_count": len(handlers)})

    for line in sys.stdin:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = decode_message(stripped)
        except Exception as exc:
            _write_stdout({"type": "error", "error": f"Invalid message: {exc}"})
            continue
        message_type = payload.get("type")
        if message_type == "ping":
            _write_stdout({"type": "pong"})
            continue
        if message_type == "reload":
            handlers = load_runtime_command_handlers(state_root=args.state_root)
            _write_stdout({"type": "reloaded", "command_count": len(handlers)})
            continue
        if message_type != "command":
            _write_stdout({"type": "error", "error": f"Unsupported message type: {message_type}"})
            continue

        request_id = payload.get("request_id")
        command_id = payload.get("command_id")
        command_payload = payload.get("payload", {})
        if not isinstance(request_id, str) or not request_id.strip():
            _write_stdout({"type": "error", "error": "Missing request_id"})
            continue
        if not isinstance(command_id, str) or not command_id.strip():
            _write_stdout(encode_message(build_response(request_id=request_id, ok=False, error="Missing command_id")))
            continue
        if not isinstance(command_payload, dict):
            _write_stdout(encode_message(build_response(request_id=request_id, ok=False, error="payload must be object")))
            continue
        handler = handlers.get(command_id)
        if handler is None:
            _write_stdout(
                encode_message(
                    build_response(
                        request_id=request_id,
                        ok=False,
                        error=f"Command not found: {command_id}",
                    )
                )
            )
            continue
        try:
            result = handler(dict(command_payload))
        except Exception as exc:
            _write_stdout(
                encode_message(build_response(request_id=request_id, ok=False, error=str(exc)))
            )
            continue
        _write_stdout(encode_message(build_response(request_id=request_id, ok=True, result=result)))
    return 0


def _write_stdout(payload: dict[str, Any] | str) -> None:
    if isinstance(payload, str):
        text = payload
    else:
        text = encode_message(payload)
    if not text.endswith("\n"):
        text += "\n"
    sys.stdout.write(text)
    sys.stdout.flush()


if __name__ == "__main__":
    raise SystemExit(main())
