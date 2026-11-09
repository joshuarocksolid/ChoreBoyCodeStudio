# pyright: reportAttributeAccessIssue=false
"""L4 shots: the + chip after a rename, and the refusal badge on an unknown enum. Skips without the shot folder."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.features.form_builder.engine.query.selection import SelectionSource
from app.qt.QtTest import QTest
from app.shell.theme_tokens import tokens_from_palette
from tests.form_builder.qtside.support import form, opened
from tests.form_builder.qtside.test_canvas_text import _canvas, _flush, _open, _qt_key
from tests.form_builder.qtside.test_m4_title_editor import PAGES

pytestmark = pytest.mark.usefixtures("qapp")

_MODES = ("light", "high_contrast_dark")
_ENUM = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>360</width><height>160</height></rect></property>
  <widget class="QLineEdit" name="email">
   <property name="geometry"><rect><x>20</x><y>30</y><width>200</width><height>28</height></rect></property>
   <property name="echoMode"><enum>QLineEdit::SomeFutureMode</enum></property>
  </widget>
""",
)


def _folder() -> Path:
    raw = os.environ.get("CBCS_FB_SCREENSHOT_DIR") or ""
    if not raw:
        pytest.skip("CBCS_FB_SCREENSHOT_DIR is not set")
    path = Path(raw)
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.mark.timeout(120)
def test_l4_shots(qapp) -> None:  # type: ignore[no-untyped-def]
    out = _folder()
    for mode in _MODES:
        tokens = tokens_from_palette(qapp.palette(), force_mode=mode)
        with opened(PAGES) as (session, realizer):
            canvas, parent = _canvas(session, realizer)
            canvas.apply_theme(tokens)
            page = session.document.by_name("tab_a")[0]
            session.selection.set((page,), current=page, source=SelectionSource.CANVAS)
            _flush()
            edit = _open(canvas)
            QTest.keyClicks(edit, "A much longer title here")
            QTest.keyClick(edit, _qt_key("Key_Return"))
            _flush()
            session.selection.set((session.document.by_name("tabs")[0],), source=SelectionSource.PROGRAM)
            _flush()
            canvas.grab().save(str(out / ("page-chip-after-rename-%s.png" % mode)))
            canvas.dispose()
            parent.deleteLater()
        with opened(_ENUM) as (session, realizer):
            canvas, parent = _canvas(session, realizer)
            canvas.apply_theme(tokens)
            _flush()
            canvas.grab().save(str(out / ("refusal-badge-%s.png" % mode)))
            canvas.dispose()
            parent.deleteLater()
