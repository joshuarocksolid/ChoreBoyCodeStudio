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

import pytest

from testing.runtime_child_reaper import reap_leaked_runtime_children

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _require_pytest_timeout(config: pytest.Config) -> None:
    timeout_ini = config.getini("timeout")
    if timeout_ini in (None, "", 0):
        return
    try:
        import pytest_timeout  # noqa: F401
    except ImportError:
        pytest.exit(
            "pytest-timeout is required for the configured global timeout in pyproject.toml. "
            "Install it into the AppRun site-packages: "
            "pip3 install pytest-timeout --target=/opt/freecad/usr/lib/python3.11/site-packages/",
            returncode=1,
        )


def pytest_configure(config: pytest.Config) -> None:
    _require_pytest_timeout(config)


def _should_reap_after_test(item: pytest.Item) -> bool:
    """Reap only after tests likely to spawn nested AppRun children."""
    nodeid = item.nodeid.replace("\\", "/")
    if "/integration/" in nodeid or "/runtime_parity/" in nodeid:
        return True
    if "/unit/plugins/" in nodeid:
        return True
    if "/unit/shell/test_main_window_background_teardown.py" in nodeid:
        return True
    return False


@pytest.fixture(autouse=True)
def _reap_runtime_children_after_test(request: pytest.FixtureRequest) -> None:
    yield
    if _should_reap_after_test(request.node):
        reap_leaked_runtime_children()


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
    reap_leaked_runtime_children()


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
