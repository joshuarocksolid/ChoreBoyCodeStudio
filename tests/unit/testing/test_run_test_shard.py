"""Unit tests for the named test shard runner."""

from __future__ import annotations

import subprocess
import sys

import pytest

from testing import run_test_shard

pytestmark = pytest.mark.unit


def test_build_command_targets_unit_shard() -> None:
    command = run_test_shard.build_command("unit", python_executable="/usr/bin/python3")

    assert command == [
        "/usr/bin/python3",
        str(run_test_shard.RUN_TESTS_PATH),
        "-q",
        "--import-mode=importlib",
        "tests/unit",
    ]


def test_build_command_excludes_performance_from_integration() -> None:
    command = run_test_shard.build_command("integration", python_executable="/usr/bin/python3")

    assert command == [
        "/usr/bin/python3",
        str(run_test_shard.RUN_TESTS_PATH),
        "-q",
        "--import-mode=importlib",
        "tests/integration",
        "--ignore=tests/integration/performance",
    ]


def test_build_command_allows_pytest_passthrough_args() -> None:
    command = run_test_shard.build_command(
        "performance",
        python_executable="/usr/bin/python3",
        extra_pytest_args=["--durations=10"],
    )

    assert command == [
        "/usr/bin/python3",
        str(run_test_shard.RUN_TESTS_PATH),
        "-q",
        "--import-mode=importlib",
        "tests/integration/performance",
        "--durations=10",
    ]


def test_main_sets_worker_env_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(args=command, returncode=0)

    monkeypatch.setattr(run_test_shard.subprocess, "run", fake_run)

    exit_code = run_test_shard.main(["runtime_parity", "--workers", "4"])

    assert exit_code == 0
    assert captured["command"] == [
        sys.executable,
        str(run_test_shard.RUN_TESTS_PATH),
        "-q",
        "--import-mode=importlib",
        "tests/runtime_parity",
    ]
    kwargs = captured["kwargs"]
    assert kwargs["cwd"] == str(run_test_shard.REPO_ROOT)
    env = kwargs["env"]
    assert env[run_test_shard.PYTEST_WORKERS_ENV_VAR] == "4"


def test_main_strips_remainder_separator_for_pytest_args(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        return subprocess.CompletedProcess(args=command, returncode=0)

    monkeypatch.setattr(run_test_shard.subprocess, "run", fake_run)

    exit_code = run_test_shard.main(["unit", "--", "-k", "test_config"])

    assert exit_code == 0
    assert captured["command"] == [
        sys.executable,
        str(run_test_shard.RUN_TESTS_PATH),
        "-q",
        "--import-mode=importlib",
        "tests/unit",
        "-k",
        "test_config",
    ]
