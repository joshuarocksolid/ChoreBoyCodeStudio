from __future__ import annotations

import argparse
from dataclasses import dataclass
import sys
import threading
from typing import Any

from app.plugins.host_runtime import load_runtime_index
from app.plugins.rpc_protocol import (
    build_job_event,
    build_job_terminal_message,
    build_response,
    decode_message,
    encode_message,
)


@dataclass
class _RunningJob:
    job_id: str
    provider_key: str
    cancel_event: threading.Event
    thread: threading.Thread


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="run_plugin_host.py")
    parser.add_argument("--state-root", dest="state_root", default=None)
    args = parser.parse_args(argv)

    runtime_index = load_runtime_index(state_root=args.state_root)
    jobs: dict[str, _RunningJob] = {}
    jobs_lock = threading.RLock()
    write_lock = threading.RLock()
    _write_stdout(
        {
            "type": "ready",
            "command_count": runtime_index.command_count,
            "provider_count": runtime_index.provider_count,
        },
        write_lock=write_lock,
    )

    for line in sys.stdin:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = decode_message(stripped)
        except Exception as exc:
            _write_stdout({"type": "error", "error": f"Invalid message: {exc}"}, write_lock=write_lock)
            continue
        message_type = payload.get("type")
        if message_type == "ping":
            _write_stdout({"type": "pong"}, write_lock=write_lock)
            continue
        if message_type == "reload":
            with jobs_lock:
                for running_job in jobs.values():
                    running_job.cancel_event.set()
            runtime_index = load_runtime_index(state_root=args.state_root)
            _write_stdout(
                {
                    "type": "reloaded",
                    "command_count": runtime_index.command_count,
                    "provider_count": runtime_index.provider_count,
                },
                write_lock=write_lock,
            )
            continue
        if message_type not in {
            "command",
            "provider_query",
            "provider_job_start",
            "provider_job_cancel",
        }:
            _write_stdout(
                {"type": "error", "error": f"Unsupported message type: {message_type}"},
                write_lock=write_lock,
            )
            continue

        request_id = payload.get("request_id")
        if not isinstance(request_id, str) or not request_id.strip():
            _write_stdout({"type": "error", "error": "Missing request_id"}, write_lock=write_lock)
            continue
        if message_type == "command":
            command_id = payload.get("command_id")
            command_payload = payload.get("payload", {})
            activation_event = payload.get("activation_event")
            if not isinstance(command_id, str) or not command_id.strip():
                _write_stdout(
                    encode_message(build_response(request_id=request_id, ok=False, error="Missing command_id")),
                    write_lock=write_lock,
                )
                continue
            if not isinstance(command_payload, dict):
                _write_stdout(
                    encode_message(build_response(request_id=request_id, ok=False, error="payload must be object")),
                    write_lock=write_lock,
                )
                continue
            try:
                result = runtime_index.invoke_command(
                    command_id.strip(),
                    dict(command_payload),
                    activation_event=activation_event if isinstance(activation_event, str) else None,
                )
            except Exception as exc:
                _write_stdout(
                    encode_message(build_response(request_id=request_id, ok=False, error=str(exc))),
                    write_lock=write_lock,
                )
                continue
            _write_stdout(
                encode_message(
                    build_response(
                        request_id=request_id,
                        ok=True,
                        result=result,
                    )
                ),
                write_lock=write_lock,
            )
            continue
        if message_type == "provider_query":
            provider_key = payload.get("provider_key")
            request_payload = payload.get("request", {})
            activation_event = payload.get("activation_event")
            if not isinstance(provider_key, str) or not provider_key.strip():
                _write_stdout(
                    encode_message(build_response(request_id=request_id, ok=False, error="Missing provider_key")),
                    write_lock=write_lock,
                )
                continue
            if not isinstance(request_payload, dict):
                _write_stdout(
                    encode_message(build_response(request_id=request_id, ok=False, error="request must be object")),
                    write_lock=write_lock,
                )
                continue
            try:
                result = runtime_index.invoke_query(
                    provider_key.strip(),
                    dict(request_payload),
                    activation_event=activation_event if isinstance(activation_event, str) else None,
                )
            except Exception as exc:
                _write_stdout(
                    encode_message(build_response(request_id=request_id, ok=False, error=str(exc))),
                    write_lock=write_lock,
                )
                continue
            _write_stdout(
                encode_message(
                    build_response(
                        request_id=request_id,
                        ok=True,
                        result=result,
                    )
                ),
                write_lock=write_lock,
            )
            continue
        if message_type == "provider_job_cancel":
            job_id = payload.get("job_id")
            if not isinstance(job_id, str) or not job_id.strip():
                _write_stdout(
                    encode_message(build_response(request_id=request_id, ok=False, error="Missing job_id")),
                    write_lock=write_lock,
                )
                continue
            cancelled = False
            with jobs_lock:
                running_job = jobs.get(job_id)
                if running_job is not None:
                    running_job.cancel_event.set()
                    cancelled = True
            _write_stdout(
                encode_message(
                    build_response(
                        request_id=request_id,
                        ok=True,
                        result={"job_id": job_id, "cancel_requested": cancelled},
                    )
                ),
                write_lock=write_lock,
            )
            continue

        provider_key = payload.get("provider_key")
        request_payload = payload.get("request", {})
        activation_event = payload.get("activation_event")
        job_id = payload.get("job_id")
        if not isinstance(provider_key, str) or not provider_key.strip():
            _write_stdout(
                encode_message(build_response(request_id=request_id, ok=False, error="Missing provider_key")),
                write_lock=write_lock,
            )
            continue
        if not isinstance(job_id, str) or not job_id.strip():
            _write_stdout(
                encode_message(build_response(request_id=request_id, ok=False, error="Missing job_id")),
                write_lock=write_lock,
            )
            continue
        normalized_provider_key = provider_key.strip()
        normalized_job_id = job_id.strip()
        if not isinstance(request_payload, dict):
            _write_stdout(
                encode_message(build_response(request_id=request_id, ok=False, error="request must be object")),
                write_lock=write_lock,
            )
            continue
        cancel_event = threading.Event()

        def _emit_job_event(event_type: str, payload_dict: dict[str, Any]) -> None:
            _write_stdout(
                build_job_event(
                    job_id=normalized_job_id,
                    provider_key=normalized_provider_key,
                    event_type=event_type,
                    payload=payload_dict,
                ),
                write_lock=write_lock,
            )

        def _run_job() -> None:
            try:
                result = runtime_index.run_job(
                    normalized_provider_key,
                    dict(request_payload),
                    emit_event=_emit_job_event,
                    is_cancelled=cancel_event.is_set,
                    activation_event=activation_event if isinstance(activation_event, str) else None,
                )
            except Exception as exc:
                _write_stdout(
                    build_job_terminal_message(
                        job_id=normalized_job_id,
                        provider_key=normalized_provider_key,
                        message_type="job_error",
                        error=str(exc),
                    ),
                    write_lock=write_lock,
                )
            else:
                _write_stdout(
                    build_job_terminal_message(
                        job_id=normalized_job_id,
                        provider_key=normalized_provider_key,
                        message_type="job_result",
                        result=result,
                    ),
                    write_lock=write_lock,
                )
            finally:
                with jobs_lock:
                    jobs.pop(normalized_job_id, None)

        job_thread = threading.Thread(
            target=_run_job,
            name=f"plugin_job_{normalized_job_id}",
            daemon=True,
        )
        with jobs_lock:
            jobs[normalized_job_id] = _RunningJob(
                job_id=normalized_job_id,
                provider_key=normalized_provider_key,
                cancel_event=cancel_event,
                thread=job_thread,
            )
        job_thread.start()
        _write_stdout(
            encode_message(
                build_response(
                    request_id=request_id,
                    ok=True,
                    result={"job_id": normalized_job_id, "provider_key": normalized_provider_key},
                )
            ),
            write_lock=write_lock,
        )
    return 0


def _write_stdout(payload: dict[str, Any] | str, *, write_lock: threading.RLock) -> None:
    if isinstance(payload, str):
        text = payload
    else:
        text = encode_message(payload)
    if not text.endswith("\n"):
        text += "\n"
    with write_lock:
        sys.stdout.write(text)
        sys.stdout.flush()


if __name__ == "__main__":
    raise SystemExit(main())
