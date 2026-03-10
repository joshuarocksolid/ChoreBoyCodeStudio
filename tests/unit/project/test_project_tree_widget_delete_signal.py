"""Unit tests for ProjectTreeWidget — delete signal and mimeData URL embedding."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtCore import Qt  # noqa: E402
from PySide2.QtTest import QTest  # noqa: E402
from PySide2.QtWidgets import QApplication, QTreeWidgetItem  # noqa: E402

from app.project.project_tree_widget import ProjectTreeWidget  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module", autouse=True)
def _qapp():  # type: ignore[no-untyped-def]
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture()
def tree_widget():  # type: ignore[no-untyped-def]
    widget = ProjectTreeWidget()
    return widget


def test_delete_key_emits_delete_requested(tree_widget: ProjectTreeWidget) -> None:
    received: list[bool] = []
    tree_widget.deleteRequested.connect(lambda: received.append(True))
    QTest.keyPress(tree_widget, Qt.Key_Delete)
    assert received == [True]


def test_backspace_key_emits_delete_requested(tree_widget: ProjectTreeWidget) -> None:
    received: list[bool] = []
    tree_widget.deleteRequested.connect(lambda: received.append(True))
    QTest.keyPress(tree_widget, Qt.Key_Backspace)
    assert received == [True]


def test_other_key_does_not_emit_delete_requested(tree_widget: ProjectTreeWidget) -> None:
    received: list[bool] = []
    tree_widget.deleteRequested.connect(lambda: received.append(True))
    QTest.keyPress(tree_widget, Qt.Key_A)
    assert received == []


# ---------------------------------------------------------------------------
# mimeData — file URL embedding for cross-widget drag-and-drop
# ---------------------------------------------------------------------------

_PATH_DATA_ROLE = 256


class TestMimeDataUrls:
    def test_mime_data_includes_file_urls(self, tree_widget: ProjectTreeWidget) -> None:
        item = QTreeWidgetItem(tree_widget, ["script.py"])
        item.setData(0, _PATH_DATA_ROLE, "/home/user/project/script.py")

        mime = tree_widget.mimeData([item])

        assert mime.hasUrls()
        urls = mime.urls()
        assert len(urls) == 1
        assert urls[0].toLocalFile() == "/home/user/project/script.py"

    def test_mime_data_multiple_items(self, tree_widget: ProjectTreeWidget) -> None:
        item_a = QTreeWidgetItem(tree_widget, ["a.py"])
        item_a.setData(0, _PATH_DATA_ROLE, "/project/a.py")
        item_b = QTreeWidgetItem(tree_widget, ["b.py"])
        item_b.setData(0, _PATH_DATA_ROLE, "/project/b.py")

        mime = tree_widget.mimeData([item_a, item_b])

        local_paths = [u.toLocalFile() for u in mime.urls()]
        assert local_paths == ["/project/a.py", "/project/b.py"]

    def test_mime_data_skips_items_without_path(self, tree_widget: ProjectTreeWidget) -> None:
        item = QTreeWidgetItem(tree_widget, ["no-path"])

        mime = tree_widget.mimeData([item])

        assert not mime.hasUrls()
