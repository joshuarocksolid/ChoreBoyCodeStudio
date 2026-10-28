# pyright: reportAttributeAccessIssue=false
"""M4.1 catalog contract: every entry inserts into a form that saves, loads and matches uic.

For each catalog entry: insert its fragment with the real command log, save,
check that QUiLoader loads it and that our generated module and ``uic -g python``
build the same widget tree (the oracle), then check that a second save is
byte-identical. The FreeCAD entries also check that the declaration lands once.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import cast
from typing import Optional

import pytest

from app.features.form_builder.engine.commands.drop_plan import auto_commands
from app.features.form_builder.engine.project.templates import build_template_ui
from app.features.form_builder.engine.query.drop_target import DropPayload, PayloadKind
from app.features.form_builder.engine.ui4.nodes import CustomWidgetNode
from app.features.form_builder.qtside.canvas.core.palette import fragment_for
from app.features.form_builder.qtside.insert.catalog import load_catalog
from app.features.form_builder.qtside.start.wizard import wizard_document
from tests.form_builder.qtside.support import open_session

pytestmark = pytest.mark.usefixtures("qapp")

_UIC_CANDIDATES = (
    Path("/Applications/FreeCAD.app/Contents/Resources/lib/qt6/uic"),
    Path("/opt/freecad-1.1/usr/lib/qt6/uic"),
    Path("/usr/local/bin/cbcs-fb-uic"),
)

_FREECAD = tuple(entry.key for entry in load_catalog().entries if entry.freecad)


def _uic() -> Optional[Path]:
    override = os.environ.get("CBCS_FB_UIC")
    candidates = ([Path(override)] if override else []) + list(_UIC_CANDIDATES)
    for path in candidates:
        if path.is_file() and os.access(str(path), os.X_OK):
            return path
    return None


def _require_oracle() -> None:
    uic = _uic()
    if uic is None:
        pytest.skip("uic is not available; set CBCS_FB_UIC")
    os.environ.setdefault("CBCS_FB_UIC", str(uic))


def _host_text(key: str) -> str:
    if key == "QWizardPage":
        return wizard_document("Form")
    return build_template_ui("widget", "Form")


def _insert(session, key: str) -> None:  # type: ignore[no-untyped-def]
    entry = load_catalog().get(key)
    assert entry is not None, key
    fragment = fragment_for(key)
    assert fragment is not None, key
    payload_kind = cast(PayloadKind, entry.payload)
    commands = auto_commands(session.document, session.selection.state.current, DropPayload(payload_kind), fragment)
    assert commands, "%s was refused on a host it should fit" % key
    with session.log.transaction("Insert %s" % entry.friendly.lower()) as txn:
        for command in commands:
            txn.execute(command)



@pytest.mark.oracle
@pytest.mark.parametrize(
    "key",
    [
        pytest.param("layout-v", marks=pytest.mark.parity("R3-57"), id="layout-v"),
        pytest.param("layout-h", marks=pytest.mark.parity("R3-58"), id="layout-h"),
        pytest.param("layout-grid", marks=pytest.mark.parity("R3-59"), id="layout-grid"),
        pytest.param("layout-form", marks=pytest.mark.parity("R3-60"), id="layout-form"),
        pytest.param("splitter-h", marks=pytest.mark.parity("R3-120"), id="splitter-h"),
        pytest.param("splitter-v", marks=pytest.mark.parity("R3-120"), id="splitter-v"),
        pytest.param("spacer-h", marks=pytest.mark.parity("R3-61"), id="spacer-h"),
        pytest.param("spacer-v", marks=pytest.mark.parity("R3-62"), id="spacer-v"),
        pytest.param("QLineEdit", marks=pytest.mark.parity("R3-88"), id="QLineEdit"),
        pytest.param("QTextEdit", marks=pytest.mark.parity("R3-89"), id="QTextEdit"),
        pytest.param("QPlainTextEdit", marks=pytest.mark.parity("R3-90"), id="QPlainTextEdit"),
        pytest.param("QSpinBox", marks=pytest.mark.parity("R3-91"), id="QSpinBox"),
        pytest.param("QDoubleSpinBox", marks=pytest.mark.parity("R3-92"), id="QDoubleSpinBox"),
        pytest.param("slider-h", marks=pytest.mark.parity("R3-99"), id="slider-h"),
        pytest.param("slider-v", marks=pytest.mark.parity("R3-100"), id="slider-v"),
        pytest.param("QDial", marks=pytest.mark.parity("R3-96"), id="QDial"),
        pytest.param("scrollbar-h", marks=pytest.mark.parity("R3-97"), id="scrollbar-h"),
        pytest.param("scrollbar-v", marks=pytest.mark.parity("R3-98"), id="scrollbar-v"),
        pytest.param("QKeySequenceEdit", marks=pytest.mark.parity("R3-101"), id="QKeySequenceEdit"),
        pytest.param("QComboBox", marks=pytest.mark.parity("R3-86"), id="QComboBox"),
        pytest.param("QFontComboBox", marks=pytest.mark.parity("R3-87"), id="QFontComboBox"),
        pytest.param("QCheckBox", marks=pytest.mark.parity("R3-66"), id="QCheckBox"),
        pytest.param("QRadioButton", marks=pytest.mark.parity("R3-65"), id="QRadioButton"),
        pytest.param("QPushButton", marks=pytest.mark.parity("R3-63"), id="QPushButton"),
        pytest.param("QToolButton", marks=pytest.mark.parity("R3-64"), id="QToolButton"),
        pytest.param("QCommandLinkButton", marks=pytest.mark.parity("R3-67"), id="QCommandLinkButton"),
        pytest.param("QDialogButtonBox", marks=pytest.mark.parity("R3-68"), id="QDialogButtonBox"),
        pytest.param("QDateEdit", marks=pytest.mark.parity("R3-94"), id="QDateEdit"),
        pytest.param("QTimeEdit", marks=pytest.mark.parity("R3-93"), id="QTimeEdit"),
        pytest.param("QDateTimeEdit", marks=pytest.mark.parity("R3-95"), id="QDateTimeEdit"),
        pytest.param("QCalendarWidget", marks=pytest.mark.parity("R3-105"), id="QCalendarWidget"),
        pytest.param("QListWidget", marks=pytest.mark.parity("R3-74"), id="QListWidget"),
        pytest.param("QTreeWidget", marks=pytest.mark.parity("R3-75"), id="QTreeWidget"),
        pytest.param("QTableWidget", marks=pytest.mark.parity("R3-76"), id="QTableWidget"),
        pytest.param("QListView", marks=pytest.mark.parity("R3-69"), id="QListView"),
        pytest.param("QTreeView", marks=pytest.mark.parity("R3-70"), id="QTreeView"),
        pytest.param("QTableView", marks=pytest.mark.parity("R3-71"), id="QTableView"),
        pytest.param("QColumnView", marks=pytest.mark.parity("R3-72"), id="QColumnView"),
        pytest.param("QUndoView", marks=pytest.mark.parity("R3-73"), id="QUndoView"),
        pytest.param("QGroupBox", marks=pytest.mark.parity("R3-77"), id="QGroupBox"),
        pytest.param("QFrame", marks=pytest.mark.parity("R3-82"), id="QFrame"),
        pytest.param("QWidget", marks=pytest.mark.parity("R3-83"), id="QWidget"),
        pytest.param("QTabWidget", marks=pytest.mark.parity("R3-80"), id="QTabWidget"),
        pytest.param("QToolBox", marks=pytest.mark.parity("R3-79"), id="QToolBox"),
        pytest.param("QStackedWidget", marks=pytest.mark.parity("R3-81"), id="QStackedWidget"),
        pytest.param("QScrollArea", marks=pytest.mark.parity("R3-78"), id="QScrollArea"),
        pytest.param("QWizard", id="QWizard"),
        pytest.param("QWizardPage", id="QWizardPage"),
        pytest.param("QMdiArea", marks=pytest.mark.parity("R3-84"), id="QMdiArea"),
        pytest.param("QDockWidget", marks=pytest.mark.parity("R3-85"), id="QDockWidget"),
        pytest.param("QLabel", marks=pytest.mark.parity("R3-102"), id="QLabel"),
        pytest.param("QTextBrowser", marks=pytest.mark.parity("R3-103"), id="QTextBrowser"),
        pytest.param("line-h", marks=pytest.mark.parity("R3-108"), id="line-h"),
        pytest.param("line-v", marks=pytest.mark.parity("R3-109"), id="line-v"),
        pytest.param("QProgressBar", marks=pytest.mark.parity("R3-107"), id="QProgressBar"),
        pytest.param("QLCDNumber", marks=pytest.mark.parity("R3-106"), id="QLCDNumber"),
        pytest.param("QGraphicsView", marks=pytest.mark.parity("R3-104"), id="QGraphicsView"),
        pytest.param("QOpenGLWidget", id="QOpenGLWidget"),
        pytest.param("QQuickWidget", id="QQuickWidget"),
        pytest.param("Gui::QuantitySpinBox", id="Gui::QuantitySpinBox"),
        pytest.param("Gui::InputField", id="Gui::InputField"),
        pytest.param("Gui::FileChooser", id="Gui::FileChooser"),
        pytest.param("Gui::ColorButton", id="Gui::ColorButton"),
        pytest.param("Gui::UrlLabel", id="Gui::UrlLabel"),
        pytest.param("Gui::IntSpinBox", id="Gui::IntSpinBox"),
        pytest.param("Gui::DoubleSpinBox", id="Gui::DoubleSpinBox"),
    ],
)
def test_every_catalog_entry_saves_loads_and_matches_uic(key: str, tmp_path: Path) -> None:
    _require_oracle()
    from tests.form_builder.engine.codegen.uic_compare import compare  # pyright: ignore[reportMissingImports]

    entry = load_catalog().get(key)
    assert entry is not None
    path = tmp_path / "form.ui"
    session = open_session(_host_text(key), str(path))
    try:
        _insert(session, key)
        text = session.text()
    finally:
        session.dispose()
    if entry.payload == "spacer":
        assert "<spacer" in text
    elif entry.freecad:
        assert 'class="%s"' % entry.qt_class in text
    else:
        assert 'class="%s"' % entry.qt_class in text, entry.qt_class
    path.write_text(text, encoding="utf-8")

    outcome = compare(path)
    assert outcome[0] == "ok", outcome

    again = open_session(text, str(path))
    try:
        assert again.text() == text, "a second save of %s is not byte-identical" % key
    finally:
        again.dispose()


@pytest.mark.parametrize("key", _FREECAD)
def test_a_freecad_declaration_lands_once_per_form(key: str) -> None:
    session = open_session(_host_text(key), "/tmp/cbcs-m41-freecad.ui")
    try:
        _insert(session, key)
        _insert(session, key)
        declared = [node for node in session.document.ui.children("customwidgets") if isinstance(node, CustomWidgetNode)]
        assert [node.class_name for node in declared].count(key) == 1
    finally:
        session.dispose()


def test_a_wizard_page_outside_a_wizard_is_refused() -> None:
    session = open_session(build_template_ui("widget", "Form"), "/tmp/cbcs-m41-page.ui")
    try:
        commands = auto_commands(
            session.document,
            None,
            DropPayload("widget"),
            fragment_for("QWizardPage"),
        )
        assert commands == ()
    finally:
        session.dispose()


def test_a_dock_widget_in_a_main_window_central_area_is_refused() -> None:
    session = open_session(build_template_ui("main_window", "Shop"), "/tmp/cbcs-m41-dock.ui")
    try:
        commands = auto_commands(
            session.document,
            session.document.root.id,
            DropPayload("widget"),
            fragment_for("QDockWidget"),
        )
        assert commands == ()
    finally:
        session.dispose()


@pytest.mark.oracle
@pytest.mark.xfail(
    strict=True,
    reason="M4.2 owns engine/codegen/**: uic writes 0 margins for a plain QWidget holder inside a "
    "non-container parent, our generator gives 9 (only does 0 when the object name starts with layoutWidget)",
)
def test_a_layout_without_written_margins_in_a_plain_widget_matches_uic(tmp_path: Path) -> None:
    _require_oracle()
    from tests.form_builder.engine.codegen.uic_compare import compare  # pyright: ignore[reportMissingImports]

    text = (
        '<?xml version="1.0" encoding="UTF-8"?>\n<ui version="4.0">\n <class>Form</class>\n'
        ' <widget class="QWidget" name="Form">\n  <layout class="QVBoxLayout" name="verticalLayout">\n   <item>\n'
        '    <widget class="QWidget" name="holder">\n     <layout class="QVBoxLayout" name="inner"/>\n    </widget>\n'
        "   </item>\n  </layout>\n </widget>\n <resources/>\n <connections/>\n</ui>\n"
    )
    path = tmp_path / "margins.ui"
    path.write_text(text, encoding="utf-8")
    outcome = compare(path)
    assert outcome[0] == "ok", outcome
