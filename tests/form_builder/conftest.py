# pyright: reportAttributeAccessIssue=false
"""PySide6-only collection for the form-builder lanes.

``testing/run_form_builder_checks.py`` runs this directory on FreeCAD 1.1's
Python 3.11 and on ``~/opt/freecad`` AppRun with ``CBCS_QT_API=pyside6``.
On any other binding every test in the directory is skipped, so a PySide2
shard stays green.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("CBCS_FB_VALIDATE", "1")


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "oracle: compare form-builder output with Qt uic or Designer",
    )
    config.addinivalue_line(
        "markers",
        "perf: form-builder speed budget; the gate records os.getloadavg beside the result",
    )
    config.addinivalue_line(
        "markers",
        "soak: long seeded soak runs (minutes); run on demand with -m soak, not in the gate lanes",
    )
    config.addinivalue_line(
        "markers",
        'parity(*ids): proves R3 parity items, e.g. parity("R3-145"); read by tools/form_builder_parity.py',
    )
    config.addinivalue_line(
        "markers",
        'pain(*ids): proves ranked pains, e.g. pain("P-3"); read by tools/form_builder_parity.py',
    )
    config.addinivalue_line(
        "markers",
        'logic(*ids): proves logic scenarios and features, e.g. logic("L-line-total-live")',
    )
    config.addinivalue_line(
        "markers",
        "pg93: PostgreSQL 9.3 tests; opt-in, not part of the unit lane",
    )


def _pyside6_skip_reason() -> str | None:
    try:
        from app.bootstrap.qt_binding_choice import select_binding
    except ImportError as exc:
        return "form builder tests require PySide6 (%s)" % exc
    try:
        binding = select_binding()
    except ImportError as exc:
        return "form builder tests require PySide6 (%s)" % exc
    if binding != "PySide6":
        return "form builder tests require PySide6 (active binding is %s)" % binding
    return None


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    # Directory conftest hooks still see the whole session. Touch only this folder.
    del config
    reason = _pyside6_skip_reason()
    if reason is None:
        return
    skip = pytest.mark.skip(reason=reason)
    root = Path(__file__).resolve().parent
    for item in items:
        path = Path(str(getattr(item, "path", item.fspath)))
        if path == root or root in path.parents:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def qapp():  # type: ignore[no-untyped-def]
    """Offscreen ``QApplication`` for form-builder tests on PySide6."""
    pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)
    from app.qt.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app
    # setMimeData then process exit segfaults under this offscreen build.
    clipboard = app.clipboard()
    if clipboard is not None:
        clipboard.clear()


@pytest.fixture
def connections_module():
    """Load a rendered ``cbcs_connections`` module and close its databases afterwards.

    The module is registered on ``sys.modules`` for the test and removed in
    teardown, after ``close_all()``. A test that fails mid-way still releases
    the SQLite connection it opened.
    """
    import importlib.util
    import sys
    import uuid
    from typing import Any, cast

    from app.features.form_builder.engine.data.connections_module import render_connections_module

    loaded = []

    def load(directory, connection_set, slug):
        text = render_connections_module(connection_set, project_slug=slug)
        path = os.path.join(str(directory), "cbcs_connections.py")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        name = "cbcs_connections_%s" % uuid.uuid4().hex
        spec = importlib.util.spec_from_file_location(name, path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        loaded.append(name)
        getattr(spec.loader, "exec_module")(module)
        return cast(Any, module), text

    yield load
    for name in loaded:
        module = sys.modules.pop(name, None)
        closer = getattr(module, "close_all", None)
        if closer is not None:
            closer()
