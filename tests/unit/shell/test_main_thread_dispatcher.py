"""Unit tests for GUI-thread callback dispatch wiring."""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtCore import QThread  # noqa: E402
from PySide2.QtWidgets import QApplication  # noqa: E402

from app.shell.main_thread_dispatcher import MainThreadDispatcher  # noqa: E402
from app.shell.main_window import MainWindow  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module", autouse=True)
def _qapp():  # type: ignore[no-untyped-def]
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _wait_for(predicate, *, timeout_seconds: float = 1.0) -> bool:
    app = QApplication.instance()
    assert app is not None
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    app.processEvents()
    return predicate()


class _LoggerStub:
    def __init__(self) -> None:
        self.info_calls: list[tuple[object, ...]] = []
        self.warning_calls: list[tuple[object, ...]] = []

    def info(self, *args: object) -> None:
        self.info_calls.append(args)

    def warning(self, *args: object) -> None:
        self.warning_calls.append(args)


def test_dispatcher_runs_callback_on_gui_thread() -> None:
    dispatcher = MainThreadDispatcher()
    done = threading.Event()
    seen_gui_thread: list[bool] = []

    def callback() -> None:
        app = QApplication.instance()
        assert app is not None
        seen_gui_thread.append(QThread.currentThread() == app.thread())
        done.set()

    worker = threading.Thread(target=lambda: dispatcher.dispatch(callback), daemon=True)
    worker.start()
    worker.join(timeout=1.0)

    assert _wait_for(done.is_set)
    assert seen_gui_thread == [True]


def test_main_window_dispatch_to_main_thread_noop_when_shutting_down() -> None:
    dispatched: list[object] = []

    class _FakeDispatcher:
        def dispatch(self, callback) -> None:  # type: ignore[no-untyped-def]
            dispatched.append(callback)

    fake = SimpleNamespace(_is_shutting_down=True, _main_thread_dispatcher=_FakeDispatcher())

    MainWindow._dispatch_to_main_thread(fake, lambda: None)

    assert dispatched == []


def test_schedule_search_results_uses_dispatcher() -> None:
    captured: dict[str, object] = {}

    class _FakeWindow:
        def __init__(self) -> None:
            self.dispatched: list[object] = []

        def _dispatch_to_main_thread(self, callback) -> None:  # type: ignore[no-untyped-def]
            self.dispatched.append(callback)

        def _set_search_results(self, matches, query) -> None:  # type: ignore[no-untyped-def]
            captured["matches"] = matches
            captured["query"] = query

    fake = _FakeWindow()
    MainWindow._schedule_search_results_update(fake, [], "needle")
    assert len(fake.dispatched) == 1

    callback = fake.dispatched[0]
    callback()
    assert captured == {"matches": [], "query": "needle"}


def test_search_worker_done_uses_dispatcher_for_state_clear() -> None:
    logger = _LoggerStub()

    class _FakeWindow:
        def __init__(self) -> None:
            self._logger = logger
            self._active_search_worker = object()
            self.dispatched: list[object] = []

        def _dispatch_to_main_thread(self, callback) -> None:  # type: ignore[no-untyped-def]
            self.dispatched.append(callback)

    fake = _FakeWindow()
    MainWindow._handle_search_worker_done(fake, time.perf_counter() - 0.01, "abc")
    assert len(logger.info_calls) == 1
    assert len(fake.dispatched) == 1

    callback = fake.dispatched[0]
    callback()
    assert fake._active_search_worker is None


def test_symbol_index_done_uses_dispatcher_for_state_clear() -> None:
    logger = _LoggerStub()

    class _FakeWindow:
        def __init__(self) -> None:
            self._symbol_index_generation = 7
            self._intelligence_runtime_settings = SimpleNamespace(metrics_logging_enabled=False)
            self._logger = logger
            self._active_symbol_index_worker = object()
            self.dispatched: list[object] = []

        def _dispatch_to_main_thread(self, callback) -> None:  # type: ignore[no-untyped-def]
            self.dispatched.append(callback)

    fake = _FakeWindow()
    MainWindow._handle_symbol_index_done(
        fake,
        "/tmp/project",
        13,
        time.perf_counter() - 0.01,
        7,
    )
    assert len(fake.dispatched) == 1

    callback = fake.dispatched[0]
    callback()
    assert fake._active_symbol_index_worker is None


def test_symbol_index_error_uses_dispatcher_for_state_clear() -> None:
    logger = _LoggerStub()

    class _FakeWindow:
        def __init__(self) -> None:
            self._symbol_index_generation = 4
            self._logger = logger
            self._active_symbol_index_worker = object()
            self.dispatched: list[object] = []

        def _dispatch_to_main_thread(self, callback) -> None:  # type: ignore[no-untyped-def]
            self.dispatched.append(callback)

    fake = _FakeWindow()
    MainWindow._handle_symbol_index_error(fake, "/tmp/project", "boom", 4)
    assert len(logger.warning_calls) == 1
    assert len(fake.dispatched) == 1

    callback = fake.dispatched[0]
    callback()
    assert fake._active_symbol_index_worker is None
