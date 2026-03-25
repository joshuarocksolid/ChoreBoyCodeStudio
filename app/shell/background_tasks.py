"""Bounded keyed background scheduler for shell actions."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, TypeVar

T = TypeVar("T")

DispatchToMainThread = Callable[[Callable[[], None]], None]
TaskFunction = Callable[[threading.Event], T]
SuccessCallback = Callable[[T], None]
ErrorCallback = Callable[[Exception], None]


class GeneralTaskScheduler:
    """Runs keyed background tasks on a reusable bounded thread pool."""

    def __init__(
        self,
        *,
        dispatch_to_main_thread: DispatchToMainThread,
        max_workers: int = 4,
    ) -> None:
        self._dispatch_to_main_thread = dispatch_to_main_thread
        self._lock = threading.RLock()
        self._active_cancellations: dict[str, threading.Event] = {}
        self._executor = ThreadPoolExecutor(
            max_workers=max(1, max_workers),
            thread_name_prefix="shell-task",
        )

    def run(
        self,
        *,
        key: str,
        task: TaskFunction[T],
        on_success: SuccessCallback[T] | None = None,
        on_error: ErrorCallback | None = None,
    ) -> None:
        cancellation = threading.Event()
        with self._lock:
            previous = self._active_cancellations.get(key)
            if previous is not None:
                previous.set()
            self._active_cancellations[key] = cancellation

        def worker() -> None:
            try:
                result = task(cancellation)
            except Exception as exc:  # pragma: no cover - defensive guard
                self._dispatch_to_main_thread(lambda: self._handle_error(key, cancellation, exc, on_error))
                return
            self._dispatch_to_main_thread(lambda: self._handle_success(key, cancellation, result, on_success))

        self._executor.submit(worker)

    def cancel(self, key: str) -> None:
        with self._lock:
            cancellation = self._active_cancellations.pop(key, None)
        if cancellation is not None:
            cancellation.set()

    def cancel_all(self) -> None:
        with self._lock:
            keys = list(self._active_cancellations.keys())
        for key in keys:
            self.cancel(key)

    def shutdown(self, *, wait: bool = False) -> None:
        """Cancel outstanding work and stop accepting new tasks."""
        self.cancel_all()
        self._executor.shutdown(wait=wait, cancel_futures=False)

    def _handle_success(
        self,
        key: str,
        cancellation: threading.Event,
        result: T,
        on_success: SuccessCallback[T] | None,
    ) -> None:
        if not self._is_current(key, cancellation):
            return
        if on_success is not None and not cancellation.is_set():
            on_success(result)

    def _handle_error(
        self,
        key: str,
        cancellation: threading.Event,
        exc: Exception,
        on_error: ErrorCallback | None,
    ) -> None:
        if not self._is_current(key, cancellation):
            return
        if on_error is not None and not cancellation.is_set():
            on_error(exc)

    def _is_current(self, key: str, cancellation: threading.Event) -> bool:
        with self._lock:
            current = self._active_cancellations.get(key)
            if current is not cancellation:
                return False
            self._active_cancellations.pop(key, None)
            return True


