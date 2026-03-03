"""Run manifest model and JSON serialization contract."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, cast

from app.core import constants
from app.core.errors import RunManifestValidationError

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
    safe_mode: bool = True
    timestamp: str = ""
    breakpoints: list[dict[str, int | str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifest_version": self.manifest_version,
            "run_id": self.run_id,
            "project_root": self.project_root,
            "entry_file": self.entry_file,
            "working_directory": self.working_directory,
            "log_file": self.log_file,
            "mode": self.mode,
            "argv": list(self.argv),
            "env": dict(self.env),
            "safe_mode": self.safe_mode,
            "timestamp": self.timestamp,
            "breakpoints": [dict(entry) for entry in self.breakpoints],
        }


def parse_run_manifest(payload: dict[str, Any], *, manifest_path: Path | None = None) -> RunManifest:
    """Validate and parse JSON payload into a run manifest model."""
    if not isinstance(payload, dict):
        _raise_manifest_error("Run manifest payload must be a JSON object.", manifest_path=manifest_path)

    manifest_version = _require_int(payload, "manifest_version", manifest_path=manifest_path)
    if manifest_version != constants.RUN_MANIFEST_VERSION:
        _raise_manifest_error(
            f"Unsupported manifest_version: {manifest_version}. Expected {constants.RUN_MANIFEST_VERSION}.",
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
            f"Unsupported mode: {mode}. Allowed values: {sorted(ALLOWED_RUN_MODES)}.",
            field="mode",
            manifest_path=manifest_path,
        )

    argv = payload.get("argv", [])
    if not isinstance(argv, list) or not all(isinstance(item, str) for item in argv):
        _raise_manifest_error("argv must be a list of strings.", field="argv", manifest_path=manifest_path)

    env = payload.get("env", {})
    if not isinstance(env, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in env.items()):
        _raise_manifest_error("env must be an object of string key/value pairs.", field="env", manifest_path=manifest_path)

    safe_mode = payload.get("safe_mode", True)
    if not isinstance(safe_mode, bool):
        _raise_manifest_error("safe_mode must be a boolean.", field="safe_mode", manifest_path=manifest_path)

    timestamp = _require_non_empty_string(payload, "timestamp", manifest_path=manifest_path)
    breakpoints = _parse_breakpoints(payload.get("breakpoints", []), manifest_path=manifest_path)

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
        safe_mode=safe_mode,
        timestamp=timestamp,
        breakpoints=breakpoints,
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
            f"Invalid JSON in run manifest: {exc.msg} (line {exc.lineno}, column {exc.colno}).",
            manifest_path=manifest_path,
        )
    except OSError as exc:
        _raise_manifest_error(f"Unable to read run manifest: {exc}", manifest_path=manifest_path)

    return parse_run_manifest(payload, manifest_path=manifest_path)


def save_run_manifest(path: str | Path, manifest: RunManifest) -> Path:
    """Persist run manifest with deterministic formatting."""
    manifest_path = Path(path).expanduser().resolve()
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest_path


def _require_int(payload: dict[str, Any], field: str, *, manifest_path: Path | None) -> int:
    if field not in payload:
        _raise_manifest_error(f"Missing required field: {field}.", field=field, manifest_path=manifest_path)
    value = payload[field]
    if not isinstance(value, int) or isinstance(value, bool):
        _raise_manifest_error(f"{field} must be an integer.", field=field, manifest_path=manifest_path)
    return value


def _require_non_empty_string(payload: dict[str, Any], field: str, *, manifest_path: Path | None) -> str:
    if field not in payload:
        _raise_manifest_error(f"Missing required field: {field}.", field=field, manifest_path=manifest_path)
    value = payload[field]
    if not isinstance(value, str) or not value.strip():
        _raise_manifest_error(f"{field} must be a non-empty string.", field=field, manifest_path=manifest_path)
    return value


def _require_absolute_path(payload: dict[str, Any], field: str, *, manifest_path: Path | None) -> str:
    path_value = _require_non_empty_string(payload, field, manifest_path=manifest_path)
    candidate = Path(path_value).expanduser()
    if not candidate.is_absolute():
        _raise_manifest_error(f"{field} must be an absolute path.", field=field, manifest_path=manifest_path)
    return str(candidate.resolve())


def _raise_manifest_error(message: str, *, field: str | None = None, manifest_path: Path | None = None) -> None:
    raise RunManifestValidationError(message, field=field, manifest_path=manifest_path)


def _parse_breakpoints(
    raw_breakpoints: object,
    *,
    manifest_path: Path | None,
) -> list[dict[str, int | str]]:
    if not isinstance(raw_breakpoints, list):
        _raise_manifest_error("breakpoints must be a list.", field="breakpoints", manifest_path=manifest_path)

    normalized: list[dict[str, int | str]] = []
    for index, entry in enumerate(cast(list[object], raw_breakpoints)):
        if not isinstance(entry, dict):
            _raise_manifest_error(
                f"breakpoints[{index}] must be an object with file_path and line_number.",
                field="breakpoints",
                manifest_path=manifest_path,
            )
        entry_dict = cast(dict[str, object], entry)
        file_path = entry_dict.get("file_path")
        line_number = entry_dict.get("line_number")
        if not isinstance(file_path, str) or not file_path.strip():
            _raise_manifest_error(
                f"breakpoints[{index}].file_path must be a non-empty string.",
                field="breakpoints",
                manifest_path=manifest_path,
            )
        if not isinstance(line_number, int) or line_number <= 0:
            _raise_manifest_error(
                f"breakpoints[{index}].line_number must be a positive integer.",
                field="breakpoints",
                manifest_path=manifest_path,
            )
        normalized_file_path = cast(str, file_path)
        normalized_line_number = cast(int, line_number)
        normalized.append(
            {
                "file_path": str(Path(normalized_file_path).expanduser().resolve()),
                "line_number": normalized_line_number,
            }
        )
    return normalized
