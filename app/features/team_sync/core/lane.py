"""One ordered lane per project so the repo and the ledger have a single writer.

Status and poll wait while a user action is queued. A running status still
finishes, because stopping dulwich in the middle of a write is how the index
gets corrupted. The same thread may re-enter, since status() calls incoming().
"""

from __future__ import annotations

import threading
from typing import Callable, TypeVar

T = TypeVar("T")

_USER = frozenset(
    {
        "share",
        "accept_invite",
        "send",
        "share_experiment",
        "save_only",
        "post_note",
        "accept",
        "dismiss",
        "resolve",
        "finish_combine",
        "cancel_combine",
        "restore",
        "undo_change",
        "copy_change",
        "set_aside",
        "bring_back",
        "mark_milestone",
        "start_experiment",
        "switch_line",
        "bring_experiment_in",
        "delete_experiment",
        "remove_member",
        "export_bundle",
        "import_bundle",
        "close",
    }
)
_REFRESH = frozenset(
    {
        "status",
        "feed",
        "incoming",
        "mailboxes",
        "pending_invites",
        "invite_detail",
        "incoming_diff",
        "combine_state",
        "history",
        "change_diff",
        "working_diff",
        "blame",
        "poll",
    }
)


class ProjectLane:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._gate = threading.Condition()
        self._user_waiting = 0
        self._owner: int | None = None
        self._depth = 0

    def call(self, user: bool, fn: Callable[[], T]) -> T:
        self._acquire(user)
        try:
            return fn()
        finally:
            self._release(user)

    def _acquire(self, user: bool) -> None:
        me = threading.get_ident()
        with self._gate:
            if self._owner == me:
                self._depth += 1
                return
            if user:
                self._user_waiting += 1
            else:
                while self._user_waiting:
                    self._gate.wait()
        try:
            self._lock.acquire()
        except BaseException:
            with self._gate:
                if user:
                    self._user_waiting -= 1
                self._gate.notify_all()
            raise
        with self._gate:
            self._owner = me
            self._depth = 1

    def _release(self, user: bool) -> None:
        me = threading.get_ident()
        unlock = False
        with self._gate:
            if self._owner != me:
                return
            self._depth -= 1
            if self._depth > 0:
                return
            self._owner = None
            unlock = True
            if user:
                self._user_waiting -= 1
            self._gate.notify_all()
        if unlock:
            self._lock.release()


def bind_project_lane(service: object) -> None:
    lane = service._lane  # type: ignore[attr-defined]
    for name in _USER | _REFRESH:
        original = getattr(service, name)
        user = name in _USER
        setattr(service, name, _bound(lane, original, user))


def _bound(lane: ProjectLane, original: Callable[..., T], user: bool) -> Callable[..., T]:
    def wrapped(*args: object, **kwargs: object) -> T:
        return lane.call(user, lambda: original(*args, **kwargs))

    return wrapped


__all__ = ["ProjectLane", "bind_project_lane"]
