"""Run manifest model and JSON serialization contract."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Mapping, NoReturn, cast

from app.core import constants
from app.core.errors import RunManifestValidationError
from app.debug.debug_breakpoints import breakpoint_to_wire_dict, parse_breakpoint_entry
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

_MODE_REQUIRED_FIELDS: dict[str, frozenset[str]] = {
    constants.RUN_MODE_PYTHON_DEBUG: frozenset({"debug_transport"}),
    constants.RUN_MODE_PYTHON_REPL: frozenset({"repl_control"}),
}

_MODE_FORBIDDEN_FIELDS: dict[str, frozenset[str]] = {
    constants.RUN_MODE_PYTHON_SCRIPT: frozenset({"debug_transport", "repl_control"}),
    constants.RUN_MODE_PYTHON_REPL: frozenset({"debug_transport"}),
}


@dataclass(frozen=True)
class LoopbackTransportConfig:
    """Shared loopback socket contract for debug and REPL control channels."""

    protocol: str
    host: str
    port: int
    session_token: str
    connect_timeout_ms: int = 8000

    def to_wire_dict(self) -> dict[str, Any]:
        return {
            "protocol": self.protocol,
            "host": self.host,
            "port": self.port,
            "session_token": self.session_token,
            "connect_timeout_ms": self.connect_timeout_ms,
        }


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
    argv: tuple[str, ...] = field(default_factory=tuple)
    env: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    timestamp: str = ""
    breakpoints: tuple[DebugBreakpoint, ...] = field(default_factory=tuple)
    debug_transport: DebugTransportConfig | None = None
    repl_control: ReplControlConfig | None = None
    debug_exception_policy: DebugExceptionPolicy = field(default_factory=DebugExceptionPolicy)
    source_maps: tuple[DebugSourceMap, ...] = field(default_factory=tuple)

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
            "breakpoints": [breakpoint_to_wire_dict(breakpoint) for breakpoint in self.breakpoints],
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
            payload["debug_transport"] = LoopbackTransportConfig(
                protocol=self.debug_transport.protocol,
                host=self.debug_transport.host,
                port=self.debug_transport.port,
                session_token=self.debug_transport.session_token,
                connect_timeout_ms=self.debug_transport.connect_timeout_ms,
            ).to_wire_dict()
        if self.repl_control is not None:
            payload["repl_control"] = LoopbackTransportConfig(
                protocol=self.repl_control.protocol,
                host=self.repl_control.host,
                port=self.repl_control.port,
                session_token=self.repl_control.session_token,
                connect_timeout_ms=self.repl_control.connect_timeout_ms,
            ).to_wire_dict()
        return payload


@dataclass(frozen=True)
class ReplControlConfig:
    """Loopback control channel for Python Console metadata requests."""

    protocol: str
    host: str
    port: int
    session_token: str
    connect_timeout_ms: int = 800

    @classmethod
    def from_loopback(cls, config: LoopbackTransportConfig) -> ReplControlConfig:
        return cls(
            protocol=config.protocol,
            host=config.host,
            port=config.port,
            session_token=config.session_token,
            connect_timeout_ms=config.connect_timeout_ms,
        )


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

    argv = _parse_argv(payload.get("argv", []), manifest_path=manifest_path)
    env = _parse_env(payload.get("env", {}), manifest_path=manifest_path)
    timestamp = _require_non_empty_string(payload, "timestamp", manifest_path=manifest_path)
    breakpoints = _parse_breakpoints(payload.get("breakpoints", []), manifest_path=manifest_path)
    debug_transport = _parse_loopback_transport(
        payload.get("debug_transport"),
        manifest_path=manifest_path,
        field_name="debug_transport",
    )
    repl_control_raw = _parse_loopback_transport(
        payload.get("repl_control"),
        manifest_path=manifest_path,
        field_name="repl_control",
    )
    repl_control = (
        ReplControlConfig.from_loopback(repl_control_raw)
        if repl_control_raw is not None
        else None
    )
    debug_transport_config = (
        DebugTransportConfig(
            protocol=debug_transport.protocol,
            host=debug_transport.host,
            port=debug_transport.port,
            session_token=debug_transport.session_token,
            connect_timeout_ms=debug_transport.connect_timeout_ms,
        )
        if debug_transport is not None
        else None
    )
    exception_policy = _parse_exception_policy(payload.get("debug_exception_policy"))
    source_maps = _parse_source_maps(payload.get("source_maps", []), manifest_path=manifest_path)

    _validate_mode_fields(
        mode,
        debug_transport=debug_transport is not None,
        repl_control=repl_control is not None,
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
        argv=argv,
        env=env,
        timestamp=timestamp,
        breakpoints=breakpoints,
        debug_transport=debug_transport_config,
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


def _parse_argv(raw_argv: object, *, manifest_path: Path | None) -> tuple[str, ...]:
    if not isinstance(raw_argv, list) or not all(isinstance(item, str) for item in raw_argv):
        _raise_manifest_error("argv must be a list of strings.", field="argv", manifest_path=manifest_path)
    return tuple(cast(list[str], raw_argv))


def _parse_env(raw_env: object, *, manifest_path: Path | None) -> tuple[tuple[str, str], ...]:
    if not isinstance(raw_env, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in raw_env.items()):
        _raise_manifest_error("env must be an object of string key/value pairs.", field="env", manifest_path=manifest_path)
    env_dict = cast(dict[str, str], raw_env)
    return tuple(sorted(env_dict.items()))


def _validate_mode_fields(
    mode: str,
    *,
    debug_transport: bool,
    repl_control: bool,
    manifest_path: Path | None,
) -> None:
    for field_name in _MODE_REQUIRED_FIELDS.get(mode, frozenset()):
        present = debug_transport if field_name == "debug_transport" else repl_control
        if not present:
            _raise_manifest_error(
                "%s is required for %s manifests." % (field_name, mode),
                field=field_name,
                manifest_path=manifest_path,
            )
    for field_name in _MODE_FORBIDDEN_FIELDS.get(mode, frozenset()):
        present = debug_transport if field_name == "debug_transport" else repl_control
        if present:
            _raise_manifest_error(
                "%s is not allowed for %s manifests." % (field_name, mode),
                field=field_name,
                manifest_path=manifest_path,
            )


def _parse_breakpoints(
    raw_breakpoints: object,
    *,
    manifest_path: Path | None,
) -> tuple[DebugBreakpoint, ...]:
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
        parsed = parse_breakpoint_entry(entry)
        if parsed is None:
            _raise_manifest_error(
                "breakpoints[%s] is invalid." % (index,),
                field="breakpoints",
                manifest_path=manifest_path,
            )
        normalized.append(parsed)
    return tuple(normalized)


def _parse_loopback_transport(
    raw_value: object,
    *,
    manifest_path: Path | None,
    field_name: str,
) -> LoopbackTransportConfig | None:
    if raw_value is None:
        return None
    if not isinstance(raw_value, Mapping):
        _raise_manifest_error("%s must be an object." % (field_name,), field=field_name, manifest_path=manifest_path)
    protocol = str(raw_value.get("protocol", "")).strip()
    host = str(raw_value.get("host", "")).strip()
    port = _parse_optional_positive_int(raw_value.get("port"))
    session_token = str(raw_value.get("session_token", "")).strip()
    default_timeout = 8000 if field_name == "debug_transport" else 800
    connect_timeout_ms = _parse_optional_positive_int(raw_value.get("connect_timeout_ms")) or default_timeout
    if not protocol or not host or port is None or not session_token:
        _raise_manifest_error(
            "%s requires protocol, host, port, and session_token." % (field_name,),
            field=field_name,
            manifest_path=manifest_path,
        )
    return LoopbackTransportConfig(
        protocol=protocol,
        host=host,
        port=port,
        session_token=session_token,
        connect_timeout_ms=connect_timeout_ms,
    )


def _parse_debug_transport(raw_value: object, *, manifest_path: Path | None) -> DebugTransportConfig | None:
    parsed = _parse_loopback_transport(raw_value, manifest_path=manifest_path, field_name="debug_transport")
    if parsed is None:
        return None
    return DebugTransportConfig(
        protocol=parsed.protocol,
        host=parsed.host,
        port=parsed.port,
        session_token=parsed.session_token,
        connect_timeout_ms=parsed.connect_timeout_ms,
    )


def _parse_repl_control(raw_value: object, *, manifest_path: Path | None) -> ReplControlConfig | None:
    parsed = _parse_loopback_transport(raw_value, manifest_path=manifest_path, field_name="repl_control")
    if parsed is None:
        return None
    return ReplControlConfig.from_loopback(parsed)


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
) -> tuple[DebugSourceMap, ...]:
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
    return tuple(source_maps)


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
