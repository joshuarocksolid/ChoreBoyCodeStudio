"""Unit tests for run_runner.py CLI entrypoint."""

import pytest

import run_runner

pytestmark = pytest.mark.unit


def test_parse_args_requires_manifest_flag() -> None:
    """Runner CLI should require --manifest argument."""
    with pytest.raises(SystemExit):
        run_runner.parse_args([])


def test_main_forwards_manifest_path_to_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    """Entrypoint should delegate execution to runner_main with manifest path."""
    called: dict[str, str] = {}

    def fake_run_from_manifest_path(path: str) -> int:
        called["path"] = path
        return 7

    monkeypatch.setattr(run_runner, "run_from_manifest_path", fake_run_from_manifest_path)

    exit_code = run_runner.main(["--manifest", "/tmp/manifest.json"])
    assert exit_code == 7
    assert called["path"] == "/tmp/manifest.json"
