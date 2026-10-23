"""The realized page matches a clean Fusion render under every shell theme."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import traceback
from pathlib import Path

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.core import constants  # noqa: E402
from app.features.form_builder.install import form_builder_enabled  # noqa: E402
from app.features.form_builder.qtside.realize import Realizer  # noqa: E402
from app.qt.QtGui import QFont, QImage  # noqa: E402
from app.qt.QtWidgets import QApplication, QStyleFactory, QWidget  # noqa: E402
from app.run.runtime_launch import (  # noqa: E402
    build_runpy_bootstrap_payload,
    sanitize_apprun_child_env,
)
from app.shell.shell_theme_surface_appliers import set_app_tooltip_style_sheet  # noqa: E402
from app.shell.style_sheet import build_app_tooltip_style_sheet  # noqa: E402
from app.shell.theme_tokens import tokens_from_palette  # noqa: E402
from tests.form_builder.qtside.support import open_session  # noqa: E402
from tests.unit.features.form_builder.test_workbench import _open  # noqa: E402

pytestmark = pytest.mark.integration

_APPRUN = Path("/opt/freecad-1.1/AppRun")
_REPO = Path(__file__).resolve().parents[3]
_SCHEMA = _REPO / "tests/form_builder/corpus/synthetic/schema"
_THEMES = (
    ("light", None),
    ("dark", None),
    ("dark", constants.UI_THEME_DARK_CHROME_PALETTE_NEUTRAL_GRAY),
    ("high_contrast_light", None),
    ("high_contrast_dark", None),
)


def _stage_kitchen(tmp_path: Path) -> Path:
    dest = tmp_path / "schema"
    shutil.copytree(_SCHEMA, dest)
    return dest / "kitchen_sink.ui"


def _theme_label(mode: str, palette: str | None) -> str:
    if palette == constants.UI_THEME_DARK_CHROME_PALETTE_NEUTRAL_GRAY:
        return "neutral_gray"
    return mode


def _argb(image: QImage) -> QImage:
    formats = getattr(QImage, "Format", QImage)
    return image.convertToFormat(getattr(formats, "Format_ARGB32"))


def _rows(image: QImage) -> tuple[QImage, list[bytes]]:
    converted = _argb(image)
    stride = converted.bytesPerLine()
    width_bytes = converted.width() * 4
    view = converted.constBits()
    raw = bytes(view[: converted.sizeInBytes()])
    rows = []
    for y in range(converted.height()):
        start = y * stride
        rows.append(raw[start : start + width_bytes])
    return converted, rows


def _keep_mismatch(theme: str, actual: QImage, reference: QImage) -> None:
    folder = Path("/opt/cursor/artifacts")
    if not folder.is_dir():
        return
    actual.save(str(folder / ("canvas-isolation-actual-%s.png" % theme)))
    reference.save(str(folder / "canvas-isolation-reference.png"))


def _assert_same(actual_image: QImage, reference_image: QImage, theme: str) -> None:
    actual, actual_rows = _rows(actual_image)
    reference, reference_rows = _rows(reference_image)
    if actual.width() != reference.width() or actual.height() != reference.height():
        _keep_mismatch(theme, actual, reference)
        raise AssertionError(
            "%s size %dx%d != reference %dx%d"
            % (theme, actual.width(), actual.height(), reference.width(), reference.height())
        )
    for y, (left, right) in enumerate(zip(actual_rows, reference_rows)):
        if left == right:
            continue
        for x in range(actual.width()):
            if actual.pixel(x, y) != reference.pixel(x, y):
                _keep_mismatch(theme, actual, reference)
                raise AssertionError(
                    "%s pixel (%d, %d) is #%08x, reference is #%08x"
                    % (theme, x, y, actual.pixel(x, y), reference.pixel(x, y))
                )
        raise AssertionError("%s row %d differs" % (theme, y))


def _render_runtime_png(ui_path: str, png_path: str) -> None:
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication([])
    style = QStyleFactory.create("Fusion")
    if style is None:
        raise RuntimeError("Qt did not provide the Fusion style")
    app.setStyle(style)
    app.setPalette(style.standardPalette())
    app.setFont(QFont(app.font()))
    text = Path(ui_path).read_text(encoding="utf-8")
    session = open_session(text, ui_path)
    realizer = Realizer(session)
    try:
        root = realizer.build()
        # sizeHint is the layout size. A later show() reports the window
        # geometry instead, so read the hint first. The show still has to
        # happen: setWidget shows the page, and that first show adjusts
        # children that were never resized.
        hint = root.sizeHint()
        root.show()
        app.processEvents()
        width = hint.width() if hint.width() > 0 else max(root.width(), 320)
        height = hint.height() if hint.height() > 0 else max(root.height(), 240)
        root.resize(width, height)
        app.processEvents()
        if not root.grab().save(png_path):
            raise RuntimeError("could not write %s" % png_path)
    finally:
        realizer.dispose()
        session.dispose()


def _render_reference(ui_path: Path, png_path: Path) -> None:
    script = Path(__file__).resolve()
    payload = build_runpy_bootstrap_payload(
        script_path=str(script),
        path_entries=(str(_REPO), str(_REPO / "vendor")),
        argv=[str(script), str(ui_path), str(png_path)],
    )
    env = sanitize_apprun_child_env()
    env["CBCS_QT_API"] = "pyside6"
    env["QT_QPA_PLATFORM"] = "offscreen"
    env.pop("PYTEST_CURRENT_TEST", None)
    completed = subprocess.run(
        [str(_APPRUN), "-c", payload],
        cwd=str(_REPO),
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=25,
    )
    assert completed.returncode == 0, completed.stdout + "\n" + completed.stderr
    assert png_path.is_file()


def test_page_grab_matches_the_clean_runtime_under_every_shell_theme(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    if not _APPRUN.is_file():
        pytest.skip("/opt/freecad-1.1/AppRun is missing")
    if not form_builder_enabled():
        pytest.skip("the form builder needs PySide6")
    ui_path = _stage_kitchen(tmp_path)
    png_path = tmp_path / "runtime.png"
    _render_reference(ui_path, png_path)
    reference = QImage(str(png_path))
    assert reference.isNull() is False
    host = QWidget()
    surface = _open(host, ui_path.read_text(encoding="utf-8"), ui_path)
    host.resize(1280, 800)
    host.show()
    surface.show()
    qapp.processEvents()
    page = surface.page_widget()
    assert page is not None
    saved_sheet = qapp.styleSheet()
    try:
        for mode, palette in _THEMES:
            tokens = tokens_from_palette(
                qapp.palette(),
                force_mode=mode,
                dark_chrome_palette=palette or constants.UI_THEME_DARK_CHROME_PALETTE_DEFAULT,
            )
            set_app_tooltip_style_sheet(build_app_tooltip_style_sheet(tokens))
            surface.apply_theme(tokens)
            qapp.processEvents()
            _assert_same(page.grab().toImage(), reference, _theme_label(mode, palette))
    finally:
        qapp.setStyleSheet(saved_sheet)
        surface.release()
        host.close()


if __name__ == "__main__":
    try:
        _render_runtime_png(sys.argv[1], sys.argv[2])
    except Exception:
        traceback.print_exc()
        os._exit(1)
    os._exit(0)
