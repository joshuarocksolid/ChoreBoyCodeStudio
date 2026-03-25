"""Serialized worker queue for semantic engine operations."""
from __future__ import annotations

from dataclasses import dataclass
import queue
import threading
from typing import Callable, Optional


@dataclass
class _QueuedSemanticTask:
    key: str
    generation: int
    task: Callable[[], object]
    on_success: Callable[[object], None] | None
    on_error: Callable[[Exception], None] | None
    dispatch_on_main_thread: bool = True


class SemanticWorker:
    """Runs semantic tasks on a single background thread."""

    def __init__(self, *, dispatch_to_main_thread: Callable[[Callable[[], None]], None]) -> None:
        self._dispatch_to_main_thread = dispatch_to_main_thread
        self._queue: "queue.Queue[_QueuedSemanticTask | None]" = queue.Queue()
        self._lock = threading.Lock()
        self._generations: dict[str, int] = {}
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
    ) -> None:
        """Queue a task, replacing any previous queued result for the same key."""
        with self._lock:
            generation = self._generations.get(key, 0) + 1
            self._generations[key] = generation
        self._queue.put(
            _QueuedSemanticTask(
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
        self._queue.put(None)
        self._thread.join(timeout=1.0)

    def _run(self) -> None:
        while True:
            queued = self._queue.get()
            if queued is None:
                return
            if not self._is_current(queued.key, queued.generation):
                continue
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
