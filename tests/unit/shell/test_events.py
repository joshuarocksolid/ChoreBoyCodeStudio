from __future__ import annotations

import logging

import pytest

from app.shell.events import ProjectOpenedEvent, ShellEventBus

pytestmark = pytest.mark.unit


def test_publish_logs_failing_subscriber_and_continues(caplog: pytest.LogCaptureFixture) -> None:
    bus = ShellEventBus()
    delivered: list[str] = []

    def failing_handler(_event: ProjectOpenedEvent) -> None:
        raise RuntimeError("subscriber failed")

    def recording_handler(event: ProjectOpenedEvent) -> None:
        delivered.append(event.project_root)

    bus.subscribe(ProjectOpenedEvent, failing_handler)
    bus.subscribe(ProjectOpenedEvent, recording_handler)

    with caplog.at_level(logging.ERROR):
        bus.publish(ProjectOpenedEvent(project_root="/tmp/project", project_name="Demo"))

    assert delivered == ["/tmp/project"]
    assert "event subscriber raised" in caplog.text
    assert "subscriber failed" in caplog.text
