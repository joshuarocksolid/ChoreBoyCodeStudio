"""Empty page containers draw their caption; a drop makes the first page (UX-CONT-009)."""

from __future__ import annotations

import pytest

from app.features.form_builder.qtside.canvas.core.overlay import Caption, build_static
from app.features.form_builder.engine.query.drop_target import AcceptedDrop, DropPayload, hosts_from
from app.features.form_builder.engine.query.drop_target import resolve_drop
from tests.form_builder.qtside.test_canvas_core import _entry, _index, _nid, _opened, _view

pytestmark = pytest.mark.unit

EMPTY = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <property name="geometry"><rect><x>0</x><y>0</y><width>400</width><height>300</height></rect></property>
  <widget class="%s" name="%s">
   <property name="geometry"><rect><x>20</x><y>20</y><width>300</width><height>200</height></rect></property>
  </widget>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


@pytest.mark.parametrize(
    ("cls", "name", "caption"),
    [
        ("QTabWidget", "tabs", "No pages. Use + or Pages > Insert page."),
        ("QWizard", "wizard", "No steps. Use + or Pages > Insert page."),
        ("QMdiArea", "mdi", "No windows. Use Pages > Add window."),
    ],
)
def test_an_empty_page_container_draws_its_caption(cls, name, caption) -> None:  # type: ignore[no-untyped-def]
    with _opened(EMPTY % (cls, name)) as session:
        view = _view()
        form = _nid(session, "Form")
        page = _nid(session, name)
        index = _index((_entry(form, "widget", (0, 0, 400, 300), None), _entry(page, "widget", (20, 20, 300, 200), form)))
        static = build_static(session.document, index, view)
        captions = [item.lines for item in static.items if isinstance(item, Caption)]
        assert (caption,) in captions


def test_a_drop_on_an_empty_tab_widget_makes_the_first_page() -> None:
    with _opened(EMPTY % ("QTabWidget", "tabs")) as session:
        tabs = _nid(session, "tabs")
        from app.features.form_builder.engine.query.drop_target import _widget_host

        host = _widget_host(session.document, {tabs: _rect(20, 20, 300, 200)}, tabs, "tabs")
        assert host is not None
        target = resolve_drop(host, (100, 100), DropPayload("widget"))
        assert isinstance(target, AcceptedDrop) and target.action == "new_page"


def _rect(x: int, y: int, w: int, h: int):  # type: ignore[no-untyped-def]
    from app.features.form_builder.engine.query.hit_index import Rect

    return Rect(x, y, w, h)
