"""Unit tests for runner debug bootstrap through execute_manifest."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core import constants
from app.debug.debug_models import DebugTransportConfig
from app.run.run_manifest import RunManifest
from app.runner.runner_main import execute_manifest

pytestmark = pytest.mark.unit


class _FakeTransport:
    instances: list["_FakeTransport"] = []

    def __init__(self, _config, *, engine_name: str, on_message, on_error) -> None:  # type: ignore[no-untyped-def]
        self.engine_name = engine_name
        self._on_message = on_message
        self._on_error = on_error
        type(self).instances.append(self)

    def connect(self) -> None:
        return None

    def send_message(self, message: dict[str, object]) -> None:
        if message.get("kind") == "event" and message.get("event") == "stopped":
            self._on_message(
                {
                    "kind": "command",
                    "command": "continue",
                    "command_id": "cmd_continue",
                    "arguments": {},
                }
            )

    def close(self) -> None:
        return None


def _build_qt_app_style_debug_manifest(tmp_path: Path) -> RunManifest:
    project_root = tmp_path / "project"
    app_dir = project_root / "app"
    app_dir.mkdir(parents=True)
    (app_dir / "__init__.py").write_text("", encoding="utf-8")
    (project_root / "main.py").write_text("print('DEBUG_OK')\n", encoding="utf-8")
    (project_root / "logs").mkdir(parents=True, exist_ok=True)

    return RunManifest(
        manifest_version=constants.RUN_MANIFEST_VERSION,
        run_id="run_debug_manifest",
        project_root=str(project_root.resolve()),
        entry_file="main.py",
        working_directory=str(project_root.resolve()),
        log_file=str((project_root / "logs" / "run_debug_manifest.log").resolve()),
        mode=constants.RUN_MODE_PYTHON_DEBUG,
        argv=(),
        env=(),
        timestamp="2026-03-01T01:01:01",
        debug_transport=DebugTransportConfig(
            protocol="cb-debug-v1",
            host="127.0.0.1",
            port=9000,
            session_token="token",
        ),
    )


def test_execute_manifest_debug_succeeds_with_user_app_package(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Debug bootstrap must survive user app/ shadowing apply_execution_context sys.path."""
    manifest = _build_qt_app_style_debug_manifest(tmp_path)
    _FakeTransport.instances.clear()
    monkeypatch.setattr(
        "app.runner.debug.command_loop.RunnerDebugTransportClient",
        _FakeTransport,
    )

    exit_code = execute_manifest(manifest)

    log_text = Path(manifest.log_file).read_text(encoding="utf-8")
    assert exit_code == constants.RUN_EXIT_SUCCESS
    assert "ModuleNotFoundError" not in log_text
    assert "app.runner" not in log_text
    assert "DEBUG_OK" in log_text
    assert _FakeTransport.instances
