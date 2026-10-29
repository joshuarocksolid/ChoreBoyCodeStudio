# pyright: reportAttributeAccessIssue=false
"""M5.R review repros on the canvas (UX-OVL-003)."""

from __future__ import annotations

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.features.form_builder.integration.canvas import FormCanvas  # noqa: E402
from app.features.form_builder.qtside.canvas.core.frame import Caption  # noqa: E402
from app.features.form_builder.qtside.canvas.layers.tab_order import TabOrderState  # noqa: E402
from app.qt.QtWidgets import QApplication, QWidget  # noqa: E402
from tests.form_builder.qtside.support import opened  # noqa: E402
from tests.form_builder.qtside.test_m37a_canvas import _NEST, _Host, _require  # noqa: E402

pytestmark = [pytest.mark.unit]


def test_drop_widgets_here_fades_with_the_layout_frames_under_tab_order() -> None:
    _require()
    with opened(_NEST) as (session, realizer):
        parent = QWidget()
        parent.resize(640, 480)
        canvas = FormCanvas(session, realizer, _Host(), parent)
        canvas.resize(640, 480)
        parent.show()
        app = QApplication.instance()
        assert app is not None
        app.processEvents()

        def hints() -> list:
            return [i for i in canvas.overlay().items if isinstance(i, Caption) and i.lines == ("Drop widgets here",)]

        assert hints() and all(hint.alpha == 1.0 for hint in hints())
        canvas.show_layer("tab_order", TabOrderState(order=()))
        app.processEvents()
        assert hints() and all(hint.alpha < 1.0 for hint in hints())
        canvas.hide_layer("tab_order")
        app.processEvents()
        assert all(hint.alpha == 1.0 for hint in hints())
        canvas.dispose()
        parent.deleteLater()
