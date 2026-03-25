"""Unit tests for serialized semantic worker behavior."""
from __future__ import annotations

import threading
import time

import pytest

from app.intelligence.semantic_worker import SemanticWorker

pytestmark = pytest.mark.unit


def test_semantic_worker_drops_stale_result_for_same_key() -> None:
    completed: list[str] = []
    release_first = threading.Event()
    worker = SemanticWorker(dispatch_to_main_thread=lambda callback: callback())

    try:
        worker.submit(
            key="definition",
            task=lambda: _blocked_result(release_first, "first"),
            on_success=lambda result: completed.append(result),
        )
        time.sleep(0.05)
        worker.submit(
            key="definition",
            task=lambda: "second",
            on_success=lambda result: completed.append(result),
        )
        release_first.set()
        deadline = time.time() + 2.0
        while time.time() < deadline and completed != ["second"]:
            time.sleep(0.02)
    finally:
        worker.shutdown()

    assert completed == ["second"]


def test_semantic_worker_runs_tasks_serially() -> None:
    order: list[str] = []
    release_first = threading.Event()
    worker = SemanticWorker(dispatch_to_main_thread=lambda callback: callback())

    def first_task() -> str:
        order.append("first-start")
        release_first.wait(timeout=1.0)
        order.append("first-end")
        return "first"

    def second_task() -> str:
        order.append("second-start")
        return "second"

    try:
        worker.submit(key="one", task=first_task, on_success=lambda _result: None)
        time.sleep(0.05)
        worker.submit(key="two", task=second_task, on_success=lambda _result: None)
        time.sleep(0.05)
        assert order == ["first-start"]
        release_first.set()
        deadline = time.time() + 2.0
        while time.time() < deadline and order != ["first-start", "first-end", "second-start"]:
            time.sleep(0.02)
    finally:
        worker.shutdown()

    assert order == ["first-start", "first-end", "second-start"]


def test_semantic_worker_call_runs_task_on_worker_thread() -> None:
    worker = SemanticWorker(dispatch_to_main_thread=lambda callback: callback())
    try:
        result = worker.call(key="hover_sync", task=lambda: "hover-result")
    finally:
        worker.shutdown()

    assert result == "hover-result"


def _blocked_result(release_event: threading.Event, value: str) -> str:
    release_event.wait(timeout=1.0)
    return value
