"""Unit tests for the AppRun pytest launcher wrapper."""

from __future__ import annotations

import sys

import pytest

import run_tests

pytestmark = pytest.mark.unit


def _exclude_perf(*args: str) -> list[str]:
    return ["-m", "not performance", *args]


def test_pytest_argv_prepends_import_mode_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CBCS_PYTEST_WORKERS", raising=False)
    monkeypatch.setattr(sys, "argv", ["run_tests.py", "tests/unit"])

    assert run_tests._pytest_argv() == _exclude_perf("--import-mode=importlib", "tests/unit")


def test_pytest_argv_preserves_explicit_import_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CBCS_PYTEST_WORKERS", raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        ["run_tests.py", "--import-mode=append", "tests/unit"],
    )

    assert run_tests._pytest_argv() == _exclude_perf("--import-mode=append", "tests/unit")


def test_pytest_argv_adds_worker_count_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CBCS_PYTEST_WORKERS", "auto")
    monkeypatch.setattr(sys, "argv", ["run_tests.py", "tests/unit"])

    assert run_tests._pytest_argv() == _exclude_perf(
        "--import-mode=importlib", "-n", "auto", "tests/unit"
    )


def test_pytest_argv_ignores_blank_and_zero_worker_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "argv", ["run_tests.py", "tests/unit"])

    monkeypatch.setenv("CBCS_PYTEST_WORKERS", " ")
    assert run_tests._pytest_argv() == _exclude_perf("--import-mode=importlib", "tests/unit")

    monkeypatch.setenv("CBCS_PYTEST_WORKERS", "0")
    assert run_tests._pytest_argv() == _exclude_perf("--import-mode=importlib", "tests/unit")


def test_pytest_argv_does_not_override_explicit_parallelism(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CBCS_PYTEST_WORKERS", "auto")
    monkeypatch.setattr(sys, "argv", ["run_tests.py", "-n", "2", "tests/unit"])

    assert run_tests._pytest_argv() == _exclude_perf(
        "--import-mode=importlib", "-n", "2", "tests/unit"
    )


def test_pytest_argv_recognizes_explicit_numprocesses_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CBCS_PYTEST_WORKERS", "auto")
    monkeypatch.setattr(
        sys,
        "argv",
        ["run_tests.py", "--numprocesses=3", "tests/unit"],
    )

    assert run_tests._pytest_argv() == _exclude_perf(
        "--import-mode=importlib", "--numprocesses=3", "tests/unit"
    )


def test_pytest_argv_does_not_inject_perf_exclusion_when_marker_supplied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An explicit ``-m`` from the caller wins; the launcher must not double up."""
    monkeypatch.delenv("CBCS_PYTEST_WORKERS", raising=False)
    monkeypatch.setattr(
        sys, "argv", ["run_tests.py", "-m", "performance", "tests/integration"]
    )

    assert run_tests._pytest_argv() == [
        "--import-mode=importlib",
        "-m",
        "performance",
        "tests/integration",
    ]


def test_pytest_argv_does_not_inject_perf_exclusion_for_perf_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Selecting a perf path implies opting in; the launcher must not exclude it."""
    monkeypatch.delenv("CBCS_PYTEST_WORKERS", raising=False)
    monkeypatch.setattr(
        sys, "argv", ["run_tests.py", "tests/integration/performance/"]
    )

    assert run_tests._pytest_argv() == [
        "--import-mode=importlib",
        "tests/integration/performance/",
    ]
