"""Reap nested AppRun runtime children leaked by editor-side supervisors in tests."""

from __future__ import annotations

import os
import signal
import time

_RUNTIME_CHILD_MARKERS = ("run_plugin_host.py", "run_runner.py")


def read_proc_cmdline(pid: int) -> str:
    try:
        with open("/proc/%d/cmdline" % pid, "rb") as handle:
            return handle.read().replace(b"\x00", b" ").decode("utf-8", "replace")
    except OSError:
        return ""


def read_proc_ppid(pid: int) -> int | None:
    try:
        with open("/proc/%d/status" % pid, "rb") as handle:
            for line in handle.read().decode("utf-8", "replace").splitlines():
                if line.startswith("PPid:"):
                    return int(line.split()[1])
    except (OSError, ValueError):
        return None
    return None


def iter_pids() -> list[int]:
    pids: list[int] = []
    try:
        entries = os.listdir("/proc")
    except OSError:
        return pids
    for entry in entries:
        if entry.isdigit():
            pids.append(int(entry))
    return pids


def descendant_pids(root_pid: int) -> set[int]:
    children: dict[int, list[int]] = {}
    for pid in iter_pids():
        ppid = read_proc_ppid(pid)
        if ppid is not None:
            children.setdefault(ppid, []).append(pid)
    descendants: set[int] = set()
    stack = list(children.get(root_pid, []))
    while stack:
        pid = stack.pop()
        if pid in descendants:
            continue
        descendants.add(pid)
        stack.extend(children.get(pid, []))
    return descendants


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def leaked_runtime_child_pids(root_pid: int | None = None) -> list[int]:
    """Return descendant PIDs whose cmdline matches run_plugin_host or run_runner."""
    if not os.path.isdir("/proc"):
        return []
    resolved_root = os.getpid() if root_pid is None else root_pid
    return [
        pid
        for pid in descendant_pids(resolved_root)
        if any(marker in read_proc_cmdline(pid) for marker in _RUNTIME_CHILD_MARKERS)
    ]


def reap_leaked_runtime_children(*, root_pid: int | None = None) -> None:
    """SIGTERM/SIGKILL any leaked run_plugin_host/run_runner descendants."""
    targets = leaked_runtime_child_pids(root_pid)
    if not targets:
        return
    for pid in targets:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    deadline = time.time() + 2.0
    while time.time() < deadline:
        if not any(pid_alive(pid) for pid in targets):
            return
        time.sleep(0.05)
    for pid in targets:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
