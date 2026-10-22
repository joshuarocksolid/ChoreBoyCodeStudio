"""Preview timing and crash policy (CONTRACTS.md section 10.3).

The numbers live here so the Qt-free director and the editor pool share one
source. ``qtside.preview.pool`` re-exports them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Tuple

#: Restart delays after consecutive crashes (seconds). After the last one, a
#: crash opens the circuit: preview is off until the user presses Retry.
BACKOFF_SCHEDULE: Tuple[float, ...] = (0.0, 1.0, 4.0, 15.0)
#: Crashes older than this do not count toward the backoff position.
CRASH_WINDOW_SECONDS = 120.0
#: The child exits on its own after this long with no views.
IDLE_EXIT_SECONDS = 600.0
#: Hello must be answered within this long (cold AppRun start included).
HANDSHAKE_TIMEOUT_SECONDS = 30.0
#: A request without a response after this long fails with a hang.
REQUEST_TIMEOUT_SECONDS = 20.0
#: Shutdown grace before SIGTERM to the process group, then SIGKILL.
SHUTDOWN_GRACE_SECONDS = 2.0
#: Ping period while views are open; two consecutive misses means hung.
PING_INTERVAL_SECONDS = 5.0
MISSED_PINGS_FOR_HANG = 2
#: Default of the pre-warm setting: spawn the child when the first form opens.
PREWARM_DEFAULT = True
STDERR_TAIL_LINES = 40
PROTOCOL_VIOLATIONS_BEFORE_RESTART = 3


@dataclass(frozen=True)
class DirectorConfig:
    """Knobs for :class:`app.features.form_builder.engine.ipc.director.PreviewDirector`.

    Production uses the module constants. Tests pass a shorter schedule.
    """

    backoff: Tuple[float, ...] = BACKOFF_SCHEDULE
    crash_window: float = CRASH_WINDOW_SECONDS
    handshake_timeout: float = HANDSHAKE_TIMEOUT_SECONDS
    request_timeout: float = REQUEST_TIMEOUT_SECONDS
    shutdown_grace: float = SHUTDOWN_GRACE_SECONDS
    ping_interval: float = PING_INTERVAL_SECONDS
    missed_pings: int = MISSED_PINGS_FOR_HANG
    prewarm: bool = PREWARM_DEFAULT


def prewarm_from_environ(environ: Mapping[str, str]) -> bool:
    """Read ``CBCS_FORM_PREVIEW_PREWARM``. Empty keeps :data:`PREWARM_DEFAULT`."""
    raw = environ.get("CBCS_FORM_PREVIEW_PREWARM", "").strip().lower()
    if raw in {"0", "false", "off", "no"}:
        return False
    if raw in {"1", "true", "on", "yes"}:
        return True
    return PREWARM_DEFAULT
