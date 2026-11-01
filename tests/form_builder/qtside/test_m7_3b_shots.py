# pyright: reportAttributeAccessIssue=false
"""Checks screenshots. Skips unless CBCS_FB_SCREENSHOT_DIR is set."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import cast

import pytest

from app.features.form_builder.engine.ipc.protocol import Appearance, TryStart, encode_frame
from app.features.form_builder.integration.chrome import chrome_for
from app.features.form_builder.integration.preview_notice import preview_request
from app.features.form_builder.qtside.preview.child.session import ChildSession
from app.features.form_builder.qtside.preview.child.stdio import FrameWriter
from app.qt.QtCore import Qt
from app.qt.QtTest import QTest
from app.qt.QtWidgets import (
    QApplication,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QSizePolicy,
    QTreeWidget,
    QWidget,
)
from app.shell.theme_tokens import tokens_from_palette
from tests.form_builder.qtside.test_m7_2b1_shots import (
    _MODES,
    _clear_inspector_width,
    _grab,
    _pump,
    _set_inspector_width,
    _theme,
    _with_pytest_path,
)
from tests.form_builder.qtside.test_m7_6_try import _Writer

pytestmark = pytest.mark.unit


def _key(name: str) -> object:
    from app.qt.QtCore import Qt

    return getattr(getattr(Qt, "Key", Qt), name)


def _pick(window: QWidget, qapp: QApplication, key: str) -> None:
    add = window.findChild(QPushButton, "formBuilder.checks.add")
    assert add is not None
    add.click()
    _pump(qapp)
    menu = window.findChild(QMenu, "formBuilder.checks.menu")
    assert menu is not None
    picked = next(action for action in menu.actions() if action.data() == key)
    picked.trigger()
    _pump(qapp)


def _save(section: QWidget, window: QWidget, folder: Path, slug: str, mode: str, scale: str, qapp: QApplication) -> None:
    _pump(qapp)
    _grab(section, folder / ("%s-%s-%s.png" % (slug, mode, scale)))
    _set_inspector_width(window, 236, qapp)
    _pump(qapp)
    _grab(section, folder / ("%s-%s-%s-236.png" % (slug, mode, scale)))
    _clear_inspector_width(window, qapp)


def _shoot(qapp: QApplication, folder: Path, scale: str) -> None:
    from app.features.form_builder.qtside.inspector import TabId
    from tests.form_builder.qtside.test_m3_keyboard_scripts import _close
    from tests.form_builder.qtside.test_m7_3b_k28 import _session

    tmp = Path(tempfile.mkdtemp()).resolve()
    window, kb, guard, path = _session(tmp, qapp)
    child = None
    before_path = list(sys.path)
    before_modules = dict(sys.modules)
    try:
        surface = kb.surface
        edit = surface.session.document.by_name("emailEdit")[0]
        inspector = surface.workbench.inspector
        for mode in _MODES:
            _theme(window, mode, qapp)
            surface.session.selection.set((edit,), source="canvas")
            inspector.focus_tab(TabId.BEHAVIOR)
            inspector.flush()
            _pump(qapp)
            section = window.findChild(QWidget, "formBuilder.checks")
            assert section is not None
            _save(section, window, folder, "checks-empty", mode, scale, qapp)
            add = window.findChild(QPushButton, "formBuilder.checks.add")
            assert add is not None
            add.click()
            _pump(qapp)
            menu = window.findChild(QMenu, "formBuilder.checks.menu")
            assert menu is not None and menu.isVisible()
            # Offscreen does not paint a popup over the section grab. Pin the
            # same menu under the button so the shot shows the kind list.
            menu.close()
            kind = getattr(Qt, "WindowType", Qt)
            menu.setWindowFlag(getattr(kind, "Popup"), False)
            menu.setParent(section)
            layout = section.layout()
            assert layout is not None
            layout.insertWidget(layout.indexOf(add) + 1, menu)
            menu.show()
            _pump(qapp)
            rects = [menu.actionGeometry(action) for action in menu.actions()]
            heights = [rect.height() for rect in rects if rect.height() > 4]
            row = max(heights) if heights else 28
            menu.setFixedHeight(row * len(menu.actions()) + 12)
            layout.activate()
            section.setMinimumHeight(menu.y() + menu.height() + 72)
            _pump(qapp)
            _save(section, window, folder, "checks-add-menu", mode, scale, qapp)
            section.setMinimumHeight(0)
            layout.removeWidget(menu)
            menu.hide()
            picked = next(action for action in menu.actions() if action.data() == "required")
            picked.trigger()
            _pump(qapp)
            _save(section, window, folder, "checks-page", mode, scale, qapp)
            commit = window.findChild(QPushButton, "formBuilder.checks.commit")
            assert commit is not None
            commit.click()
            _pump(qapp)
            _save(section, window, folder, "checks-offer", mode, scale, qapp)
            add_label = window.findChild(QPushButton, "formBuilder.checks.addLabel")
            assert add_label is not None
            add_label.click()
            _pump(qapp)
            _save(section, window, folder, "checks-filled", mode, scale, qapp)
            assert surface.session.log.undo()
            _pump(qapp)
        surface.session.selection.set((edit,), source="canvas")
        inspector.focus_tab(TabId.BEHAVIOR)
        inspector.flush()
        _pump(qapp)
        _pick(window, qapp, "required")
        window.findChild(QPushButton, "formBuilder.checks.commit").click()  # type: ignore[union-attr]
        _pump(qapp)
        window.findChild(QPushButton, "formBuilder.checks.addLabel").click()  # type: ignore[union-attr]
        _pump(qapp)
        outline = window.findChild(QPushButton, "formBuilder.checks.outline")
        assert outline is not None and outline.isVisible()
        outline.click()
        _pump(qapp)
        message = preview_request(
            surface.session,
            str(path),
            "v1",
            run_behavior=True,
            appearance=Appearance(title="Preview"),
        )
        assert isinstance(message, TryStart), message
        writer = _Writer()
        child = ChildSession(cast(FrameWriter, writer), qapp)
        child._handle_line(encode_frame(message))  # noqa: SLF001
        qapp.processEvents()
        shell = child._views["v1"].widget  # noqa: SLF001
        field = shell.findChild(QLineEdit, "emailEdit")
        label = shell.findChild(QLabel, "emailEditError")
        assert isinstance(field, QLineEdit) and isinstance(label, QLabel)
        field.setFocus()
        QTest.keyClick(field, _key("Key_A"))  # type: ignore[arg-type]
        QTest.keyClick(field, _key("Key_Backspace"))  # type: ignore[arg-type]
        qapp.processEvents()
        QTest.keyClick(field, _key("Key_Tab"))  # type: ignore[arg-type]
        qapp.processEvents()
        assert label.text() == "Email is required"
        QTest.qWait(50)
        tree = shell.findChild(QTreeWidget, "preview.whatRan.list")
        assert tree is not None
        lines = [tree.topLevelItem(index).text(1) for index in range(tree.topLevelItemCount())]
        sources = [tree.topLevelItem(index).text(2) for index in range(tree.topLevelItemCount())]
        assert any("Email is required" in line for line in lines), lines
        assert any(source == "Email · Checks" for source in sources), sources
        logged = " ".join(getattr(item, "text", "") for item in writer.sent)
        assert "Email is required" in logged
        for index in range(tree.topLevelItemCount()):
            tree.topLevelItem(index).setExpanded(True)
        host = shell.findChild(QWidget, "preview.form")
        assert host is not None and host.layout() is not None
        inner = host.layout().itemAt(0).widget()
        assert inner is not None
        hint = inner.sizeHint()
        names = getattr(QSizePolicy, "Policy", QSizePolicy)
        inner.setSizePolicy(getattr(names, "Preferred"), getattr(names, "Fixed"))
        inner.setFixedHeight(max(hint.height(), 1))
        column = max(hint.width() + 24, 280)
        shell._splitter.setSizes([column, 480])  # noqa: SLF001
        shell.resize(column + 480, max(hint.height() + 64, 360))
        shell.show()
        qapp.processEvents()
        for mode in _MODES:
            tokens = tokens_from_palette(qapp.palette(), force_mode=mode)
            shell.apply_chrome(chrome_for(tokens))
            qapp.processEvents()
            _grab(shell, folder / ("checks-preview-%s-%s.png" % (mode, scale)))
    finally:
        if child is not None:
            for view_id in list(child._views):  # noqa: SLF001
                widget = child._views.pop(view_id).widget  # noqa: SLF001
                widget.hide()
                widget.deleteLater()
            qapp.processEvents()
            qapp.removeEventFilter(child._user_close)  # noqa: SLF001
            sys.path[:] = before_path
            for name in list(sys.modules):
                if name not in before_modules:
                    sys.modules.pop(name, None)
            for name, module in before_modules.items():
                sys.modules[name] = module
        _close(window, qapp, guard)


@pytest.mark.timeout(300)
def test_m7_3b_shots(qapp: QApplication) -> None:
    raw = os.environ.get("CBCS_FB_SCREENSHOT_DIR") or ""
    if not raw:
        pytest.skip("CBCS_FB_SCREENSHOT_DIR is not set")
    folder = Path(raw)
    folder.mkdir(parents=True, exist_ok=True)
    if os.environ.get("CBCS_FB_SHOT_CHILD") == "1":
        _shoot(qapp, folder, "200")
        return
    _shoot(qapp, folder, "100")
    env = os.environ.copy()
    env["QT_SCALE_FACTOR"] = "2"
    env["CBCS_FB_SHOT_CHILD"] = "1"
    env["CBCS_FB_SCREENSHOT_DIR"] = str(folder)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    env["PYTHONNOUSERSITE"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    env["CBCS_DISABLE_BACKGROUND_RUNTIME"] = "1"
    _with_pytest_path(env)
    done = subprocess.run(
        [
            sys.executable,
            "-s",
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            "--import-mode=importlib",
            "--timeout",
            "300",
            "-q",
            str(Path(__file__).resolve()),
            "-k",
            "test_m7_3b_shots",
        ],
        cwd=str(Path(__file__).resolve().parents[3]),
        env=env,
        capture_output=True,
        text=True,
    )
    text = done.stdout + "\n" + done.stderr
    passed = "passed" in text and "failed" not in text
    assert done.returncode == 0 or (done.returncode in (-11, 139) and passed), text
