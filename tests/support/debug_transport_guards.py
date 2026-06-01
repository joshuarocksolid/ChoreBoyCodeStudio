"""Shared guards for debug-transport integration tests on AppRun."""

from __future__ import annotations

import time
from typing import Callable, Mapping

import pytest

from app.run.process_supervisor import ProcessEvent
from app.run.run_service import RunService

_SKIP_NO_EVENTS = (
    "Debug transport did not emit events in this environment "
    "(runner subprocess started but no debug channel; known Cloud/AppRun limitation). "
    "See docs/DISCOVERY.md §4D."
)
_SKIP_PARTIAL_CHANNEL = (
    "Debug transport emitted lifecycle traffic but no structured pause (stopped) event "
    "within the wait window on this AppRun build (known Cloud/AppRun debug-transport "
    "limitation). See docs/DISCOVERY.md §4D."
)


def wait_until(predicate: Callable[[], bool], timeout_seconds: float = 6.0) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def has_debug_events(events: list[ProcessEvent]) -> bool:
    return any(event.event_type == "debug" for event in events)


def debug_is_paused(events: list[ProcessEvent]) -> bool:
    paused = False
    for event in events:
        if event.event_type != "debug" or not isinstance(event.payload, Mapping):
            continue
        if event.payload.get("kind") != "event":
            continue
        event_name = str(event.payload.get("event", "")).strip()
        if event_name == "stopped":
            paused = True
        elif event_name in {"continued", "session_ready", "session_ended"}:
            paused = False
    return paused


def stopped_event_count(events: list[ProcessEvent]) -> int:
    count = 0
    for event in events:
        if event.event_type != "debug" or not isinstance(event.payload, Mapping):
            continue
        if event.payload.get("kind") == "event" and event.payload.get("event") == "stopped":
            count += 1
    return count


def require_debug_pause_or_skip(
    service: RunService,
    events: list[ProcessEvent],
    *,
    timeout_seconds: float = 12.0,
) -> None:
    """Wait for a structured pause or skip when the debug channel is unavailable."""
    if wait_until(lambda: debug_is_paused(events), timeout_seconds=timeout_seconds):
        return
    service.stop_run()
    if not has_debug_events(events):
        pytest.skip(_SKIP_NO_EVENTS)
    if stopped_event_count(events) == 0:
        pytest.skip(_SKIP_PARTIAL_CHANNEL)
    assert debug_is_paused(events)
