from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import logging
from typing import Callable, TypeVar

from app.run.process_supervisor import ProcessState

T = TypeVar("T")
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RunSessionStartedEvent:
    run_id: str
    mode: str
    entry_file: str
    project_root: str


@dataclass(frozen=True)
class RunProcessOutputEvent:
    run_id: str | None
    mode: str | None
    stream: str
    text: str


@dataclass(frozen=True)
class RunProcessStateEvent:
    run_id: str | None
    mode: str | None
    state: ProcessState | None
    terminated_by_user: bool


@dataclass(frozen=True)
class RunProcessExitEvent:
    run_id: str | None
    mode: str | None
    return_code: int | None
    terminated_by_user: bool


@dataclass(frozen=True)
class ProjectOpenedEvent:
    project_root: str
    project_name: str


@dataclass(frozen=True)
class ProjectOpenFailedEvent:
    project_root: str
    error_message: str


class ShellEventBus:
    def __init__(self) -> None:
        self._subscribers: dict[type[object], list[Callable[[object], None]]] = defaultdict(list)

    def subscribe(self, event_type: type[T], handler: Callable[[T], None]) -> None:
        self._subscribers[event_type].append(handler)  # type: ignore[arg-type]

    def unsubscribe(self, event_type: type[T], handler: Callable[[T], None]) -> None:
        handlers = self._subscribers.get(event_type)
        if not handlers:
            return
        self._subscribers[event_type] = [h for h in handlers if h is not handler]
        if not self._subscribers[event_type]:
            self._subscribers.pop(event_type, None)

    def publish(self, event: object) -> None:
        handlers = list(self._subscribers.get(type(event), []))
        for handler in handlers:
            try:
                handler(event)
            except Exception:
                logger.exception("event subscriber raised: %s", handler)
                continue
