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

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def qapp():  # type: ignore[no-untyped-def]
    """Session-scoped ``QApplication`` shared by all Qt-touching tests."""
    pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)
    from PySide2.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


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
