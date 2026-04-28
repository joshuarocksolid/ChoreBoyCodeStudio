"""Run manifest model and JSON serialization contract."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Mapping, NoReturn, cast

from app.core import constants
from app.core.errors import RunManifestValidationError
from app.debug.debug_breakpoints import build_breakpoint
from app.debug.debug_models import (
    DebugBreakpoint,
    DebugExceptionPolicy,
    DebugSourceMap,
    DebugTransportConfig,
)

ALLOWED_RUN_MODES = frozenset(
    {
        constants.RUN_MODE_PYTHON_SCRIPT,
        constants.RUN_MODE_PYTHON_REPL,
        constants.RUN_MODE_PYTHON_DEBUG,
    }
)


@dataclass(frozen=True)
class RunManifest:
    """Canonical editor->runner contract for one run execution."""

    manifest_version: int
    run_id: str
    project_root: str
    entry_file: str
    working_directory: str
    log_file: str
    mode: str
    argv: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    timestamp: str = ""
    breakpoints: list[DebugBreakpoint] = field(default_factory=list)
    debug_transport: DebugTransportConfig | None = None
    repl_control: ReplControlConfig | None = None
    debug_exception_policy: DebugExceptionPolicy = field(default_factory=DebugExceptionPolicy)
    source_maps: list[DebugSourceMap] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "manifest_version": self.manifest_version,
            "run_id": self.run_id,
            "project_root": self.project_root,
            "entry_file": self.entry_file,
            "working_directory": self.working_directory,
            "log_file": self.log_file,
            "mode": self.mode,
            "argv": list(self.argv),
            "env": dict(self.env),
            "timestamp": self.timestamp,
            "breakpoints": [
                {
                    "breakpoint_id": breakpoint.breakpoint_id,
                    "file_path": breakpoint.file_path,
                    "line_number": breakpoint.line_number,
                    "enabled": breakpoint.enabled,
                    "condition": breakpoint.condition,
                    "hit_condition": breakpoint.hit_condition,
                }
                for breakpoint in self.breakpoints
            ],
            "debug_exception_policy": {
                "stop_on_uncaught_exceptions": self.debug_exception_policy.stop_on_uncaught_exceptions,
                "stop_on_raised_exceptions": self.debug_exception_policy.stop_on_raised_exceptions,
            },
            "source_maps": [
                {
                    "runtime_path": source_map.runtime_path,
                    "source_path": source_map.source_path,
                }
                for source_map in self.source_maps
            ],
        }
        if self.debug_transport is not None:
            payload["debug_transport"] = {
                "protocol": self.debug_transport.protocol,
                "host": self.debug_transport.host,
                "port": self.debug_transport.port,
                "session_token": self.debug_transport.session_token,
                "connect_timeout_ms": self.debug_transport.connect_timeout_ms,
            }
        if self.repl_control is not None:
            payload["repl_control"] = {
                "protocol": self.repl_control.protocol,
                "host": self.repl_control.host,
                "port": self.repl_control.port,
                "session_token": self.repl_control.session_token,
                "connect_timeout_ms": self.repl_control.connect_timeout_ms,
            }
        return payload


@dataclass(frozen=True)
class ReplControlConfig:
    """Loopback control channel for Python Console metadata requests."""

    protocol: str
    host: str
    port: int
    session_token: str
    connect_timeout_ms: int = 800


def parse_run_manifest(payload: dict[str, Any], *, manifest_path: Path | None = None) -> RunManifest:
    """Validate and parse JSON payload into a run manifest model."""

    if not isinstance(payload, dict):
        _raise_manifest_error("Run manifest payload must be a JSON object.", manifest_path=manifest_path)

    manifest_version = _require_int(payload, "manifest_version", manifest_path=manifest_path)
    if manifest_version != constants.RUN_MANIFEST_VERSION:
        _raise_manifest_error(
            "Unsupported manifest_version: %s. Expected %s."
            % (manifest_version, constants.RUN_MANIFEST_VERSION),
            field="manifest_version",
            manifest_path=manifest_path,
        )

    run_id = _require_non_empty_string(payload, "run_id", manifest_path=manifest_path)
    project_root = _require_absolute_path(payload, "project_root", manifest_path=manifest_path)
    entry_file = _require_non_empty_string(payload, "entry_file", manifest_path=manifest_path)
    working_directory = _require_absolute_path(payload, "working_directory", manifest_path=manifest_path)
    log_file = _require_absolute_path(payload, "log_file", manifest_path=manifest_path)
    mode = _require_non_empty_string(payload, "mode", manifest_path=manifest_path)
    if mode not in ALLOWED_RUN_MODES:
        _raise_manifest_error(
            "Unsupported mode: %s. Allowed values: %s." % (mode, sorted(ALLOWED_RUN_MODES)),
            field="mode",
            manifest_path=manifest_path,
        )

    argv = payload.get("argv", [])
    if not isinstance(argv, list) or not all(isinstance(item, str) for item in argv):
        _raise_manifest_error("argv must be a list of strings.", field="argv", manifest_path=manifest_path)

    env = payload.get("env", {})
    if not isinstance(env, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in env.items()):
        _raise_manifest_error("env must be an object of string key/value pairs.", field="env", manifest_path=manifest_path)

    timestamp = _require_non_empty_string(payload, "timestamp", manifest_path=manifest_path)
    breakpoints = _parse_breakpoints(payload.get("breakpoints", []), manifest_path=manifest_path)
    debug_transport = _parse_debug_transport(payload.get("debug_transport"), manifest_path=manifest_path)
    repl_control = _parse_repl_control(payload.get("repl_control"), manifest_path=manifest_path)
    exception_policy = _parse_exception_policy(payload.get("debug_exception_policy"))
    source_maps = _parse_source_maps(payload.get("source_maps", []), manifest_path=manifest_path)

    if mode == constants.RUN_MODE_PYTHON_DEBUG and debug_transport is None:
        _raise_manifest_error(
            "debug_transport is required for python_debug manifests.",
            field="debug_transport",
            manifest_path=manifest_path,
        )

    return RunManifest(
        manifest_version=manifest_version,
        run_id=run_id,
        project_root=project_root,
        entry_file=entry_file,
        working_directory=working_directory,
        log_file=log_file,
        mode=mode,
        argv=list(argv),
        env=dict(env),
        timestamp=timestamp,
        breakpoints=breakpoints,
        debug_transport=debug_transport,
        repl_control=repl_control,
        debug_exception_policy=exception_policy,
        source_maps=source_maps,
    )


def load_run_manifest(path: str | Path) -> RunManifest:
    """Load manifest file from disk."""

    manifest_path = Path(path).expanduser().resolve()
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        _raise_manifest_error("Run manifest file not found.", manifest_path=manifest_path)
    except json.JSONDecodeError as exc:
        _raise_manifest_error(
            "Invalid JSON in run manifest: %s (line %s, column %s)." % (exc.msg, exc.lineno, exc.colno),
            manifest_path=manifest_path,
        )
    except OSError as exc:
        _raise_manifest_error("Unable to read run manifest: %s" % (exc,), manifest_path=manifest_path)

    return parse_run_manifest(payload, manifest_path=manifest_path)


def save_run_manifest(path: str | Path, manifest: RunManifest) -> Path:
    """Persist run manifest with deterministic formatting."""

    manifest_path = Path(path).expanduser().resolve()
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest_path


def _require_int(payload: dict[str, Any], field: str, *, manifest_path: Path | None) -> int:
    if field not in payload:
        _raise_manifest_error("Missing required field: %s." % (field,), field=field, manifest_path=manifest_path)
    value = payload[field]
    if not isinstance(value, int) or isinstance(value, bool):
        _raise_manifest_error("%s must be an integer." % (field,), field=field, manifest_path=manifest_path)
    return value


def _require_non_empty_string(payload: dict[str, Any], field: str, *, manifest_path: Path | None) -> str:
    if field not in payload:
        _raise_manifest_error("Missing required field: %s." % (field,), field=field, manifest_path=manifest_path)
    value = payload[field]
    if not isinstance(value, str) or not value.strip():
        _raise_manifest_error("%s must be a non-empty string." % (field,), field=field, manifest_path=manifest_path)
    return value


def _require_absolute_path(payload: dict[str, Any], field: str, *, manifest_path: Path | None) -> str:
    path_value = _require_non_empty_string(payload, field, manifest_path=manifest_path)
    candidate = Path(path_value).expanduser()
    if not candidate.is_absolute():
        _raise_manifest_error("%s must be an absolute path." % (field,), field=field, manifest_path=manifest_path)
    return str(candidate.resolve())


def _raise_manifest_error(
    message: str,
    *,
    field: str | None = None,
    manifest_path: Path | None = None,
) -> NoReturn:
    raise RunManifestValidationError(message, field=field, manifest_path=manifest_path)


def _parse_breakpoints(
    raw_breakpoints: object,
    *,
    manifest_path: Path | None,
) -> list[DebugBreakpoint]:
    if not isinstance(raw_breakpoints, list):
        _raise_manifest_error("breakpoints must be a list.", field="breakpoints", manifest_path=manifest_path)

    normalized: list[DebugBreakpoint] = []
    for index, entry in enumerate(cast(list[object], raw_breakpoints)):
        if not isinstance(entry, Mapping):
            _raise_manifest_error(
                "breakpoints[%s] must be an object." % (index,),
                field="breakpoints",
                manifest_path=manifest_path,
            )
        file_path = entry.get("file_path")
        line_number = entry.get("line_number")
        if not isinstance(file_path, str) or not file_path.strip():
            _raise_manifest_error(
                "breakpoints[%s].file_path must be a non-empty string." % (index,),
                field="breakpoints",
                manifest_path=manifest_path,
            )
        if not isinstance(line_number, int) or line_number <= 0:
            _raise_manifest_error(
                "breakpoints[%s].line_number must be a positive integer." % (index,),
                field="breakpoints",
                manifest_path=manifest_path,
            )
        normalized.append(
            build_breakpoint(
                file_path=str(file_path),
                line_number=int(line_number),
                breakpoint_id=str(entry.get("breakpoint_id", "")).strip() or None,
                enabled=bool(entry.get("enabled", True)),
                condition=str(entry.get("condition", "")).strip(),
                hit_condition=_parse_optional_positive_int(entry.get("hit_condition")),
            )
        )
    return normalized


def _parse_debug_transport(raw_value: object, *, manifest_path: Path | None) -> DebugTransportConfig | None:
    if raw_value is None:
        return None
    if not isinstance(raw_value, Mapping):
        _raise_manifest_error("debug_transport must be an object.", field="debug_transport", manifest_path=manifest_path)
    protocol = str(raw_value.get("protocol", "")).strip()
    host = str(raw_value.get("host", "")).strip()
    port = _parse_optional_positive_int(raw_value.get("port"))
    session_token = str(raw_value.get("session_token", "")).strip()
    connect_timeout_ms = _parse_optional_positive_int(raw_value.get("connect_timeout_ms")) or 8000
    if not protocol or not host or port is None or not session_token:
        _raise_manifest_error(
            "debug_transport requires protocol, host, port, and session_token.",
            field="debug_transport",
            manifest_path=manifest_path,
        )
    return DebugTransportConfig(
        protocol=protocol,
        host=host,
        port=port,
        session_token=session_token,
        connect_timeout_ms=connect_timeout_ms,
    )


def _parse_repl_control(raw_value: object, *, manifest_path: Path | None) -> ReplControlConfig | None:
    if raw_value is None:
        return None
    if not isinstance(raw_value, Mapping):
        _raise_manifest_error("repl_control must be an object.", field="repl_control", manifest_path=manifest_path)
    protocol = str(raw_value.get("protocol", "")).strip()
    host = str(raw_value.get("host", "")).strip()
    port = _parse_optional_positive_int(raw_value.get("port"))
    session_token = str(raw_value.get("session_token", "")).strip()
    connect_timeout_ms = _parse_optional_positive_int(raw_value.get("connect_timeout_ms")) or 800
    if not protocol or not host or port is None or not session_token:
        _raise_manifest_error(
            "repl_control requires protocol, host, port, and session_token.",
            field="repl_control",
            manifest_path=manifest_path,
        )
    return ReplControlConfig(
        protocol=protocol,
        host=host,
        port=port,
        session_token=session_token,
        connect_timeout_ms=connect_timeout_ms,
    )


def _parse_exception_policy(raw_value: object) -> DebugExceptionPolicy:
    if not isinstance(raw_value, Mapping):
        return DebugExceptionPolicy()
    return DebugExceptionPolicy(
        stop_on_uncaught_exceptions=bool(raw_value.get("stop_on_uncaught_exceptions", True)),
        stop_on_raised_exceptions=bool(raw_value.get("stop_on_raised_exceptions", False)),
    )


def _parse_source_maps(
    raw_value: object,
    *,
    manifest_path: Path | None,
) -> list[DebugSourceMap]:
    if not isinstance(raw_value, list):
        _raise_manifest_error("source_maps must be a list.", field="source_maps", manifest_path=manifest_path)
    source_maps: list[DebugSourceMap] = []
    for index, entry in enumerate(cast(list[object], raw_value)):
        if not isinstance(entry, Mapping):
            _raise_manifest_error(
                "source_maps[%s] must be an object." % (index,),
                field="source_maps",
                manifest_path=manifest_path,
            )
        runtime_path = entry.get("runtime_path")
        source_path = entry.get("source_path")
        if not isinstance(runtime_path, str) or not runtime_path.strip():
            _raise_manifest_error(
                "source_maps[%s].runtime_path must be a non-empty string." % (index,),
                field="source_maps",
                manifest_path=manifest_path,
            )
        if not isinstance(source_path, str) or not source_path.strip():
            _raise_manifest_error(
                "source_maps[%s].source_path must be a non-empty string." % (index,),
                field="source_maps",
                manifest_path=manifest_path,
            )
        source_maps.append(
            DebugSourceMap(
                runtime_path=str(Path(runtime_path).expanduser().resolve()),
                source_path=str(Path(source_path).expanduser().resolve()),
            )
        )
    return source_maps


def _parse_optional_positive_int(raw_value: object) -> int | None:
    if raw_value is None:
        return None
    if isinstance(raw_value, int) and not isinstance(raw_value, bool) and raw_value > 0:
        return int(raw_value)
    try:
        parsed = int(str(raw_value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None
