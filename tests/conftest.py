"""Root test configuration -- session-scoped Qt singleton + Shiboken teardown.

PySide2's Shiboken binding manager walks its wrapper table during C++ static
destruction.  If Python-side wrappers still reference already-freed C++ Qt
objects, the destructor segfaults.  Running GC before interpreter teardown lets
Python release its side of the wrapper graph in a controlled order, reducing the
number of stale entries the Shiboken destructor has to walk.  The companion
``os._exit()`` call in ``run_tests.py`` prevents the destructor from running at
all as a backstop.

The ``qapp`` fixture is the canonical way for any Qt-touching test (unit,
integration, or performance) to obtain a ``QApplication``.  Using a single
session-scoped instance avoids paying Qt + offscreen-platform-plugin cold-start
cost in every test module.  Tests that need a fresh ``QApplication`` for
isolation reasons (for example, teardown / shutdown tests) should still create
their own and document why.
"""
from __future__ import annotations

import gc
import os
import signal
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Boot-script markers for the nested AppRun children that editor-side supervisors
# spawn (ProcessSupervisor.start uses ``start_new_session=True``, so these survive
# the parent if a test leaks them). The reaper below targets only descendants of
# THIS pytest process, so concurrent test sessions are never affected.
_RUNTIME_CHILD_MARKERS = ("run_plugin_host.py", "run_runner.py")


def _read_proc_cmdline(pid: int) -> str:
    try:
        with open("/proc/%d/cmdline" % pid, "rb") as handle:
            return handle.read().replace(b"\x00", b" ").decode("utf-8", "replace")
    except OSError:
        return ""


def _read_proc_ppid(pid: int):  # type: ignore[no-untyped-def]
    try:
        with open("/proc/%d/status" % pid, "rb") as handle:
            for line in handle.read().decode("utf-8", "replace").splitlines():
                if line.startswith("PPid:"):
                    return int(line.split()[1])
    except (OSError, ValueError):
        return None
    return None


def _iter_pids() -> list[int]:
    pids: list[int] = []
    try:
        entries = os.listdir("/proc")
    except OSError:
        return pids
    for entry in entries:
        if entry.isdigit():
            pids.append(int(entry))
    return pids


def _descendant_pids(root_pid: int) -> set[int]:
    children: dict[int, list[int]] = {}
    for pid in _iter_pids():
        ppid = _read_proc_ppid(pid)
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


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _reap_leaked_runtime_children() -> None:
    """SIGTERM/SIGKILL any leaked run_plugin_host/run_runner descendants."""
    if not os.path.isdir("/proc"):
        return
    targets = [
        pid
        for pid in _descendant_pids(os.getpid())
        if any(marker in _read_proc_cmdline(pid) for marker in _RUNTIME_CHILD_MARKERS)
    ]
    if not targets:
        return
    for pid in targets:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    deadline = time.time() + 2.0
    while time.time() < deadline:
        if not any(_pid_alive(pid) for pid in targets):
            return
        time.sleep(0.05)
    for pid in targets:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass


@pytest.fixture(scope="session")
def qapp():  # type: ignore[no-untyped-def]
    """Session-scoped ``QApplication`` shared by all Qt-touching tests."""
    pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)
    from PySide2.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def pytest_sessionfinish(session, exitstatus):  # type: ignore[no-untyped-def]
    """Reap any nested AppRun runtime children leaked by tests in this session."""
    _reap_leaked_runtime_children()


def pytest_unconfigure(config):  # type: ignore[no-untyped-def]
    """Run GC to finalize Python-side Qt wrapper references before shutdown."""
    try:
        from PySide2.QtWidgets import QApplication
    except ImportError:
        return

    app = QApplication.instance()
    if app is None:
        return

    app.processEvents()
    gc.collect()
    app.processEvents()
