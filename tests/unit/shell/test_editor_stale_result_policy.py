"""Unit tests for shared editor stale-result policy."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.shell.editor_stale_result_policy import (
    deliver_revision_gated_editor_result,
    is_stale_revision_gated_editor_request,
)

pytestmark = pytest.mark.unit


class _Widget:
    pass


def test_is_stale_when_active_widget_differs() -> None:
    requested = _Widget()
    current = _Widget()

    assert is_stale_revision_gated_editor_request(
        file_path="/tmp/a.py",
        editor_widget=requested,
        requested_revision=1,
        editor_widget_for_path=lambda _path: current,
        buffer_revision=lambda _path: 1,
    )


def test_is_stale_when_revision_differs() -> None:
    widget = _Widget()

    assert is_stale_revision_gated_editor_request(
        file_path="/tmp/a.py",
        editor_widget=widget,
        requested_revision=1,
        editor_widget_for_path=lambda _path: widget,
        buffer_revision=lambda _path: 2,
    )


def test_is_stale_when_generation_differs() -> None:
    widget = _Widget()

    assert is_stale_revision_gated_editor_request(
        file_path="/tmp/a.py",
        editor_widget=widget,
        requested_revision=1,
        editor_widget_for_path=lambda _path: widget,
        buffer_revision=lambda _path: 1,
        requested_generation=3,
        current_generation=4,
    )


def test_is_stale_false_when_all_match() -> None:
    widget = _Widget()

    assert not is_stale_revision_gated_editor_request(
        file_path="/tmp/a.py",
        editor_widget=widget,
        requested_revision=1,
        editor_widget_for_path=lambda _path: widget,
        buffer_revision=lambda _path: 1,
        requested_generation=3,
        current_generation=3,
    )


def test_deliver_skips_stale() -> None:
    widget = _Widget()
    delivered: list[str] = []

    deliver_revision_gated_editor_result(
        file_path="/tmp/a.py",
        editor_widget=widget,
        requested_revision=1,
        editor_widget_for_path=lambda _path: widget,
        buffer_revision=lambda _path: 2,
        deliver=lambda: delivered.append("ran"),
    )

    assert delivered == []


def test_deliver_runs_when_current() -> None:
    widget = _Widget()
    delivered: list[str] = []

    deliver_revision_gated_editor_result(
        file_path="/tmp/a.py",
        editor_widget=widget,
        requested_revision=1,
        editor_widget_for_path=lambda _path: widget,
        buffer_revision=lambda _path: 1,
        deliver=lambda: delivered.append("ran"),
    )

    assert delivered == ["ran"]
