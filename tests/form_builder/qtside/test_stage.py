"""Stage keeps an authored page size and owns the readout."""

from __future__ import annotations

import pytest

from app.qt.QtWidgets import QGraphicsScene, QGraphicsView, QLabel, QWidget
from app.features.form_builder.qtside.canvas.core.gesture import EndPreview, PreviewPage
from app.features.form_builder.qtside.canvas.core.space import Size
from app.features.form_builder.qtside.canvas.stage import Stage
from app.features.form_builder.integration.canvas import FormCanvas
from tests.form_builder.qtside.support import form, opened

pytestmark = pytest.mark.usefixtures("qapp")

AUTHORED = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>640</width><height>480</height></rect></property>
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QPushButton" name="ok">
     <property name="text"><string>OK</string></property>
    </widget>
   </item>
  </layout>
""",
)


class _Host:
    def canvas_pressed(self) -> None:
        return None

    def narrate(self, sentence: str) -> None:
        return None

    def hover_changed(self, node: object) -> None:
        return None

    def zoom_changed(self, label: str) -> None:
        return None

    def open_problem(self, node: object) -> None:
        return None

    def open_layout_popover(self, node: object) -> None:
        return None


def test_authored_page_stays_640_by_480_and_the_readout_matches() -> None:
    with opened(AUTHORED) as (session, realizer):
        parent = QWidget()
        parent.resize(960, 720)
        canvas = FormCanvas(session, realizer, _Host(), parent)
        canvas.resize(960, 720)
        canvas.show()
        root = canvas.page_widget()
        assert root is not None
        assert (root.width(), root.height()) == (640, 480)
        readout = canvas.findChild(QLabel, "formBuilder.sizeReadout")
        assert readout is not None
        assert readout.text() == "640 × 480"
        assert canvas.transform().isIdentity()
        canvas.dispose()
        parent.deleteLater()


def test_end_preview_invalidates_when_the_page_size_does_not_change() -> None:
    reasons = []
    with opened(AUTHORED) as (session, realizer):
        view = QGraphicsView()
        view.setScene(QGraphicsScene(view))
        view.resize(960, 720)
        stage = Stage(view, session, realizer, reasons.append)
        stage.place()
        root = realizer.root_widget
        assert root is not None
        assert (root.width(), root.height()) == (640, 480)
        reasons.clear()
        stage.run(EndPreview())
        assert reasons == ["root_resize"]
        assert (root.width(), root.height()) == (640, 480)
        view.deleteLater()


def test_page_preview_resizes_live_and_keeps_the_top_left() -> None:
    reasons = []
    with opened(AUTHORED) as (session, realizer):
        view = QGraphicsView()
        view.setScene(QGraphicsScene(view))
        view.resize(960, 720)
        stage = Stage(view, session, realizer, reasons.append)
        stage.place()
        origin = stage.view_map().page_origin
        reasons.clear()
        stage.run(PreviewPage(Size(800, 600)))
        root = realizer.root_widget
        assert root is not None
        assert (root.width(), root.height()) == (800, 600)
        assert stage.view_map().page_origin == origin
        readout = view.findChild(QLabel, "formBuilder.sizeReadout")
        assert readout is not None
        assert readout.text() == "800 × 600"
        assert reasons == []
        stage.run(EndPreview())
        assert (root.width(), root.height()) == (640, 480)
        assert readout.text() == "640 × 480"
        view.deleteLater()
