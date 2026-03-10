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
    assert f"sys.path.insert(0, {str(editor_boot.parent)!r})" in payload
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


def test_resolve_artifacts_dir_uses_env_var(tmp_path: Path) -> None:
    """CBCS_ARTIFACTS_DIR env var should override the sibling convention."""
    custom_dir = tmp_path / "custom_artifacts"
    env = {dev_launch_editor.ARTIFACTS_DIR_ENV_VAR: str(custom_dir)}

    resolved = dev_launch_editor.resolve_artifacts_dir(repo_root=tmp_path, env=env)
    assert resolved == custom_dir.resolve()


def test_resolve_artifacts_dir_defaults_to_sibling(tmp_path: Path) -> None:
    """Without env var, artifacts dir should be a sibling of the repo root."""
    repo_root = tmp_path / "MyRepo"
    repo_root.mkdir()

    resolved = dev_launch_editor.resolve_artifacts_dir(repo_root=repo_root, env={})
    assert resolved == (tmp_path / dev_launch_editor.DEFAULT_ARTIFACTS_DIRNAME).resolve()


def test_ensure_vendor_symlink_creates_symlink(tmp_path: Path) -> None:
    """Symlink should be created when artifacts vendor exists but repo vendor does not."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    artifacts_dir = tmp_path / "artifacts"
    vendor_dir = artifacts_dir / "vendor"
    vendor_dir.mkdir(parents=True)
    (vendor_dir / "dummy.py").write_text("x = 1\n", encoding="utf-8")

    dev_launch_editor.ensure_vendor_symlink(repo_root, artifacts_dir)

    link = repo_root / "vendor"
    assert link.is_symlink()
    assert link.resolve() == vendor_dir.resolve()
    assert (link / "dummy.py").read_text(encoding="utf-8") == "x = 1\n"


def test_ensure_vendor_symlink_noop_when_vendor_already_exists(tmp_path: Path) -> None:
    """No symlink should be created when vendor/ already exists at repo root."""
    repo_root = tmp_path / "repo"
    existing_vendor = repo_root / "vendor"
    existing_vendor.mkdir(parents=True)
    (existing_vendor / "local.py").write_text("y = 2\n", encoding="utf-8")

    artifacts_dir = tmp_path / "artifacts"
    (artifacts_dir / "vendor").mkdir(parents=True)

    dev_launch_editor.ensure_vendor_symlink(repo_root, artifacts_dir)

    assert not existing_vendor.is_symlink()
    assert (existing_vendor / "local.py").read_text(encoding="utf-8") == "y = 2\n"


def test_ensure_vendor_symlink_warns_when_artifacts_vendor_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Missing artifacts vendor should warn but not crash."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir()

    dev_launch_editor.ensure_vendor_symlink(repo_root, artifacts_dir)

    assert not (repo_root / "vendor").exists()
    err = capsys.readouterr().err
    assert "not found" in err.lower()
    assert dev_launch_editor.ARTIFACTS_DIR_ENV_VAR in err


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
