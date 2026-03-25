"""Unit tests for the AppRun pytest launcher wrapper."""

from __future__ import annotations

import sys

import pytest

import run_tests

pytestmark = pytest.mark.unit


def test_pytest_argv_prepends_import_mode_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CBCS_PYTEST_WORKERS", raising=False)
    monkeypatch.setattr(sys, "argv", ["run_tests.py", "tests/unit"])

    assert run_tests._pytest_argv() == ["--import-mode=importlib", "tests/unit"]


def test_pytest_argv_preserves_explicit_import_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CBCS_PYTEST_WORKERS", raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        ["run_tests.py", "--import-mode=append", "tests/unit"],
    )

    assert run_tests._pytest_argv() == ["--import-mode=append", "tests/unit"]


def test_pytest_argv_adds_worker_count_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CBCS_PYTEST_WORKERS", "auto")
    monkeypatch.setattr(sys, "argv", ["run_tests.py", "tests/unit"])

    assert run_tests._pytest_argv() == ["--import-mode=importlib", "-n", "auto", "tests/unit"]


def test_pytest_argv_ignores_blank_and_zero_worker_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "argv", ["run_tests.py", "tests/unit"])

    monkeypatch.setenv("CBCS_PYTEST_WORKERS", " ")
    assert run_tests._pytest_argv() == ["--import-mode=importlib", "tests/unit"]

    monkeypatch.setenv("CBCS_PYTEST_WORKERS", "0")
    assert run_tests._pytest_argv() == ["--import-mode=importlib", "tests/unit"]


def test_pytest_argv_does_not_override_explicit_parallelism(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CBCS_PYTEST_WORKERS", "auto")
    monkeypatch.setattr(sys, "argv", ["run_tests.py", "-n", "2", "tests/unit"])

    assert run_tests._pytest_argv() == ["--import-mode=importlib", "-n", "2", "tests/unit"]


def test_pytest_argv_recognizes_explicit_numprocesses_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CBCS_PYTEST_WORKERS", "auto")
    monkeypatch.setattr(
        sys,
        "argv",
        ["run_tests.py", "--numprocesses=3", "tests/unit"],
    )

    assert run_tests._pytest_argv() == ["--import-mode=importlib", "--numprocesses=3", "tests/unit"]
