"""Unit tests for the dev-only FreeCAD launcher helper."""

from pathlib import Path
import subprocess

import pytest

import dev_launch_editor

pytestmark = pytest.mark.unit


def test_build_apprun_command_bootstraps_repo_root_and_executes_editor_boot(tmp_path: Path) -> None:
    """Generated payload should make repo imports deterministic before boot."""
    app_run = tmp_path / "AppRun"
    editor_boot = tmp_path / "run_editor.py"
    command = dev_launch_editor.build_apprun_command(app_run_path=app_run, editor_boot_path=editor_boot)
    payload = command[2]

    assert command[0] == str(app_run)
    assert command[1] == "-c"
    assert "import runpy, sys;" in payload
    assert f"repo_root={str(editor_boot.parent)!r};" in payload
    assert "sys.path.insert(0, repo_root) if repo_root not in sys.path else None;" in payload
    assert "runpy.run_path(" in payload
    assert str(editor_boot) in payload
    assert "run_name='__main__'" in payload


def test_resolve_apprun_path_prefers_cli_over_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """CLI option should override CBCS_APPRUN when both are provided."""
    cli_path = tmp_path / "cli-freecad"
    env_path = tmp_path / "env-freecad"
    monkeypatch.setenv(dev_launch_editor.APP_RUN_ENV_VAR, str(env_path))

    resolved = dev_launch_editor.resolve_apprun_path(str(cli_path))
    assert resolved == cli_path.resolve()


def test_resolve_apprun_path_uses_env_when_cli_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Environment override should be used when no CLI path is provided."""
    env_path = tmp_path / "env-freecad"
    monkeypatch.setenv(dev_launch_editor.APP_RUN_ENV_VAR, str(env_path))

    resolved = dev_launch_editor.resolve_apprun_path(None)
    assert resolved == env_path.resolve()


def test_resolve_apprun_path_uses_default_when_cli_and_env_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default should target /opt/freecad/AppRun parity runtime path."""
    monkeypatch.delenv(dev_launch_editor.APP_RUN_ENV_VAR, raising=False)

    resolved = dev_launch_editor.resolve_apprun_path(None)
    assert resolved == Path("/opt/freecad/AppRun")


def test_main_dry_run_prints_command_without_path_validation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Dry run should print command details even for missing AppRun path."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "run_editor.py").write_text("print('stub')\n", encoding="utf-8")

    monkeypatch.setattr(dev_launch_editor, "resolve_repo_root", lambda: repo_root)

    exit_code = dev_launch_editor.main(["--dry-run", "--apprun", str(tmp_path / "missing-app-run")])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Command:" in output
    assert str(repo_root / "run_editor.py") in output


def test_main_launches_detached_with_start_new_session(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Default launch mode should detach similarly to ChoreBoy launcher behavior."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "run_editor.py").write_text("print('stub')\n", encoding="utf-8")

    app_run = tmp_path / "AppRun"
    app_run.write_text("", encoding="utf-8")
    app_run.chmod(0o755)

    calls: dict[str, object] = {}

    class _FakeProcess:
        pid = 4242

    def fake_popen(command: list[str], **kwargs: object) -> _FakeProcess:
        calls["command"] = command
        calls["kwargs"] = kwargs
        return _FakeProcess()

    monkeypatch.setattr(dev_launch_editor, "resolve_repo_root", lambda: repo_root)
    monkeypatch.setattr(dev_launch_editor.subprocess, "Popen", fake_popen)

    exit_code = dev_launch_editor.main(["--apprun", str(app_run)])

    assert exit_code == 0
    assert calls["command"] is not None
    kwargs = calls["kwargs"]
    assert kwargs["start_new_session"] is True
    assert kwargs["cwd"] == str(repo_root)


def test_main_foreground_returns_child_exit_code(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Foreground mode should return the child runtime exit code."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "run_editor.py").write_text("print('stub')\n", encoding="utf-8")

    app_run = tmp_path / "AppRun"
    app_run.write_text("", encoding="utf-8")
    app_run.chmod(0o755)

    calls: dict[str, object] = {}

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls["command"] = command
        calls["kwargs"] = kwargs
        return subprocess.CompletedProcess(args=command, returncode=17)

    monkeypatch.setattr(dev_launch_editor, "resolve_repo_root", lambda: repo_root)
    monkeypatch.setattr(dev_launch_editor.subprocess, "run", fake_run)

    exit_code = dev_launch_editor.main(["--foreground", "--apprun", str(app_run)])

    assert exit_code == 17
    kwargs = calls["kwargs"]
    assert kwargs["check"] is False
    assert kwargs["cwd"] == str(repo_root)


def test_main_returns_actionable_error_when_apprun_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Missing AppRun path should fail with clear guidance."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "run_editor.py").write_text("print('stub')\n", encoding="utf-8")
    missing = tmp_path / "missing-app-run"

    monkeypatch.setattr(dev_launch_editor, "resolve_repo_root", lambda: repo_root)

    exit_code = dev_launch_editor.main(["--apprun", str(missing)])
    error_output = capsys.readouterr().err

    assert exit_code == 2
    assert "not found" in error_output.lower()
    assert dev_launch_editor.APP_RUN_ENV_VAR in error_output
