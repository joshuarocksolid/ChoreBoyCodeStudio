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


# AD-018 gate matrix — inline/menu generation omission (Wave 3c contract).
# inline_intelligence_workflow.py calls deliver_revision_gated_editor_result with
# revision only; generation is checked inside editor paint methods for async inline
# paths, and menu paths use ungated show_calltip. Wave 3c must pass generation
# through the policy module for all four deliver sites.


@pytest.mark.parametrize(
    "surface",
    [
        "inline_hover",
        "inline_signature",
        "menu_hover",
        "menu_signature",
    ],
)
def test_revision_only_policy_misses_stale_generation(surface: str) -> None:
    """Current inline/menu behavior: revision-only gate passes when generation is stale."""
    _ = surface
    widget = _Widget()

    assert not is_stale_revision_gated_editor_request(
        file_path="/tmp/a.py",
        editor_widget=widget,
        requested_revision=1,
        editor_widget_for_path=lambda _path: widget,
        buffer_revision=lambda _path: 1,
    )


@pytest.mark.parametrize(
    "surface",
    [
        "inline_hover",
        "inline_signature",
        "menu_hover",
        "menu_signature",
    ],
)
def test_full_gate_blocks_stale_generation_for_inline_and_menu(surface: str) -> None:
    """Wave 3c target: inline/menu deliver generation through the policy module."""
    _ = surface
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


@pytest.mark.parametrize(
    "surface",
    [
        "inline_hover",
        "inline_signature",
        "menu_hover",
        "menu_signature",
    ],
)
def test_revision_only_delivery_runs_when_generation_stale(surface: str) -> None:
    """Documents deliver gap: revision-only path invokes deliver on stale generation."""
    _ = surface
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


@pytest.mark.parametrize(
    "surface",
    [
        "inline_hover",
        "inline_signature",
        "menu_hover",
        "menu_signature",
    ],
)
def test_full_gate_delivery_skips_when_generation_stale(surface: str) -> None:
    """Wave 3c target: deliver skipped when revision matches but generation differs."""
    _ = surface
    widget = _Widget()
    delivered: list[str] = []

    deliver_revision_gated_editor_result(
        file_path="/tmp/a.py",
        editor_widget=widget,
        requested_revision=1,
        editor_widget_for_path=lambda _path: widget,
        buffer_revision=lambda _path: 1,
        deliver=lambda: delivered.append("ran"),
        requested_generation=3,
        current_generation=4,
    )

    assert delivered == []
