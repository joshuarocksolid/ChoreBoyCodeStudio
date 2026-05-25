"""Breakpoint state store for debug sessions."""

from __future__ import annotations

from typing import Callable

from app.debug.debug_breakpoints import breakpoint_key, build_breakpoint, with_file_path
from app.debug.debug_models import DebugBreakpoint


class BreakpointStore:
    """Single source of truth for gutter presence and breakpoint specs."""

    def __init__(self) -> None:
        self._breakpoints_by_file: dict[str, set[int]] = {}
        self._breakpoint_specs_by_key: dict[tuple[str, int], DebugBreakpoint] = {}

    def has_any_breakpoints(self) -> bool:
        return bool(self._breakpoints_by_file)

    def get_spec(self, file_path: str, line_number: int) -> DebugBreakpoint | None:
        return self._breakpoint_specs_by_key.get(breakpoint_key(file_path, line_number))

    def list_all(self) -> list[DebugBreakpoint]:
        return self.all_specs()

    def clear_all(self) -> None:
        self._breakpoints_by_file.clear()
        self._breakpoint_specs_by_key.clear()

    def clear_file(self, file_path: str) -> None:
        self._breakpoints_by_file.pop(file_path, None)
        keys_to_remove = [key for key in self._breakpoint_specs_by_key if key[0] == file_path]
        for key in keys_to_remove:
            self._breakpoint_specs_by_key.pop(key, None)

    def lines_for_file(self, file_path: str) -> set[int]:
        return set(self._breakpoints_by_file.get(file_path, set()))

    def lines_snapshot(self) -> dict[str, set[int]]:
        """Return a shallow copy of gutter line sets keyed by file path."""
        return {file_path: set(lines) for file_path, lines in self._breakpoints_by_file.items()}

    def restore_session_breakpoints(
        self,
        restored_by_file: dict[str, set[int]],
        *,
        ensure_spec: Callable[[str, int], DebugBreakpoint] | None = None,
    ) -> None:
        """Replace store contents from persisted session breakpoint lines."""
        self.clear_all()
        for file_path, lines in restored_by_file.items():
            if not lines:
                continue
            self._breakpoints_by_file[file_path] = set(lines)
            if ensure_spec is not None:
                for line_number in lines:
                    ensure_spec(file_path, line_number)

    def ensure_spec(self, file_path: str, line_number: int) -> DebugBreakpoint:
        key = breakpoint_key(file_path, line_number)
        existing = self._breakpoint_specs_by_key.get(key)
        if existing is not None:
            return existing
        created = build_breakpoint(file_path=file_path, line_number=line_number)
        self._breakpoint_specs_by_key[key] = created
        return created

    def all_specs(self) -> list[DebugBreakpoint]:
        breakpoints = list(self._breakpoint_specs_by_key.values())
        return sorted(breakpoints, key=lambda breakpoint: (breakpoint.file_path, breakpoint.line_number))

    def set_spec(self, breakpoint: DebugBreakpoint) -> None:
        self._breakpoint_specs_by_key[
            breakpoint_key(breakpoint.file_path, breakpoint.line_number)
        ] = breakpoint

    def remove_line(self, file_path: str, line_number: int) -> None:
        breakpoints = self._breakpoints_by_file.get(file_path, set())
        breakpoints.discard(line_number)
        if not breakpoints:
            self._breakpoints_by_file.pop(file_path, None)
        self._breakpoint_specs_by_key.pop(breakpoint_key(file_path, line_number), None)

    def set_line_enabled(self, file_path: str, line_number: int, enabled: bool) -> None:
        breakpoints = self._breakpoints_by_file.setdefault(file_path, set())
        if enabled:
            breakpoints.add(line_number)
            self.ensure_spec(file_path, line_number)
        else:
            breakpoints.discard(line_number)
            self._breakpoint_specs_by_key.pop(breakpoint_key(file_path, line_number), None)
            if not breakpoints:
                self._breakpoints_by_file.pop(file_path, None)

    def remap_paths(self, path_map: dict[str, str]) -> None:
        if not path_map:
            return
        remapped_by_file: dict[str, set[int]] = {}
        for file_path, lines in self._breakpoints_by_file.items():
            target_path = path_map.get(file_path, file_path)
            remapped_by_file.setdefault(target_path, set()).update(lines)
        self._breakpoints_by_file.clear()
        self._breakpoints_by_file.update(remapped_by_file)

        remapped_specs: dict[tuple[str, int], DebugBreakpoint] = {}
        for (file_path, line_number), spec in self._breakpoint_specs_by_key.items():
            target_path = path_map.get(file_path, file_path)
            remapped_specs[breakpoint_key(target_path, line_number)] = with_file_path(spec, target_path)
        self._breakpoint_specs_by_key.clear()
        self._breakpoint_specs_by_key.update(remapped_specs)
