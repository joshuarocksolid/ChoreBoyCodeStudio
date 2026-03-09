"""Runner-side debug execution helpers."""

from __future__ import annotations

import bdb
import pdb
import sys
from typing import Callable

from app.core import constants
from app.debug.debug_event_protocol import format_debug_event
from app.debug.debug_models import DebugEvent, DebugFrame, DebugVariable
from app.run.run_manifest import RunManifest


class MarkedPdb(pdb.Pdb):
    """PDB subclass that emits machine-readable pause events."""

    def __init__(self) -> None:
        super().__init__()
        self._skip_until_first_breakpoint = False

    def configure_initial_breakpoint_seek(self, enabled: bool) -> None:
        """Skip startup wrapper frames until first configured breakpoint is reached."""
        self._skip_until_first_breakpoint = enabled

    def user_line(self, frame):  # type: ignore[override]
        if self._skip_until_first_breakpoint and not self.break_here(frame):
            self.set_continue()
            return
        self._skip_until_first_breakpoint = False
        super().user_line(frame)

    def interaction(self, frame, traceback):  # type: ignore[override]
        event = DebugEvent(
            event_type="paused",
            message="Paused at breakpoint.",
            frames=[
                DebugFrame(
                    file_path=str(frame.f_code.co_filename),
                    line_number=int(frame.f_lineno),
                    function_name=str(frame.f_code.co_name),
                )
            ],
            variables=[
                DebugVariable(name=str(name), value_repr=repr(value))
                for name, value in sorted(frame.f_locals.items(), key=lambda item: item[0])[:50]
            ],
        )
        print(format_debug_event(event))
        print("__CB_DEBUG_PAUSED__")
        try:
            super().interaction(frame, traceback)
        finally:
            print("__CB_DEBUG_RUNNING__")


def run_debug_session(manifest: RunManifest, entry_callable: Callable[[str], None], entry_script_path: str) -> int:
    """Run entry script under debugger with manifest breakpoints."""
    debugger = MarkedPdb()
    has_valid_breakpoints = False
    for breakpoint_entry in manifest.breakpoints:
        file_path = str(breakpoint_entry["file_path"])
        line_number = int(breakpoint_entry["line_number"])
        try:
            result = debugger.set_break(file_path, line_number)
            if result:
                print(
                    f"Failed to set breakpoint {file_path}:{line_number}: {result}",
                    file=sys.stderr,
                )
                continue
            has_valid_breakpoints = True
        except Exception as exc:
            print(f"Failed to set breakpoint {file_path}:{line_number}: {exc}", file=sys.stderr)
    if manifest.breakpoints and not has_valid_breakpoints:
        print("No valid breakpoints were set; debug run will continue without pausing.", file=sys.stderr)
    debugger.configure_initial_breakpoint_seek(True)

    try:
        print("__CB_DEBUG_RUNNING__")
        debugger.runcall(entry_callable, entry_script_path)
        return constants.RUN_EXIT_SUCCESS
    except bdb.BdbQuit:
        return constants.RUN_EXIT_TERMINATED_BY_USER
