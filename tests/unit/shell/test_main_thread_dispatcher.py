"""Unit tests for GUI-thread callback dispatch wiring."""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace
from typing import Any

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtCore import QThread  # noqa: E402
from PySide2.QtWidgets import QApplication  # noqa: E402

from app.shell.main_thread_dispatcher import MainThreadDispatcher  # noqa: E402
from app.shell.main_window import MainWindow  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module", autouse=True)
def _qapp(qapp):  # type: ignore[no-untyped-def]
    return qapp


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
