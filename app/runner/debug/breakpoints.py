"""Breakpoint apply/sync helpers for runner debug sessions."""

from __future__ import annotations

import bdb
from dataclasses import replace
from typing import Mapping

from app.debug.debug_breakpoints import parse_breakpoint_entry
from app.debug.debug_models import DebugBreakpoint


def parse_breakpoints(raw_value: object) -> list[DebugBreakpoint]:
    if not isinstance(raw_value, list):
        return []
    breakpoints: list[DebugBreakpoint] = []
    for entry in raw_value:
        if not isinstance(entry, Mapping):
            continue
        parsed = parse_breakpoint_entry(entry)
        if parsed is not None:
            breakpoints.append(parsed)
    return breakpoints


class BreakpointMixin:
    """Breakpoint verification and manifest sync for the debug host."""

    def _apply_breakpoints(self, breakpoints: list[DebugBreakpoint]) -> list[dict[str, object]]:
        self.debugger.clear_all_breaks()
        verified_payloads: list[dict[str, object]] = []
        for breakpoint in breakpoints:
            if not breakpoint.enabled:
                verified_payloads.append(
                    {
                        "breakpoint_id": breakpoint.breakpoint_id,
                        "file_path": self._display_file_path(breakpoint.file_path),
                        "line_number": breakpoint.line_number,
                        "enabled": breakpoint.enabled,
                        "condition": breakpoint.condition,
                        "hit_condition": breakpoint.hit_condition,
                        "verified": True,
                        "verification_message": "Disabled",
                    }
                )
                continue
            try:
                result = self.debugger.set_break(
                    breakpoint.file_path,
                    breakpoint.line_number,
                    cond=breakpoint.condition or None,
                )
                if result:
                    verified_payloads.append(
                        {
                            "breakpoint_id": breakpoint.breakpoint_id,
                            "file_path": self._display_file_path(breakpoint.file_path),
                            "line_number": breakpoint.line_number,
                            "enabled": breakpoint.enabled,
                            "condition": breakpoint.condition,
                            "hit_condition": breakpoint.hit_condition,
                            "verified": False,
                            "verification_message": str(result),
                        }
                    )
                    continue
                if breakpoint.hit_condition is not None and breakpoint.hit_condition > 1:
                    canonical_file = self.debugger.canonic(breakpoint.file_path)
                    active_breakpoint = bdb.Breakpoint.bplist[canonical_file, breakpoint.line_number][-1]
                    active_breakpoint.ignore = breakpoint.hit_condition - 1
                verified_payloads.append(
                    {
                        "breakpoint_id": breakpoint.breakpoint_id,
                        "file_path": self._display_file_path(breakpoint.file_path),
                        "line_number": breakpoint.line_number,
                        "enabled": breakpoint.enabled,
                        "condition": breakpoint.condition,
                        "hit_condition": breakpoint.hit_condition,
                        "verified": True,
                        "verification_message": "",
                    }
                )
            except Exception as exc:
                verified_payloads.append(
                    {
                        "breakpoint_id": breakpoint.breakpoint_id,
                        "file_path": self._display_file_path(breakpoint.file_path),
                        "line_number": breakpoint.line_number,
                        "enabled": breakpoint.enabled,
                        "condition": breakpoint.condition,
                        "hit_condition": breakpoint.hit_condition,
                        "verified": False,
                        "verification_message": str(exc),
                    }
                )
        return verified_payloads

    def _breakpoint_payloads(self, breakpoints: list[DebugBreakpoint]) -> list[dict[str, object]]:
        return [
            {
                "breakpoint_id": breakpoint.breakpoint_id,
                "file_path": self._display_file_path(breakpoint.file_path),
                "line_number": breakpoint.line_number,
                "enabled": breakpoint.enabled,
                "condition": breakpoint.condition,
                "hit_condition": breakpoint.hit_condition,
                "verified": breakpoint.verified,
                "verification_message": breakpoint.verification_message,
            }
            for breakpoint in breakpoints
        ]

    def _handle_update_breakpoints(self, *, command_id: str, arguments: Mapping[str, object]) -> None:
        breakpoints = parse_breakpoints(arguments.get("breakpoints", []))
        self._manifest = replace(self._manifest, breakpoints=breakpoints)
        updated = self._apply_breakpoints(breakpoints)
        self._send_event("breakpoints_updated", {"breakpoints": updated})
        self._send_response(
            command_name="update_breakpoints",
            command_id=command_id,
            success=True,
            body={"breakpoints": updated},
        )
