# pyright: reportAttributeAccessIssue=false
"""Canvas screenshots for the M4.2 container states (light and dark). Runs only with CBCS_FB_SCREENSHOT_DIR set."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.features.form_builder.integration.canvas import FormCanvas
from app.qt.QtWidgets import QWidget
from app.shell.theme_tokens import tokens_from_palette
from tests.form_builder.qtside.support import form, opened
from tests.form_builder.qtside.test_m4_mdi import MDI
from tests.form_builder.qtside.test_m4_scroll_area import AREA, _Host, _flush
from tests.form_builder.qtside.test_m4_pages_canvas import TABS
from tests.form_builder.qtside.test_m4_wizard_canvas import WIZARD

pytestmark = pytest.mark.usefixtures("qapp")

DOCK = form(
    'class="QMainWindow" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>600</width><height>400</height></rect></property>
  <widget class="QWidget" name="centralwidget">
   <property name="geometry"><rect><x>120</x><y>20</y><width>440</width><height>360</height></rect></property>
  </widget>
  <widget class="QDockWidget" name="tools">
   <attribute name="dockWidgetArea"><number>1</number></attribute>
   <property name="windowTitle"><string>Tools</string></property>
   <widget class="QWidget" name="dockWidgetContents">
    <property name="geometry"><rect><x>0</x><y>0</y><width>100</width><height>300</height></rect></property>
   </widget>
  </widget>
""",
)

SUBJECTS = {
    "tab_pages": TABS,
    "scroll_area_scrolled": AREA,
    "mdi_windows": MDI,
    "dock_docked_left": DOCK,
    "wizard_step": WIZARD,
}


@pytest.mark.parametrize("mode", ["light", "dark"])
@pytest.mark.parametrize("subject", sorted(SUBJECTS))
def test_capture_container_state(qapp, subject: str, mode: str) -> None:  # type: ignore[no-untyped-def]
    folder = os.environ.get("CBCS_FB_SCREENSHOT_DIR")
    if not folder:
        pytest.skip("CBCS_FB_SCREENSHOT_DIR is not set")
    out = Path(folder)
    out.mkdir(parents=True, exist_ok=True)
    tokens = tokens_from_palette(qapp.palette(), force_mode=mode)
    with opened(SUBJECTS[subject]) as (session, realizer):
        parent = QWidget()
        parent.resize(900, 620)
        host = _Host()
        canvas = FormCanvas(session, realizer, host, parent)
        canvas.resize(900, 620)
        canvas.apply_theme(tokens)
        parent.show()
        canvas.setFocus()
        _flush()
        if subject == "scroll_area_scrolled":
            area = canvas.page_widget().findChild(object, "scroll")  # type: ignore[union-attr]
            if area is not None:
                area.verticalScrollBar().setValue(60)
        _flush()
        canvas.grab().save(str(out / ("%s_%s.png" % (subject, mode))))
        canvas.dispose()
        parent.deleteLater()
