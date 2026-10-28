# pyright: reportAttributeAccessIssue=false
"""Stand-ins for OpenGL widgets and Qt Quick views (UX-CONT-017, R3-110, R3-122)."""

from __future__ import annotations

import gc
import sys

import pytest

from app.qt.QtGui import QOpenGLContext
from app.features.form_builder.engine.codegen.api import generate_form_module
from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.ui4.reader import read_ui
from app.features.form_builder.engine.ui4.writer import write_ui
from app.features.form_builder.qtside.realize.stand_in import StandInWidget
from tests.form_builder.qtside.support import form, opened

pytestmark = pytest.mark.usefixtures("qapp")

STAND = form(
    'class="QWidget" name="Form"',
    """
  <layout class="QVBoxLayout" name="verticalLayout">
   <item><widget class="QOpenGLWidget" name="glView"/></item>
   <item><widget class="QQuickWidget" name="quickView"/></item>
  </layout>
""",
)


def _qml_engines() -> int:
    """Live QQmlEngine wrappers. Zero when the QML module was never imported."""
    qml = sys.modules.get("PySide6.QtQml")
    engine_type = getattr(qml, "QQmlEngine", None) if qml is not None else None
    if engine_type is None:
        return 0
    return sum(1 for obj in gc.get_objects() if isinstance(obj, engine_type))


@pytest.mark.parity("R3-110")
def test_gl_and_quick_views_are_drawn_as_labelled_stand_ins() -> None:
    with opened(STAND) as (session, realizer):
        gl = realizer.widget_for(session.document.by_name("glView")[0])
        quick = realizer.widget_for(session.document.by_name("quickView")[0])
        assert isinstance(gl, StandInWidget) and isinstance(quick, StandInWidget)
        assert gl.text() == "OpenGL widget · drawn by your code"
        assert quick.text() == "Qt Quick view · drawn by your code"
        for widget in (gl, quick):
            hint = widget.sizeHint()
            assert hint.width() >= 80 and hint.height() >= 24
            assert widget.minimumSizeHint().width() == 80
            widget.resize(120, 60)
            assert not widget.grab().isNull()
        assert QOpenGLContext.currentContext() is None
        assert _qml_engines() == 0


@pytest.mark.parity("R3-122")
def test_stand_ins_save_round_trip_and_generated_code_imports_the_real_classes(tmp_path) -> None:  # type: ignore[no-untyped-def]
    document = read_ui(STAND, allocator=IdAllocator()).document
    saved = write_ui(document).text
    assert 'class="QOpenGLWidget"' in saved and 'class="QQuickWidget"' in saved
    folder = str(tmp_path)
    scope = FormScope(
        kind="project",
        ui_path=folder + "/stand_in_form.ui",
        project_root=folder,
        generated_path=folder + "/ui_stand_in_form.py",
        window_path=folder + "/stand_in_form_window.py",
        module_name="ui_stand_in_form",
    )
    generated = generate_form_module(document, scope=scope, source_bytes=saved.encode("utf-8"))
    assert generated.text is not None
    assert "from PySide6.QtOpenGLWidgets import QOpenGLWidget" in generated.text
    assert "from PySide6.QtQuickWidgets import QQuickWidget" in generated.text
