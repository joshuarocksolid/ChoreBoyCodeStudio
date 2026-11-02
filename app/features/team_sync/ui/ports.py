"""How the UI runs a blocking Team Sync call off the paint path."""

from __future__ import annotations

from typing import Callable, Optional, TypeVar

T = TypeVar("T")


class SyncPorts:
    """Runs the call immediately. Tests and the screenshot script use this."""

    def run(
        self,
        key: str,
        fn: Callable[[], T],
        on_success: Callable[[T], None],
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        del key
        try:
            on_success(fn())
        except Exception as exc:
            if on_error is not None:
                on_error(exc)
            else:
                raise


class SchedulerPorts:
    """Hands the call to the shell background scheduler."""

    def __init__(self, scheduler: object) -> None:
        self._scheduler = scheduler

    def run(
        self,
        key: str,
        fn: Callable[[], T],
        on_success: Callable[[T], None],
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        def task(cancel):  # type: ignore[no-untyped-def]
            if cancel.is_set():
                return None
            return fn()

        self._scheduler.run(  # type: ignore[attr-defined]
            key=key,
            task=task,
            on_success=on_success,
            on_error=on_error,
        )


__all__ = ["SchedulerPorts", "SyncPorts"]
