# pyright: reportAttributeAccessIssue=false
"""Project Find with a Forms logic group, and the Read as text tab. Skips unless CBCS_FB_SCREENSHOT_DIR is set."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.features.form_builder.integration.find_ext.forms_logic import FormsLogic
from app.qt.QtWidgets import QApplication, QVBoxLayout, QWidget
from app.shell.search_sidebar_widget import SearchSidebarWidget
from app.shell.style_sheet_sections_workspace import shell_section_workspace_tree_editors
from app.shell.theme_tokens import tokens_from_palette
from tests.form_builder.qtside.test_m7_2b1_shots import _MODES, _grab, _pump, _with_pytest_path

pytestmark = pytest.mark.unit


def _find_host(root: Path) -> QWidget:
    host = QWidget()
    host._form_builder_forms_logic = FormsLogic()  # type: ignore[attr-defined]
    host._loaded_project = SimpleNamespace(project_root=str(root))  # type: ignore[attr-defined]
    sidebar = SearchSidebarWidget(host)
    sidebar.set_project_root(str(root))
    layout = QVBoxLayout(host)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(sidebar)
    host._sidebar = sidebar  # type: ignore[attr-defined]
    return host


def _paint_find(sidebar: SearchSidebarWidget, query: str) -> None:
    sidebar._search_input.setText(query)
    sidebar._search_generation = 1
    sidebar._pending_results = []
    sidebar._pending_query = query
    sidebar._pending_generation = 1
    sidebar._apply_search_results()
    sidebar._results_tree.expandAll()


def _behavior_form() -> str:
    from app.features.form_builder.engine.logic.events_codec import EventStep, call_step, write_list
    from tests.form_builder.engine.logic.test_m7_8a_uses import _prop

    steps = write_list((EventStep("validate"), call_step("save_invoice")))
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<ui version="4.0"><class>Invoice</class>'
        '<widget class="QDialog" name="Invoice">'
        '<property name="windowTitle"><string>Invoice</string></property>'
        '<widget class="QDoubleSpinBox" name="discountEdit">%s</widget>'
        '<widget class="QSpinBox" name="qtySpin"/>'
        '<widget class="QLabel" name="discountRateLabel">'
        '<property name="text"><string>Discount rate</string></property>'
        '<property name="buddy"><cstring>discountEdit</cstring></property>'
        "</widget>"
        '<widget class="QLabel" name="qtyLabel">'
        '<property name="text"><string>Qty</string></property>'
        '<property name="buddy"><cstring>qtySpin</cstring></property>'
        "</widget>"
        '<widget class="QPushButton" name="saveButton">'
        '<property name="text"><string>Save</string></property>'
        "%s</widget></widget></ui>"
    ) % (_prop("cbcsReadOnlyWhen", "qtySpin > 10"), _prop("cbcsOnClicked", steps))


def _shoot(qapp: QApplication, folder: Path, scale: str) -> None:
    from app.features.form_builder.qtside.logic_panel.read_as_text import show_behavior_text
    from app.shell.main_window import MainWindow
    from tests.form_builder.engine.logic.test_m7_8a_uses import window_source
    from tests.form_builder.engine.logic.test_m7_8b_find import _form, _prop
    from tests.form_builder.qtside.test_m3_keyboard_scripts import _NoMouse, _close, _open, _project, _require

    root = Path(tempfile.mkdtemp()).resolve()
    (root / "alpha.ui").write_text(
        _form("Alpha", '<widget class="QLineEdit" name="rateEdit">%s</widget>' % _prop("cbcsValue", "seasonRate")),
        encoding="utf-8",
    )
    host = _find_host(root)
    host.resize(420, 360)
    host.show()
    _paint_find(host._sidebar, "seasonRate")  # type: ignore[attr-defined]
    _pump(qapp)
    _require()
    tmp = Path(tempfile.mkdtemp()).resolve()
    window = MainWindow(state_root=str((tmp / "state").resolve()))
    shop = tmp / "shop"
    _project(window, shop)
    path = shop / "forms" / "invoice.ui"
    (path.parent / "invoice_window.py").write_text(window_source(), encoding="utf-8")
    surface = _open(window, qapp, path, _behavior_form())
    guard = _NoMouse()
    qapp.installEventFilter(guard)
    try:
        show_behavior_text(surface)
        page = surface._behavior_text_page  # type: ignore[attr-defined]
        for mode in _MODES:
            tokens = tokens_from_palette(qapp.palette(), force_mode=mode)
            host._sidebar.apply_theme_tokens(  # type: ignore[attr-defined]
                match_bg=tokens.search_match_bg,
                text_primary=tokens.text_primary,
                text_muted=tokens.text_muted,
                badge_bg=tokens.badge_bg,
                background=tokens.editor_bg,
            )
            host.setStyleSheet(
                "QWidget { background: %s; color: %s; }\n%s"
                % (tokens.panel_bg, tokens.text_primary, shell_section_workspace_tree_editors(tokens))
            )
            _pump(qapp)
            _grab(host, folder / ("find-forms-%s-%s.png" % (mode, scale)))
            surface.apply_theme(tokens)
            for width, stem in ((1000, "read-as-text"), (500, "read-as-text-500")):
                page.setMinimumWidth(0)
                page.setMaximumWidth(16777215)
                page.resize(width, 720)
                page._fit_column()  # type: ignore[attr-defined]
                _pump(qapp)
                _grab(page, folder / ("%s-%s-%s.png" % (stem, mode, scale)))
    finally:
        host.close()
        _close(window, qapp, guard)


@pytest.mark.timeout(300)
def test_m7_8b_shots(qapp: QApplication) -> None:
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
            "-q",
            str(Path(__file__).resolve()),
            "-k",
            "test_m7_8b_shots",
        ],
        cwd=str(Path(__file__).resolve().parents[3]),
        env=env,
        capture_output=True,
        text=True,
    )
    text = done.stdout + "\n" + done.stderr
    tail = "\n".join(text.splitlines()[-12:])
    passed = "passed" in text and "failed" not in text
    assert done.returncode == 0 or (done.returncode in (-11, 139) and passed), tail
