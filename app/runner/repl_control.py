"""Runner-side loopback server for Python Console metadata requests."""

from __future__ import annotations

import logging
import socketserver
import threading
from typing import Any

from app.run.run_manifest import ReplControlConfig
from app.runner.repl_completion import ReplCompletionRequest, ReplCompletionService
from app.runner.repl_introspection import ReplIntrospectionRequest, ReplIntrospectionService
from app.runner.repl_protocol import (
    REPL_METHOD_COMPLETE,
    REPL_METHOD_INTROSPECT,
    REPL_METHOD_PING,
    ReplControlProtocolError,
    build_repl_error_response,
    build_repl_success_response,
    dumps_message,
    envelope_to_dict,
    loads_message,
    validate_repl_request,
)

_logger = logging.getLogger(__name__)


class ReplControlServer:
    """Small JSON-line loopback server owned by the REPL runner process."""

    def __init__(self, *, config: ReplControlConfig, namespace: dict[str, Any]) -> None:
        self._config = config
        self._namespace_lock = threading.RLock()
        self._introspection_service = ReplIntrospectionService()
        self._completion_service = ReplCompletionService(
            namespace,
            namespace_lock=self._namespace_lock,
            introspection_service=self._introspection_service,
        )
        self._server: socketserver.ThreadingTCPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start serving requests in a daemon thread."""

        completion_service = self._completion_service
        introspection_service = self._introspection_service
        session_token = self._config.session_token
        protocol = self._config.protocol

        class _Handler(socketserver.StreamRequestHandler):
            def handle(self) -> None:  # noqa: D401 - inherited protocol method
                try:
                    request_payload = loads_message(self.rfile.readline())
                    response_payload = _handle_request(
                        request_payload,
                        protocol=protocol,
                        session_token=session_token,
                        completion_service=completion_service,
                        introspection_service=introspection_service,
                    )
                except ReplControlProtocolError as exc:
                    response_payload = build_repl_error_response(str(exc))
                except (ValueError, TypeError, KeyError) as exc:
                    response_payload = build_repl_error_response(str(exc))
                except Exception:
                    _logger.warning("REPL control request failed", exc_info=True)
                    response_payload = build_repl_error_response("repl_internal_error")
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
    protocol: str,
    session_token: str,
    completion_service: ReplCompletionService,
    introspection_service: ReplIntrospectionService,
) -> dict[str, Any]:
    try:
        method = validate_repl_request(
            payload,
            expected_protocol=protocol,
            expected_session_token=session_token,
        )
    except ReplControlProtocolError as exc:
        return build_repl_error_response(str(exc))

    if method == REPL_METHOD_COMPLETE:
        envelope = completion_service.complete(
            ReplCompletionRequest(
                line_buffer=str(payload.get("line_buffer") or ""),
                cursor_offset=int(payload.get("cursor_offset") or 0),
                trigger_kind=str(payload.get("trigger_kind") or "invoked"),
                trigger_character=str(payload.get("trigger_character") or ""),
                max_results=int(payload.get("max_results") or 100),
            )
        )
        return build_repl_success_response(envelope_to_dict(envelope))

    if method == REPL_METHOD_INTROSPECT:
        envelope = introspection_service.introspect(
            ReplIntrospectionRequest(
                target_path=str(payload.get("target_path") or ""),
                member_prefix=str(payload.get("member_prefix") or ""),
                include_private=bool(payload.get("include_private", True)),
                max_results=int(payload.get("max_results") or 100),
            )
        )
        return build_repl_success_response(envelope_to_dict(envelope))

    if method == REPL_METHOD_PING:
        return build_repl_success_response({"status": "ready"})

    return build_repl_error_response("Unsupported REPL control method: %s" % (method,))
