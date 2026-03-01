"""Unit tests for keyed shell background task runner."""

from __future__ import annotations

import threading
import time

import pytest

from app.shell.background_tasks import BackgroundTaskRunner

pytestmark = pytest.mark.unit


def test_background_task_runner_dispatches_success_callback() -> None:
    seen: list[int] = []
    done = threading.Event()
    runner = BackgroundTaskRunner(dispatch_to_main_thread=lambda callback: callback())

    runner.run(
        key="health",
        task=lambda _cancel: 42,
        on_success=lambda result: (seen.append(result), done.set()),
    )

    assert done.wait(timeout=1.0)
    assert seen == [42]


def test_background_task_runner_cancels_previous_task_for_same_key() -> None:
    seen: list[int] = []
    done = threading.Event()
    gate = threading.Event()
    runner = BackgroundTaskRunner(dispatch_to_main_thread=lambda callback: callback())

    def slow_task(cancel_event: threading.Event) -> int:
        gate.wait(timeout=1.0)
        if cancel_event.is_set():
            return -1
        return 1

    runner.run(key="search", task=slow_task, on_success=lambda result: seen.append(result))
    runner.run(
        key="search",
        task=lambda _cancel: 2,
        on_success=lambda result: (seen.append(result), done.set()),
    )

    gate.set()
    assert done.wait(timeout=1.0)
    time.sleep(0.05)
    assert seen == [2]


def test_background_task_runner_routes_errors() -> None:
    errors: list[str] = []
    done = threading.Event()
    runner = BackgroundTaskRunner(dispatch_to_main_thread=lambda callback: callback())

    runner.run(
        key="bundle",
        task=lambda _cancel: (_ for _ in ()).throw(RuntimeError("boom")),
        on_error=lambda exc: (errors.append(str(exc)), done.set()),
    )

    assert done.wait(timeout=1.0)
    assert errors == ["boom"]
