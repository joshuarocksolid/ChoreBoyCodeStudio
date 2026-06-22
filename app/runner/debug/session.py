"""Debug session entrypoint for the runner subprocess."""

from __future__ import annotations

import bdb
import sys
import threading
from typing import Any, Callable, cast

from app.core import constants
from app.run.run_manifest import RunManifest
from app.runner.debug.command_loop import RunnerDebugHost

__all__ = ["run_debug_session"]


def run_debug_session(manifest: RunManifest, entry_callable: Callable[[str], None], entry_script_path: str) -> int:
    """Run entry script under structured debugger control."""

    host = RunnerDebugHost(manifest)
    host.connect()
    threading.settrace(host.debugger.trace_dispatch)
    host.debugger.reset()
    cast(Any, host.debugger)._set_stopinfo(  # noqa: SLF001 - keep tracing active without first-line stop
        None,
        None,
        -1,
    )
    # CC-22 observer-path: optional debug pause, then propagate to process exit.
    try:
        sys.settrace(host.debugger.trace_dispatch)
        entry_callable(entry_script_path)
        return constants.RUN_EXIT_SUCCESS
    except bdb.BdbQuit:
        return constants.RUN_EXIT_TERMINATED_BY_USER
    except Exception:
        exc_info = sys.exc_info()
        if (
            exc_info[0] is not None
            and exc_info[1] is not None
            and exc_info[2] is not None
            and host.exception_policy.stop_on_uncaught_exceptions
        ):
            host.pause_on_uncaught_exception(exc_info)  # type: ignore[arg-type]
        raise
    finally:
        threading.settrace(None)
        sys.settrace(None)
        host.close()
