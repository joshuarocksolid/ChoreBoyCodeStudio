"""Unit tests for run manifest contract helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.core import constants
from app.core.errors import RunManifestValidationError
from app.debug.debug_breakpoints import breakpoint_to_wire_dict, build_breakpoint
from app.debug.debug_models import DebugBreakpoint
from app.run.run_manifest import ReplControlConfig, RunManifest, load_run_manifest, parse_run_manifest, save_run_manifest

pytestmark = pytest.mark.unit


def _base_manifest(tmp_path: Path, *, breakpoints: tuple[DebugBreakpoint, ...] = ()) -> RunManifest:
    project_root = (tmp_path / "project").resolve()
    return RunManifest(
        manifest_version=constants.RUN_MANIFEST_VERSION,
        run_id="20260301_010101_ab12cd",
        project_root=str(project_root),
        entry_file="run.py",
        working_directory=str(project_root),
        log_file=str((project_root / "logs" / "run_20260301_010101_ab12cd.log").resolve()),
        mode=constants.RUN_MODE_PYTHON_SCRIPT,
        argv=("--foo", "bar"),
        env=(("ENV_A", "1"),),
        timestamp="2026-03-01T01:01:01",
        breakpoints=breakpoints,
    )


@pytest.mark.parametrize(
    "breakpoint_kwargs",
    [
        {},
        {"condition": "x > 1"},
        {"hit_condition": 3},
        {"condition": "flag", "hit_condition": 2, "enabled": False},
        {"breakpoint_id": "bp_custom_99"},
    ],
)
def test_run_manifest_breakpoint_codec_round_trip(
    tmp_path: Path,
    breakpoint_kwargs: dict[str, Any],
) -> None:
    """Manifest save/load must preserve breakpoint wire shapes via the shared codec."""

    source_file = (tmp_path / "project" / "run.py").resolve()
    breakpoint = build_breakpoint(str(source_file), 12, **breakpoint_kwargs)
    manifest = _base_manifest(tmp_path, breakpoints=(breakpoint,))
    manifest_path = tmp_path / "manifest.json"

    save_run_manifest(manifest_path, manifest)
    loaded = load_run_manifest(manifest_path)

    assert loaded.breakpoints == (breakpoint,)

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["breakpoints"] == [breakpoint_to_wire_dict(breakpoint)]


def test_run_manifest_round_trip_save_and_load(tmp_path: Path) -> None:
    """Manifest save/load should preserve deterministic payload shape."""
    manifest = RunManifest(
        manifest_version=constants.RUN_MANIFEST_VERSION,
        run_id="20260301_010101_ab12cd",
        project_root=str((tmp_path / "project").resolve()),
        entry_file="run.py",
        working_directory=str((tmp_path / "project").resolve()),
        log_file=str((tmp_path / "project" / "logs" / "run_20260301_010101_ab12cd.log").resolve()),
        mode=constants.RUN_MODE_PYTHON_SCRIPT,
        argv=("--foo", "bar"),
        env=(("ENV_A", "1"),),
        timestamp="2026-03-01T01:01:01",
        breakpoints=(
            build_breakpoint(
                file_path=str((tmp_path / "project" / "run.py").resolve()),
                line_number=3,
            ),
        ),
    )
    manifest_path = tmp_path / "manifest.json"
    save_run_manifest(manifest_path, manifest)

    loaded = load_run_manifest(manifest_path)
    assert loaded == manifest


def test_parse_run_manifest_rejects_invalid_mode() -> None:
    """Unsupported run modes should fail with actionable validation details."""
    with pytest.raises(RunManifestValidationError, match="Unsupported mode"):
        parse_run_manifest(
            {
                "manifest_version": constants.RUN_MANIFEST_VERSION,
                "run_id": "run_1",
                "project_root": "/tmp/project",
                "entry_file": "run.py",
                "working_directory": "/tmp/project",
                "log_file": "/tmp/project/logs/run_1.log",
                "mode": "unknown",
                "argv": [],
                "env": {},
                "timestamp": "2026-03-01T01:01:01",
            }
        )


def test_parse_run_manifest_requires_absolute_paths() -> None:
    """Path fields must remain absolute to avoid cwd-coupled behavior."""
    with pytest.raises(RunManifestValidationError, match="project_root must be an absolute path"):
        parse_run_manifest(
            {
                "manifest_version": constants.RUN_MANIFEST_VERSION,
                "run_id": "run_1",
                "project_root": "relative/project",
                "entry_file": "run.py",
                "working_directory": "/tmp/project",
                "log_file": "/tmp/project/logs/run_1.log",
                "mode": constants.RUN_MODE_PYTHON_SCRIPT,
                "argv": [],
                "env": {},
                "timestamp": "2026-03-01T01:01:01",
            }
        )


def test_parse_run_manifest_validates_breakpoint_shape() -> None:
    """Breakpoint payloads must contain file path and positive line number."""
    with pytest.raises(RunManifestValidationError, match="line_number must be a positive integer"):
        parse_run_manifest(
            {
                "manifest_version": constants.RUN_MANIFEST_VERSION,
                "run_id": "run_1",
                "project_root": "/tmp/project",
                "entry_file": "run.py",
                "working_directory": "/tmp/project",
                "log_file": "/tmp/project/logs/run_1.log",
                "mode": constants.RUN_MODE_PYTHON_DEBUG,
                "argv": [],
                "env": {},
                "timestamp": "2026-03-01T01:01:01",
                "breakpoints": [{"file_path": "/tmp/project/run.py", "line_number": 0}],
            }
        )


def test_parse_run_manifest_requires_repl_control_for_repl_mode() -> None:
    """REPL manifests must include repl_control loopback config."""
    with pytest.raises(RunManifestValidationError, match="repl_control is required"):
        parse_run_manifest(
            {
                "manifest_version": constants.RUN_MANIFEST_VERSION,
                "run_id": "repl_1",
                "project_root": "/tmp/repl",
                "entry_file": "__repl__.py",
                "working_directory": "/tmp/repl",
                "log_file": "/tmp/repl/repl.log",
                "mode": constants.RUN_MODE_PYTHON_REPL,
                "argv": [],
                "env": {},
                "timestamp": "2026-04-28T10:00:00",
            }
        )


def test_parse_run_manifest_requires_debug_transport_for_debug_mode() -> None:
    """Debug manifests must include debug_transport loopback config."""
    with pytest.raises(RunManifestValidationError, match="debug_transport is required"):
        parse_run_manifest(
            {
                "manifest_version": constants.RUN_MANIFEST_VERSION,
                "run_id": "debug_1",
                "project_root": "/tmp/project",
                "entry_file": "run.py",
                "working_directory": "/tmp/project",
                "log_file": "/tmp/project/logs/debug_1.log",
                "mode": constants.RUN_MODE_PYTHON_DEBUG,
                "argv": [],
                "env": {},
                "timestamp": "2026-03-01T01:01:01",
            }
        )


def _loopback_transport_payload() -> dict[str, Any]:
    return {
        "protocol": "cbcs_loopback_v1",
        "host": "127.0.0.1",
        "port": 49123,
        "session_token": "session-token",
    }


def _minimal_manifest_payload(*, mode: str, **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "manifest_version": constants.RUN_MANIFEST_VERSION,
        "run_id": "run_1",
        "project_root": "/tmp/project",
        "entry_file": "run.py",
        "working_directory": "/tmp/project",
        "log_file": "/tmp/project/logs/run_1.log",
        "mode": mode,
        "argv": [],
        "env": {},
        "timestamp": "2026-03-01T01:01:01",
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize(
    ("mode", "field_name", "overrides"),
    [
        (
            constants.RUN_MODE_PYTHON_SCRIPT,
            "debug_transport",
            {"debug_transport": _loopback_transport_payload()},
        ),
        (
            constants.RUN_MODE_PYTHON_SCRIPT,
            "repl_control",
            {"repl_control": _loopback_transport_payload()},
        ),
        (
            constants.RUN_MODE_PYTHON_REPL,
            "debug_transport",
            {
                "debug_transport": _loopback_transport_payload(),
                "repl_control": _loopback_transport_payload(),
            },
        ),
    ],
)
def test_parse_run_manifest_rejects_forbidden_mode_fields(
    mode: str,
    field_name: str,
    overrides: dict[str, Any],
) -> None:
    """Cross-mode transport fields must be rejected at the manifest boundary."""
    with pytest.raises(RunManifestValidationError, match=f"{field_name} is not allowed"):
        parse_run_manifest(_minimal_manifest_payload(mode=mode, **overrides))


def test_parse_run_manifest_uses_immutable_tuple_containers() -> None:
    """Parsed argv/env/breakpoints must be tuples, not mutable list/dict aliases."""
    manifest = parse_run_manifest(
        _minimal_manifest_payload(
            mode=constants.RUN_MODE_PYTHON_SCRIPT,
            argv=["--foo"],
            env={"ENV_A": "1"},
            breakpoints=[{"file_path": "/tmp/project/run.py", "line_number": 3}],
        )
    )

    assert isinstance(manifest.argv, tuple)
    assert isinstance(manifest.env, tuple)
    assert isinstance(manifest.breakpoints, tuple)
    assert manifest.argv == ("--foo",)
    assert manifest.env == (("ENV_A", "1"),)


def test_run_manifest_tuple_fields_resist_shallow_mutation() -> None:
    """Frozen tuple containers must not expose list/dict mutation hooks."""
    manifest = _base_manifest(Path("/tmp"))

    with pytest.raises(AttributeError):
        manifest.argv.append("injected")  # type: ignore[attr-defined]


def test_run_manifest_round_trips_repl_control_config(tmp_path: Path) -> None:
    manifest = RunManifest(
        manifest_version=constants.RUN_MANIFEST_VERSION,
        run_id="repl_1",
        project_root=str((tmp_path / "repl").resolve()),
        entry_file="__repl__.py",
        working_directory=str(tmp_path.resolve()),
        log_file=str((tmp_path / "repl.log").resolve()),
        mode=constants.RUN_MODE_PYTHON_REPL,
        timestamp="2026-04-28T10:00:00",
        repl_control=ReplControlConfig(
            protocol="cbcs_repl_control_v1",
            host="127.0.0.1",
            port=49123,
            session_token="token",
            connect_timeout_ms=800,
        ),
    )

    parsed = parse_run_manifest(manifest.to_dict())

    assert parsed == manifest
