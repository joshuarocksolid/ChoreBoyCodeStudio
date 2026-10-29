# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportOptionalMemberAccess=false
"""The canvas hands desktop files to a registered handler (the M5.2 seam)."""

from __future__ import annotations

import pytest

from app.features.form_builder.engine.project.templates import build_template_ui
from app.features.form_builder.integration.canvas import FormCanvas
from app.features.form_builder.qtside.canvas import file_drops
from app.qt.QtCore import QMimeData, QPointF, QUrl, Qt
from app.qt.QtGui import QDropEvent
from app.qt.QtWidgets import QApplication, QWidget
from tests.form_builder.qtside.support import opened

pytestmark = pytest.mark.usefixtures("qapp")


class _Host:
    def __init__(self) -> None:
        self.said = []

    def narrate(self, sentence: str) -> None:
        self.said.append(sentence)

    def __getattr__(self, name: str):  # type: ignore[no-untyped-def]
        return lambda *args, **kwargs: None


def test_a_dropped_file_reaches_the_registered_handler_with_the_node_under_the_pointer() -> None:
    seen = []
    host = _Host()
    with opened(build_template_ui("widget", "plain")) as (session, realizer):
        parent = QWidget()
        parent.resize(900, 700)
        canvas = FormCanvas(session, realizer, host, parent)
        canvas.resize(900, 700)
        parent.show()
        QApplication.processEvents()
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile("/tmp/logo.png")])

        def drop() -> None:
            event = QDropEvent(QPointF(canvas.viewport().rect().center()), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
            canvas.dropEvent(event)

        host.said.clear()
        drop()  # no handler: ignored
        assert host.said == []
        remove = file_drops.register_file_drop(lambda target, paths: seen.append((target, paths)) or "Added logo.png")
        drop()
        assert seen and seen[0][1] == ("/tmp/logo.png",) and host.said == ["Added logo.png"]
        remove()
        drop()
        assert len(seen) == 1
        canvas.dispose()
        parent.deleteLater()


def test_a_handler_that_does_not_know_the_files_lets_the_next_one_answer() -> None:
    remove_a = file_drops.register_file_drop(lambda target, paths: None)
    remove_b = file_drops.register_file_drop(lambda target, paths: "second")
    try:
        assert file_drops.dispatch(1, ("/x",)) == "second"  # type: ignore[arg-type]
    finally:
        remove_a()
        remove_b()
