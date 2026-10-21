"""Editor side of the preview process (CONTRACTS.md section 10.3). [M2.5]

Built on ``app.run.process_supervisor.ProcessSupervisor`` (argv list, no shell,
``start_new_session=True``, killpg on stop) and the boot payload from
``app.run.runtime_launch.build_runpy_bootstrap_payload`` launching the repo-root
script ``run_form_preview.py`` under the FreeCAD AppRun. Supervisor events
arrive on reader threads; the pool marshals them to the GUI thread with a
queued Qt signal before decoding or touching any widget.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Tuple

from app.features.form_builder.engine.ipc.protocol import ChildMessage, HostMessage

#: Restart delays after consecutive crashes (seconds). After the last one, a
#: crash opens the circuit: preview is off until the user presses Retry.
BACKOFF_SCHEDULE: Tuple[float, ...] = (0.0, 1.0, 4.0, 15.0)
#: Crashes older than this do not count toward the backoff position.
CRASH_WINDOW_SECONDS = 120.0
#: The child exits on its own after this long with no views.
IDLE_EXIT_SECONDS = 600.0
#: Hello must be answered within this long (cold AppRun start included).
HANDSHAKE_TIMEOUT_SECONDS = 30.0
#: A request without a response after this long fails with "timeout".
REQUEST_TIMEOUT_SECONDS = 20.0
#: Shutdown grace before SIGTERM to the process group, then SIGKILL after 2 s more.
SHUTDOWN_GRACE_SECONDS = 2.0
#: Ping period while views are open; two consecutive misses = hung.
PING_INTERVAL_SECONDS = 5.0
MISSED_PINGS_FOR_HANG = 2
#: Default of the pre-warm setting: spawn the child when the first form opens.
PREWARM_DEFAULT = True


PoolState = str  # "stopped" | "starting" | "ready" | "backoff" | "circuit_open"


@dataclass(frozen=True)
class PoolStatus:
    state: PoolState
    child_pid: Optional[int]
    crashes_in_window: int
    next_restart_in: Optional[float]
    last_error: Optional[str]


class PreviewPool:
    """Process-wide: ONE warm child shared by every open form; each form tab is a
    view (``view_id`` = a uuid4 hex made when the tab first previews).

    * Pre-warm is on by default: the child is spawned when the first form opens.
      With the setting off, it starts on the first preview/Try request.
    * Hang: a request timeout or MISSED_PINGS_FOR_HANG missed pings -> kill the
      process group and handle it exactly like a crash (FB601, backoff).
    * Handshake: wait for Ready and the Hello response; a mismatch is FB603 and
      the pool goes to circuit_open (retrying cannot fix a version mismatch).
    * Requests are matched by ``request_id`` (uuid4 hex). Per view at most one
      LoadForm/UpdateForm is in flight; later updates coalesce to the newest.
    * Crash (exit while views open, or three ProtocolViolations): every view gets
      a FB601 diagnostic in its session with the last 40 stderr lines; restart
      after the next BACKOFF_SCHEDULE delay; views re-load on restart.
    * Shutdown on editor exit: Shutdown request, then ``supervisor.stop()``.
      ``tests/conftest.py`` reaps by the ``run_form_preview.py`` marker.
    * The editor process never imports user code for preview purposes; all of it
      runs in the child.
    """

    @classmethod
    def shared(cls) -> "PreviewPool":
        ...

    def request(self, message: HostMessage, on_response: Callable[[ChildMessage], None]) -> str:
        """Send a request (starting the child if needed); returns the request id."""
        ...

    def subscribe(self, view_id: Optional[str], listener: Callable[[ChildMessage], None]) -> Callable[[], None]:
        """Events for one view (Log, ViewClosed, ErrorReport, NeedSecret), or all
        events when ``view_id`` is None."""
        ...

    def status(self) -> PoolStatus:
        ...

    def retry(self) -> None:
        """Close the circuit and start again."""
        ...

    def shutdown(self) -> None:
        ...
