"""Unit tests for breakpoint wire helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from app.debug.debug_breakpoints import (
    breakpoint_to_verified_wire_dict,
    breakpoint_to_wire_dict,
    build_breakpoint,
    parse_breakpoint_entry,
    parse_breakpoint_list,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("breakpoint_kwargs", "expected_wire_keys"),
    [
        ({}, frozenset({"breakpoint_id", "file_path", "line_number", "enabled"})),
        ({"condition": "x > 1"}, frozenset({"breakpoint_id", "file_path", "line_number", "enabled", "condition"})),
        ({"hit_condition": 3}, frozenset({"breakpoint_id", "file_path", "line_number", "enabled", "hit_condition"})),
        (
            {"condition": "x > 1", "hit_condition": 3},
            frozenset(
                {
                    "breakpoint_id",
                    "file_path",
                    "line_number",
                    "enabled",
                    "condition",
                    "hit_condition",
                }
            ),
        ),
    ],
)
def test_breakpoint_wire_round_trip(
    tmp_path: Path,
    breakpoint_kwargs: dict[str, Any],
    expected_wire_keys: frozenset[str],
) -> None:
    """Wire serialization and parsing should preserve breakpoint models."""

    file_path = str((tmp_path / "main.py").resolve())
    breakpoint = build_breakpoint(file_path, 12, **breakpoint_kwargs)
    wire = breakpoint_to_wire_dict(breakpoint)

    assert frozenset(wire.keys()) == expected_wire_keys
    assert "condition" not in wire or wire["condition"] == breakpoint.condition
    assert "hit_condition" not in wire or wire["hit_condition"] == breakpoint.hit_condition

    parsed = parse_breakpoint_entry(wire)
    assert parsed == breakpoint


@pytest.mark.parametrize("hit_condition", [0, "0", -1])
def test_parse_breakpoint_entry_normalizes_non_positive_hit_condition(hit_condition: object) -> None:
    """Non-positive hit counts should not survive wire parsing."""

    file_path = "/tmp/project/main.py"
    breakpoint = build_breakpoint(file_path, 4, hit_condition=5)
    wire = breakpoint_to_wire_dict(breakpoint)
    wire["hit_condition"] = hit_condition

    parsed = parse_breakpoint_entry(wire)

    assert parsed is not None
    assert parsed.hit_condition is None


def test_build_breakpoint_normalizes_zero_hit_condition() -> None:
    """Model construction should treat zero hit counts as unset."""

    breakpoint = build_breakpoint("/tmp/project/main.py", 4, hit_condition=0)

    assert breakpoint.hit_condition is None
    assert "hit_condition" not in breakpoint_to_wire_dict(breakpoint)


def test_parse_breakpoint_list_skips_invalid_entries() -> None:
    """Shared list parser should ignore malformed wire entries."""

    valid = build_breakpoint("/tmp/project/main.py", 7, condition="ready")
    wire = breakpoint_to_wire_dict(valid)

    parsed = parse_breakpoint_list([wire, {"file_path": ""}, "not-a-mapping", None])

    assert parsed == [valid]


def test_breakpoint_to_verified_wire_dict_includes_verification_fields() -> None:
    """Runner transport payloads extend the manifest wire shape with verification."""

    breakpoint = build_breakpoint("/tmp/project/main.py", 9, condition="x > 1", hit_condition=2)

    payload = breakpoint_to_verified_wire_dict(
        breakpoint,
        verified=True,
        verification_message="ok",
    )

    assert payload["verified"] is True
    assert payload["verification_message"] == "ok"
    assert frozenset(payload.keys()) == frozenset(
        {
            "breakpoint_id",
            "file_path",
            "line_number",
            "enabled",
            "condition",
            "hit_condition",
            "verified",
            "verification_message",
        }
    )
    parsed = parse_breakpoint_entry(payload)
    assert parsed is not None
    assert parsed.breakpoint_id == breakpoint.breakpoint_id
    assert parsed.file_path == breakpoint.file_path
    assert parsed.line_number == breakpoint.line_number
    assert parsed.condition == breakpoint.condition
    assert parsed.hit_condition == breakpoint.hit_condition
    assert parsed.verified is True
    assert parsed.verification_message == "ok"
