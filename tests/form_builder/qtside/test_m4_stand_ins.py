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


@pytest.mark.parametrize("high_contrast", [False, True])
def test_a_stand_in_paints_the_spec_colours(high_contrast: bool) -> None:
    """ov.stand_in_* are #RRGGBBAA; QColor would read eight digits as #AARRGGBB and wash the text out."""
    from app.qt.QtWidgets import QWidget

    holder = QWidget()
    widget = StandInWidget(holder, friendly="OpenGL widget", high_contrast=high_contrast)
    widget.resize(160, 96)
    image = widget.grab().toImage()
    fill = image.pixelColor(20, 20)
    assert (fill.red(), fill.green(), fill.blue()) == ((255, 255, 255) if high_contrast else (0xF4, 0xF4, 0xF4))
    darkest = min(
        (image.pixelColor(x, y) for x in range(4, 156) for y in range(30, 66)),
        key=lambda color: color.red() + color.green() + color.blue(),
    )
    # The 11 px text is #3C3C3C (#000000 in high contrast); antialiasing only lightens it.
    assert max(darkest.red(), darkest.green(), darkest.blue()) <= (0x10 if high_contrast else 0x50)
    holder.deleteLater()


def test_a_stand_in_on_a_high_contrast_canvas_uses_the_high_contrast_tokens(qapp) -> None:  # type: ignore[no-untyped-def]
    from app.features.form_builder.integration.canvas import FormCanvas
    from app.qt.QtWidgets import QWidget
    from app.shell.theme_tokens import tokens_from_palette
    from tests.form_builder.qtside.test_m4_pages_canvas import _Host
    from tests.form_builder.qtside.test_m4_scroll_area import _flush

    with opened(STAND) as (session, realizer):
        parent = QWidget()
        parent.resize(900, 700)
        canvas = FormCanvas(session, realizer, _Host(), parent)
        canvas.resize(900, 700)
        parent.show()
        _flush()
        canvas.apply_theme(tokens_from_palette(qapp.palette(), force_mode="high_contrast_dark"))
        _flush()
        gl = realizer.widget_for(session.document.by_name("glView")[0])
        assert isinstance(gl, StandInWidget)
        image = gl.grab().toImage()
        fill = image.pixelColor(gl.width() // 2, 3)
        assert (fill.red(), fill.green(), fill.blue()) == (255, 255, 255)
        canvas.dispose()
        parent.deleteLater()
        _flush()
