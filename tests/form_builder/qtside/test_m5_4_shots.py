# pyright: reportAttributeAccessIssue=false
"""M5.4 screenshots (UX_SPEC 12.2 M5 states). Skips unless CBCS_FB_SCREENSHOT_DIR is set.

own-class-popover, own-class-check-lines, own-class-canvas, own-class-preview-notice,
own-class-stand-in-toast and the inspector header at 236 px, in light, dark and both
high-contrast themes. 100% is this process; 200% is a child with QT_SCALE_FACTOR=2.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.features.form_builder.engine.commands.catalog_ext.promote import UseOwnClass
from app.features.form_builder.engine.project import custom_widgets as cw
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.integration import preview_notice
from app.features.form_builder.integration.canvas import FormCanvas
from app.features.form_builder.integration.chrome import chrome_for
from app.features.form_builder.integration.custom_registry import registry_for
from app.features.form_builder.qtside.dialogs.promote import open_popover
from app.features.form_builder.qtside.inspector.api import GROUP_ORDER, GroupId
from app.features.form_builder.qtside.realize import Realizer
from app.qt.QtWidgets import QApplication, QWidget
from app.shell.theme_tokens import tokens_from_palette
from tests.form_builder.qtside.test_m4_pages_canvas import _Host
from tests.form_builder.qtside.test_m4_r3_shots import _fit, _flush, _inspector
from tests.form_builder.qtside.test_m5_4_own_class import _FORM

pytestmark = [pytest.mark.usefixtures("qapp"), pytest.mark.unit]

_MODES = ("light", "dark", "high_contrast_light", "high_contrast_dark")

_CANVAS_FORM = _FORM.replace(
    '<property name="text"><string>Total</string></property>',
    '<property name="text"><string>Total: 12.50</string></property>',
)


def test_m5_4_screenshots(qapp: QApplication, tmp_path: Path) -> None:
    raw = os.environ.get("CBCS_FB_SCREENSHOT_DIR") or ""
    if not raw:
        pytest.skip("CBCS_FB_SCREENSHOT_DIR is not set")
    folder = Path(raw)
    folder.mkdir(parents=True, exist_ok=True)
    if os.environ.get("CBCS_FB_SHOT_CHILD") == "1":
        _shoot(qapp, folder, tmp_path, 200)
        return
    _shoot(qapp, folder, tmp_path, 100)
    env = os.environ.copy()
    env["QT_SCALE_FACTOR"] = "2"
    env["CBCS_FB_SHOT_CHILD"] = "1"
    env["CBCS_FB_SCREENSHOT_DIR"] = str(folder)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    env.setdefault("PYTHONNOUSERSITE", "1")
    env.setdefault("CBCS_DISABLE_BACKGROUND_RUNTIME", "1")
    completed = subprocess.run(
        [sys.executable, "-s", "-m", "pytest", "-p", "no:cacheprovider", "--import-mode=importlib", "--timeout", "0",
         "-q", str(Path(__file__).resolve()), "-k", "test_m5_4_screenshots"],
        cwd=str(Path(__file__).resolve().parents[3]),
        env=env,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + "\n" + completed.stderr


def _shop(tmp_path: Path):  # noqa: ANN202
    root = tmp_path / "shop"
    (root / "cbcs").mkdir(parents=True, exist_ok=True)
    (root / "cbcs" / "project.json").write_text('{"schema_version": 2, "name": "Shop"}\n', encoding="utf-8")
    (root / "forms").mkdir(exist_ok=True)
    (root / "widgets").mkdir(exist_ok=True)
    (root / "widgets" / "till_display.py").write_text("class TillDisplay(QLabel):\n    pass\n", encoding="utf-8")
    (root / "widgets" / "card.py").write_text("class Card(QWidget):\n    pass\n", encoding="utf-8")
    (root / "widgets" / "frame.py").write_text("class FrameBased(QFrame):\n    pass\n", encoding="utf-8")
    path = str(root / "forms" / "till.ui")
    scope = FormScope(
        kind="project", ui_path=path, project_root=str(root.resolve()), generated_path=str(root / "forms" / "ui_till.py"),
        window_path=str(root / "forms" / "till_window.py"), module_name="forms.ui_till",
    )
    session = FormSession.open(_CANVAS_FORM, path=path, scope=scope)
    realizer = Realizer(session)
    realizer.build()
    return root, session, realizer


def _shoot(qapp: QApplication, folder: Path, tmp_path: Path, scale: int) -> None:
    for mode in _MODES:
        tokens = tokens_from_palette(qapp.palette(), force_mode=mode)
        chrome = chrome_for(tokens)
        root, session, realizer = _shop(tmp_path)
        try:
            registry = registry_for(str(root.resolve()))
            registry.upsert(cw.RegistryEntry("TillDisplay", "widgets.till_display", "QLabel", description="Running total"))
            registry.upsert(cw.RegistryEntry("Ticker", "widgets.ticker", "QLabel"))
            label = session.document.by_name("totalLabel")[0]
            host = QWidget()
            host.resize(420, 60)
            host.show()
            pop = open_popover(session, (label,), registry, host, chrome=chrome)
            pop.set_fields("", "")
            _flush()
            pop.grab().save(str(folder / ("own-class-popover-%s-%d.png" % (mode, scale))))
            for stem, fields, expected in (
                ("found", ("TillDisplay", "widgets.till_display"), "Found"),
                ("other-base", ("FrameBased", "widgets.frame"), "is based on"),
                ("no-class", ("Missing", "widgets.till_display"), "has no class"),
                ("no-file", ("Thing", "widgets.nowhere"), "no widgets/nowhere.py"),
                ("bad-module", ("Thing", "widgets..x"), "Use a module path"),
                ("bad-class", ("2Thing", "widgets.thing"), "Use a class name"),
            ):
                pop.set_fields(*fields)
                assert expected in pop.check_text, pop.check_text
                _flush()
                pop.grab().save(str(folder / ("own-class-check-%s-%s-%d.png" % (stem, mode, scale))))
            pop.cancel()
            _flush()
            host.deleteLater()
            # The canvas: a label with the tag, and a QWidget-based stand-in.
            session.log.execute(UseOwnClass((label,), "TillDisplay", "widgets.till_display", "QLabel", names=("totalLabel",)))
            card = session.document.by_name("card")[0]
            session.log.execute(UseOwnClass((card,), "Card", "widgets.card", "QWidget", container=True, names=("card",)))
            from app.features.form_builder.qtside.canvas.layers import own_class

            parent = QWidget()
            parent.resize(760, 520)
            canvas = FormCanvas(session, realizer, _Host(), parent)
            canvas.resize(760, 520)
            parent.show()
            canvas.setFocus()
            canvas.apply_theme(tokens)
            canvas.show_layer(own_class.NAME, True)
            for stem, node in (("label", label), ("stand-in", card)):
                session.selection.set((node,), source=SelectionSource.PROGRAM)
                _flush()
                canvas.grab().save(str(folder / ("own-class-canvas-%s-%s-%d.png" % (stem, mode, scale))))
            canvas.dispose()
            parent.deleteLater()
            _flush()
            # The inspector header at 236 px.
            window, pane = _inspector(session, realizer)
            try:
                pane.apply_chrome(chrome)
                for group in GROUP_ORDER:
                    pane.set_group_expanded(group, group in (GroupId.CONTENT,))
                session.selection.set((label,), source=SelectionSource.PROGRAM)
                pane.flush()
                _fit(qapp, window, pane, 236)
                pane.grab().save(str(folder / ("own-class-inspector-%s-%d.png" % (mode, scale))))
            finally:
                pane.dispose()
                window.close()
                window.deleteLater()
                _flush()
        finally:
            realizer.dispose()
            session.dispose()
    _main_window_shots(qapp, folder, tmp_path, scale)


def _main_window_shots(qapp: QApplication, folder: Path, tmp_path: Path, scale: int) -> None:
    """The info bar and the stand-in toast on a real form tab, with the FB602 row in Problems."""
    from app.features.form_builder.engine.ipc.protocol import ErrorReport
    from tests.form_builder.qtside.test_m3_keyboard_scripts import _close, _NoMouse, _session
    from tests.form_builder.qtside.test_m5_4_k19 import _project_files

    for mode in _MODES:
        base = tmp_path / ("window-" + mode)
        _project_files(base)
        window, kb, guard = _session(base, qapp, _FORM)
        try:
            tokens = tokens_from_palette(qapp.palette(), force_mode=mode)
            surface = kb.surface
            surface.apply_theme(tokens)
            session = surface.session
            label = session.document.by_name("totalLabel")[0]
            note = session.document.by_name("noteLabel")[0]
            session.log.execute(UseOwnClass((label,), "TillDisplay", "widgets.till_display", "QLabel", names=("totalLabel",)))
            session.log.execute(UseOwnClass((note,), "Broken", "widgets.broken", "QLabel", names=("noteLabel",)))
            notices = preview_notice.PreviewNotices(surface, session, pool=None)
            preview_notice.forget_noted()
            root = str((base / "shop").resolve())
            notices._security_note(root, preview_notice.used_classes(session.document))
            _flush()
            surface.grab().save(str(folder / ("own-class-preview-notice-%s-%d.png" % (mode, scale))))
            surface._notice.dismiss()
            failure = preview_notice.parse_failure(
                ErrorReport(
                    "v", "FB602", "Custom widget Broken could not load. The base class was used.",
                    'RuntimeError: the till is closed\n  File "%s/widgets/broken.py", line 7, in __init__' % root,
                ),
                root,
                lambda name: "",
            )
            session.diagnostics.publish("preview", preview_notice.stand_in_diagnostics(session, (failure,)))
            notices._toast(failure)
            surface._flush_problems()
            _flush()
            window.grab().save(str(folder / ("own-class-stand-in-toast-%s-%d.png" % (mode, scale))))
        finally:
            _close(window, qapp, guard)
