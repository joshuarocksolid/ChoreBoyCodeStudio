"""Serialized worker queue for semantic engine operations."""
from __future__ import annotations

from dataclasses import dataclass, field
import queue
import threading
import time
from typing import Callable, Optional


@dataclass(order=True)
class _QueuedSemanticTask:
    priority: int
    sequence: int
    key: str = field(compare=False)
    generation: int = field(compare=False)
    task: Callable[[], object] = field(compare=False)
    on_success: Callable[[object], None] | None = field(compare=False)
    on_error: Callable[[Exception], None] | None = field(compare=False)
    dispatch_on_main_thread: bool = field(default=True, compare=False)
    enqueued_at: float = field(default_factory=time.perf_counter, compare=False)


class SemanticWorker:
    """Runs semantic tasks on a single background thread."""

    def __init__(self, *, dispatch_to_main_thread: Callable[[Callable[[], None]], None]) -> None:
        self._dispatch_to_main_thread = dispatch_to_main_thread
        self._queue: "queue.PriorityQueue[_QueuedSemanticTask]" = queue.PriorityQueue()
        self._lock = threading.Lock()
        self._generations: dict[str, int] = {}
        self._sequence = 0
        self._shutdown_requested = False
        self._last_queue_wait_ms_by_key: dict[str, float] = {}
        self._thread = threading.Thread(target=self._run, name="semantic-worker", daemon=True)
        self._thread.start()

    def submit(
        self,
        *,
        key: str,
        task: Callable[[], object],
        on_success: Optional[Callable[[object], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
        dispatch_on_main_thread: bool = True,
        priority: int = 50,
    ) -> None:
        """Queue a task, replacing any previous queued result for the same key."""
        with self._lock:
            if self._shutdown_requested:
                return
            generation = self._generations.get(key, 0) + 1
            self._generations[key] = generation
            self._sequence += 1
            sequence = self._sequence
        self._queue.put(
            _QueuedSemanticTask(
                priority=priority,
                sequence=sequence,
                key=key,
                generation=generation,
                task=task,
                on_success=on_success,
                on_error=on_error,
                dispatch_on_main_thread=dispatch_on_main_thread,
            )
        )

    def call(self, *, key: str, task: Callable[[], object], timeout_seconds: float = 5.0) -> object:
        """Run a task on the semantic thread and block until it completes."""
        done = threading.Event()
        result_holder: dict[str, object] = {}

        def on_success(result: object) -> None:
            result_holder["result"] = result
            done.set()

        def on_error(exc: Exception) -> None:
            result_holder["error"] = exc
            done.set()

        self.submit(
            key=key,
            task=task,
            on_success=on_success,
            on_error=on_error,
            dispatch_on_main_thread=False,
            priority=0,
        )
        if not done.wait(timeout_seconds):
            raise TimeoutError("Semantic worker call timed out.")
        error = result_holder.get("error")
        if isinstance(error, Exception):
            raise error
        return result_holder.get("result")

    def cancel_all(self) -> None:
        """Invalidate all queued tasks."""
        with self._lock:
            for key in list(self._generations):
                self._generations[key] += 1

    def shutdown(self) -> None:
        """Stop the worker thread."""
        with self._lock:
            self._shutdown_requested = True
            self._sequence += 1
            sequence = self._sequence
        self._queue.put(
            _QueuedSemanticTask(
                priority=-100,
                sequence=sequence,
                key="__shutdown__",
                generation=0,
                task=lambda: None,
                on_success=None,
                on_error=None,
                dispatch_on_main_thread=False,
            )
        )
        self._thread.join(timeout=1.0)

    def queue_wait_ms(self, key: str) -> float:
        """Return the most recent queue wait observed for ``key``."""

        with self._lock:
            return self._last_queue_wait_ms_by_key.get(key, 0.0)

    def _run(self) -> None:
        while True:
            queued = self._queue.get()
            if queued.key == "__shutdown__":
                return
            if not self._is_current(queued.key, queued.generation):
                continue
            queue_wait_ms = (time.perf_counter() - queued.enqueued_at) * 1000.0
            with self._lock:
                self._last_queue_wait_ms_by_key[queued.key] = queue_wait_ms
            try:
                result = queued.task()
            except Exception as exc:
                if queued.on_error is not None and self._is_current(queued.key, queued.generation):
                    if queued.dispatch_on_main_thread:
                        self._dispatch_to_main_thread(lambda exc=exc, callback=queued.on_error: callback(exc))
                    else:
                        queued.on_error(exc)
                continue
            if queued.on_success is not None and self._is_current(queued.key, queued.generation):
                if queued.dispatch_on_main_thread:
                    self._dispatch_to_main_thread(lambda result=result, callback=queued.on_success: callback(result))
                else:
                    queued.on_success(result)

    def _is_current(self, key: str, generation: int) -> bool:
        with self._lock:
            return self._generations.get(key) == generation
