"""Unit tests for toolbar icon factories."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtWidgets import QApplication  # noqa: E402

from app.shell.toolbar_icons import build_toolbar_icon  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module", autouse=True)
def _qapp(request: pytest.FixtureRequest):  # type: ignore[no-untyped-def]
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _icon_pixmap_bytes(icon, size: int = 16) -> bytes:
    pm = icon.pixmap(size, size)
    image = pm.toImage()
    width = image.width()
    height = image.height()
    chunks: list[bytes] = []
    for y in range(height):
        for x in range(width):
            chunks.append(image.pixel(x, y).to_bytes(4, "little"))
    return b"".join(chunks)


def test_run_file_icon_differs_from_run_project_icon() -> None:
    accent = "#5B8CFF"
    file_icon = build_toolbar_icon("shell.action.run.run", accent)
    project_icon = build_toolbar_icon("shell.action.run.runProject", accent)

    assert file_icon is not None
    assert project_icon is not None
    assert _icon_pixmap_bytes(file_icon) != _icon_pixmap_bytes(project_icon)


def test_debug_file_icon_differs_from_debug_project_icon() -> None:
    accent = "#5B8CFF"
    file_icon = build_toolbar_icon("shell.action.run.debug", accent)
    project_icon = build_toolbar_icon("shell.action.run.debugProject", accent)

    assert file_icon is not None
    assert project_icon is not None
    assert _icon_pixmap_bytes(file_icon) != _icon_pixmap_bytes(project_icon)


def test_run_file_icon_differs_from_debug_file_icon() -> None:
    accent = "#5B8CFF"
    run_file = build_toolbar_icon("shell.action.run.run", accent)
    debug_file = build_toolbar_icon("shell.action.run.debug", accent)

    assert run_file is not None
    assert debug_file is not None
    assert _icon_pixmap_bytes(run_file) != _icon_pixmap_bytes(debug_file)
