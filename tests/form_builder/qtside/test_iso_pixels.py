# pyright: reportAttributeAccessIssue=false
"""The canvas page matches a clean QApplication under every shell theme (UX-ISO-001/002)."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.core import constants  # noqa: E402
from app.features.form_builder.install import form_builder_enabled  # noqa: E402
from app.features.form_builder.qtside.canvas.core.gesture import ZoomAsked  # noqa: E402
from app.features.form_builder.qtside.canvas.core.space import ZoomTo  # noqa: E402
from app.qt.QtGui import QColor, QImage, QPalette  # noqa: E402
from app.qt.QtWidgets import QApplication, QWidget  # noqa: E402
from app.shell.main_window import MainWindow  # noqa: E402
from testing.main_window_shutdown import shutdown_main_window_for_test  # noqa: E402
from tests.form_builder.qtside.support import run_module  # noqa: E402

pytestmark = pytest.mark.unit

_THEMES = (
    ("light", None),
    ("dark", constants.UI_THEME_DARK_CHROME_PALETTE_DEFAULT),
    ("dark-neutral", constants.UI_THEME_DARK_CHROME_PALETTE_NEUTRAL_GRAY),
    ("hc-light", None),
    ("hc-dark", None),
)
_MODES = {
    "light": "light",
    "dark": "dark",
    "dark-neutral": "dark",
    "hc-light": constants.UI_THEME_MODE_HIGH_CONTRAST_LIGHT,
    "hc-dark": constants.UI_THEME_MODE_HIGH_CONTRAST_DARK,
}

_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <property name="geometry"><rect><x>0</x><y>0</y><width>480</width><height>1400</height></rect></property>
  <layout class="QVBoxLayout" name="verticalLayout">
   <item><widget class="QLabel" name="label"><property name="text"><string>Label</string></property></widget></item>
   <item><widget class="QPushButton" name="pushButton"><property name="text"><string>Button</string></property></widget></item>
   <item><widget class="QLineEdit" name="lineEdit"/></item>
   <item><widget class="QCheckBox" name="checkBox"><property name="text"><string>Check box</string></property></widget></item>
   <item><widget class="QComboBox" name="comboBox"><item><property name="text"><string>One</string></property></item></widget></item>
   <item><widget class="QSpinBox" name="spinBox"/></item>
   <item><widget class="QDoubleSpinBox" name="doubleSpin"/></item>
   <item><widget class="QRadioButton" name="radioButton"><property name="text"><string>Radio</string></property></widget></item>
   <item><widget class="QToolButton" name="toolButton"><property name="text"><string>Tool</string></property></widget></item>
   <item><widget class="QCommandLinkButton" name="commandLink"><property name="text"><string>Command</string></property></widget></item>
   <item><widget class="QSlider" name="slider"><property name="orientation"><enum>Qt::Horizontal</enum></property></widget></item>
   <item><widget class="QTabWidget" name="tabWidget"><widget class="QWidget" name="tabPage"><attribute name="title"><string>Page</string></attribute></widget></widget></item>
   <item><widget class="QTableWidget" name="tableWidget"><property name="rowCount"><number>1</number></property><property name="columnCount"><number>1</number></property></widget></item>
   <item><widget class="QDateEdit" name="dateEdit"/></item>
   <item><widget class="QTextEdit" name="textEdit"><property name="html"><string>Text</string></property></widget></item>
   <item><widget class="QProgressBar" name="progressBar"><property name="value"><number>40</number></property></widget></item>
   <item><widget class="QListWidget" name="listWidget"><item><property name="text"><string>Row</string></property></item></widget></item>
   <item><widget class="QTreeWidget" name="treeWidget"><column><property name="text"><string>Name</string></property></column><item><property name="text"><string>Node</string></property></item></widget></item>
   <item><widget class="QGroupBox" name="groupBox"><property name="title"><string>Group box</string></property></widget></item>
   <item>
    <widget class="QWidget" name="horizontalLayoutWidget">
     <layout class="QHBoxLayout" name="horizontalLayout">
      <item><widget class="QPushButton" name="side"><property name="text"><string>Side</string></property></widget></item>
     </layout>
    </widget>
   </item>
   <item>
    <widget class="QWidget" name="gridLayoutWidget">
     <layout class="QGridLayout" name="gridLayout">
      <item row="0" column="0"><widget class="QLabel" name="cell"><property name="text"><string>Cell</string></property></widget></item>
     </layout>
    </widget>
   </item>
   <item>
    <widget class="QWidget" name="formLayoutWidget">
     <layout class="QFormLayout" name="formLayout">
      <item row="0" column="0"><widget class="QLabel" name="fieldLabel"><property name="text"><string>Field</string></property></widget></item>
      <item row="0" column="1"><widget class="QLineEdit" name="fieldEdit"/></item>
     </layout>
    </widget>
   </item>
   <item>
    <spacer name="horizontalSpacer">
     <property name="orientation"><enum>Qt::Horizontal</enum></property>
     <property name="sizeHint"><size><width>40</width><height>20</height></size></property>
    </spacer>
   </item>
   <item>
    <spacer name="verticalSpacer">
     <property name="orientation"><enum>Qt::Vertical</enum></property>
     <property name="sizeHint"><size><width>20</width><height>40</height></size></property>
    </spacer>
   </item>
   <item><widget class="QCalendarWidget" name="calendarWidget"/></item>
   <item><widget class="QColumnView" name="columnView"/></item>
   <item><widget class="QDateTimeEdit" name="dateTimeEdit"/></item>
   <item><widget class="QDial" name="dial"/></item>
   <item><widget class="QDialogButtonBox" name="buttonBox"/></item>
   <item><widget class="QDockWidget" name="dockWidget"/></item>
   <item><widget class="QFontComboBox" name="fontComboBox"/></item>
   <item><widget class="QFrame" name="frame"/></item>
   <item><widget class="QGraphicsView" name="graphicsView"/></item>
   <item><widget class="QKeySequenceEdit" name="keySequenceEdit"/></item>
   <item><widget class="QLCDNumber" name="lcdNumber"/></item>
   <item><widget class="QListView" name="listView"/></item>
   <item><widget class="QMdiArea" name="mdiArea"/></item>
   <item><widget class="QOpenGLWidget" name="openGLWidget"/></item>
   <item><widget class="QPlainTextEdit" name="plainTextEdit"/></item>
   <item><widget class="QQuickWidget" name="quickWidget"/></item>
   <item><widget class="QScrollArea" name="scrollArea"/></item>
   <item><widget class="QStackedWidget" name="stackedWidget"/></item>
   <item><widget class="QTableView" name="tableView"/></item>
   <item><widget class="QTextBrowser" name="textBrowser"/></item>
   <item><widget class="QTimeEdit" name="timeEdit"/></item>
   <item><widget class="QToolBox" name="toolBox"/></item>
   <item><widget class="QTreeView" name="treeView"/></item>
   <item><widget class="QUndoView" name="undoView"/></item>
   <item><widget class="QWizard" name="wizard"/></item>
   <item><widget class="QWizardPage" name="wizardPage"/></item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


def _shots() -> Path:
    path = Path(os.environ.get("CBCS_FB_SCREENSHOT_DIR", "/opt/cursor/artifacts"))
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        path = Path(tempfile.gettempdir()) / "cbcs-fb-iso"
        path.mkdir(parents=True, exist_ok=True)
    return path


def test_the_reference_form_holds_every_insert_tile() -> None:
    """The ISO form keeps pace with the Insert catalog as it grows."""
    from app.features.form_builder.qtside.canvas.core.palette import TILES

    classes = {tile[0] for tile in TILES if tile[0].startswith("Q")}
    missing = sorted(name for name in classes if 'class="%s"' % name not in _FORM)
    assert missing == []


def _require() -> None:
    if not form_builder_enabled():
        pytest.skip("form builder is registered on PySide6")


@pytest.mark.timeout(60)
@pytest.mark.parametrize("label", [item[0] for item in _THEMES])
def test_the_page_matches_a_clean_application(tmp_path: Path, qapp: QApplication, label: str) -> None:
    """UX-ISO-001/002. Shell chrome does not change a pixel of the realized page."""
    _require()
    palette = dict(_THEMES)[label]
    mode = _MODES[label]
    ui_path = tmp_path / "reference.ui"
    ui_path.write_text(_FORM, encoding="utf-8")
    shots = _shots()
    bare_page = shots / "iso-reference-page.png"
    bare_window = shots / "iso-reference-window.png"
    bare = run_module(
        "tests.form_builder.qtside.tools.bare_palette",
        [str(ui_path), str(bare_page), str(bare_window)],
    )
    assert bare.returncode == 0, bare.stderr[-1500:]
    saved_sheet = qapp.styleSheet()
    saved_palette = QPalette(qapp.palette())
    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    try:
        window._theme_mode = mode  # noqa: SLF001
        if palette is not None:
            window._dark_chrome_palette = palette  # noqa: SLF001
        window._shell_theme_workflow.apply_theme_styles()  # noqa: SLF001
        assert window._editor_tab_factory.open_file_in_editor(str(ui_path))  # noqa: SLF001
        stack = window._center_stack  # noqa: SLF001
        assert stack is not None
        stack.setCurrentIndex(1)
        window.resize(1400, 900)
        window.show()
        qapp.processEvents()
        canvas = window.findChild(QWidget, "formBuilder.canvas")
        assert canvas is not None
        canvas.send(ZoomAsked(ZoomTo(1.0)))
        qapp.processEvents()
        page = canvas.page_widget()
        assert page is not None
        themed_page = shots / ("iso-page-%s.png" % label)
        page.grab().save(str(themed_page))
        window.grab().save(str(shots / ("iso-window-%s.png" % label)))
        diff_path = shots / ("iso-diff-%s.png" % label)
        mismatch = _diff(themed_page, bare_page, diff_path)
        assert mismatch == "", mismatch
    finally:
        shutdown_main_window_for_test(window, qapp)
        qapp.setStyleSheet(saved_sheet)
        qapp.setPalette(saved_palette)


def _diff(themed: Path, bare: Path, diff_path: Path) -> str:
    left = QImage(str(themed)).convertToFormat(QImage.Format_ARGB32)
    right = QImage(str(bare)).convertToFormat(QImage.Format_ARGB32)
    if left.isNull() or right.isNull():
        return "a grab failed to load"
    if left.size() != right.size():
        return "page size %sx%s vs clean %sx%s" % (left.width(), left.height(), right.width(), right.height())
    if bytes(left.constBits()) == bytes(right.constBits()):
        if diff_path.exists():
            diff_path.unlink()
        return ""
    changed = 0
    diff = QImage(left.size(), QImage.Format_ARGB32)
    diff.fill(QColor(0, 0, 0))
    for y in range(left.height()):
        for x in range(left.width()):
            if left.pixel(x, y) != right.pixel(x, y):
                changed += 1
                diff.setPixel(x, y, QColor(255, 0, 0).rgba())
    diff.save(str(diff_path))
    return "%s pixels differ. Diff saved at %s" % (changed, diff_path)
