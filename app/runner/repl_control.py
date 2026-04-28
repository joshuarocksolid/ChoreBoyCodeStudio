"""Runner-side loopback server for Python Console metadata requests."""

from __future__ import annotations

import logging
import socketserver
import threading
from typing import Any

from app.run.run_manifest import ReplControlConfig
from app.runner.repl_completion import ReplCompletionRequest, ReplCompletionService
from app.runner.repl_protocol import dumps_message, envelope_to_dict, loads_message

_logger = logging.getLogger(__name__)


class ReplControlServer:
    """Small JSON-line loopback server owned by the REPL runner process."""

    def __init__(self, *, config: ReplControlConfig, namespace: dict[str, Any]) -> None:
        self._config = config
        self._completion_service = ReplCompletionService(namespace)
        self._server: socketserver.ThreadingTCPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start serving requests in a daemon thread."""

        completion_service = self._completion_service
        session_token = self._config.session_token

        class _Handler(socketserver.StreamRequestHandler):
            def handle(self) -> None:  # noqa: D401 - inherited protocol method
                try:
                    request_payload = loads_message(self.rfile.readline())
                    response_payload = _handle_request(
                        request_payload,
                        session_token=session_token,
                        completion_service=completion_service,
                    )
                except Exception as exc:
                    response_payload = {"ok": False, "error": str(exc)}
                self.wfile.write(dumps_message(response_payload))

        socketserver.ThreadingTCPServer.allow_reuse_address = True
        self._server = socketserver.ThreadingTCPServer((self._config.host, self._config.port), _Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        _logger.info("REPL control server listening on %s:%s", self._config.host, self._config.port)

    def stop(self) -> None:
        """Stop the loopback server."""

        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=0.5)
        self._server = None
        self._thread = None


def _handle_request(
    payload: dict[str, Any],
    *,
    session_token: str,
    completion_service: ReplCompletionService,
) -> dict[str, Any]:
    if payload.get("session_token") != session_token:
        return {"ok": False, "error": "Invalid REPL control session token."}

    method = payload.get("method")
    if method == "complete":
        envelope = completion_service.complete(
            ReplCompletionRequest(
                line_buffer=str(payload.get("line_buffer") or ""),
                cursor_offset=int(payload.get("cursor_offset") or 0),
                trigger_kind=str(payload.get("trigger_kind") or "invoked"),
                trigger_character=str(payload.get("trigger_character") or ""),
                max_results=int(payload.get("max_results") or 100),
            )
        )
        return {"ok": True, "result": envelope_to_dict(envelope)}

    if method == "ping":
        return {"ok": True, "result": {"status": "ready"}}

    return {"ok": False, "error": "Unsupported REPL control method: %s" % (method,)}
