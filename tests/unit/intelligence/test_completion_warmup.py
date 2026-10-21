"""Completion warmup is queued on the semantic worker and does not block."""

from __future__ import annotations

import threading
import time

import pytest

from app.intelligence.semantic_session import SemanticSession

pytestmark = pytest.mark.unit


def test_completion_warmup_returns_before_the_work_and_runs_off_the_caller() -> None:
    session = SemanticSession(
        dispatch_to_main_thread=lambda callback: callback(),
        cache_db_path=":memory:",
    )
    started = threading.Event()
    release = threading.Event()
    threads: list[int] = []

    def repl_warm() -> bool:
        threads.append(threading.get_ident())
        started.set()
        release.wait(5)
        return True

    caller = threading.get_ident()
    started_at = time.perf_counter()
    session.request_completion_warmup(project_root=None, repl_warm=repl_warm)
    elapsed = time.perf_counter() - started_at
    try:
        assert elapsed < 0.1
        assert started.wait(15)
        assert len(threads) == 1
        assert threads[0] != caller
    finally:
        release.set()
        session.shutdown()
