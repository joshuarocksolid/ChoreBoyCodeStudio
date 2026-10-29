# pyright: reportAttributeAccessIssue=false
"""The tab stops the builder shows are the ones Qt tabs through (UX-MODE-003, UX-OVL-006).

A form edited with the M5.6 commands is loaded by Qt and its focus chain walked:
the stops and their order match ``tab_stops.stops``. ``takes_tab_focus`` agrees
with each catalog class's real default focus policy.
"""

from __future__ import annotations

from typing import List

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.features.form_builder.engine.commands.catalog import InsertFragment  # noqa: E402
from app.features.form_builder.engine.commands.catalog_ext.tab_order import ChangeTabOrder  # noqa: E402
from app.features.form_builder.engine.commands.placement import InFormRow  # noqa: E402
from app.features.form_builder.engine.query import tab_stops as q  # noqa: E402
from app.features.form_builder.engine.query.tree import takes_tab_focus  # noqa: E402
from app.features.form_builder.engine.ui4.spec import Fragment  # noqa: E402
from app.features.form_builder.engine.ui4.writer import write_ui  # noqa: E402
from app.qt import QtCore, QtWidgets  # noqa: E402
from app.qt.QtCore import QBuffer, QByteArray, QIODevice  # noqa: E402
from app.qt.QtUiTools import QUiLoader  # noqa: E402
from tests.form_builder.engine.commands._support import button_spec, open_log  # noqa: E402
from tests.form_builder.engine.test_m5_6_tab_order import ROWS  # noqa: E402

pytestmark = pytest.mark.unit

BOX = ROWS.replace(
    '   <item row="3" column="0" colspan="2"><widget class="QLabel" name="note">',
    '   <item row="4" column="0" colspan="2"><widget class="QDialogButtonBox" name="buttonBox">'
    '<property name="standardButtons"><set>QDialogButtonBox::Cancel|QDialogButtonBox::Ok</set></property></widget></item>\n'
    '   <item row="3" column="0" colspan="2"><widget class="QLabel" name="note">',
)


def _chain(text: str) -> List[str]:
    data = QByteArray(text.encode("utf-8"))
    buffer = QBuffer(data)
    buffer.open(QIODevice.ReadOnly)
    form = QUiLoader().load(buffer)
    assert form is not None
    form.show()
    names: List[str] = []
    widget = form.nextInFocusChain()
    while widget is not form:
        if int(widget.focusPolicy()) & int(QtCore.Qt.TabFocus) and widget.isVisibleTo(form):
            names.append(widget.objectName() or "<%s>" % type(widget).__name__)
        widget = widget.nextInFocusChain()
    form.close()
    form.deleteLater()
    return names


def test_a_custom_order_with_a_spliced_input_is_the_order_qt_tabs_through(qapp) -> None:  # type: ignore[no-untyped-def]
    del qapp
    log = open_log(BOX)
    doc = log.document
    log.execute(ChangeTabOrder(("phoneEdit", "nameEdit", "emailEdit")))
    layout = doc.by_name("formLayout")[0]
    log.execute(InsertFragment(InFormRow(layout, 1, "field", insert_row=True), Fragment(nodes=(button_spec("extraButton"),))))
    shown = [stop.name for stop in q.stops(doc)]
    assert shown == ["phoneEdit", "nameEdit", "extraButton", "emailEdit"]
    chain = _chain(write_ui(doc).text)
    # The button box is not a stop: its buttons keep their own place after the numbered ones.
    assert [name for name in chain if not name.startswith("<")] == shown
    assert chain[len(shown):] == ["<QPushButton>", "<QPushButton>"]


@pytest.mark.parametrize(
    "class_name",
    [
        "QLineEdit", "QTextEdit", "QPlainTextEdit", "QTextBrowser", "QComboBox", "QFontComboBox", "QSpinBox",
        "QDoubleSpinBox", "QCheckBox", "QRadioButton", "QPushButton", "QToolButton", "QCommandLinkButton",
        "QDateEdit", "QTimeEdit", "QDateTimeEdit", "QDial", "QSlider", "QScrollBar", "QListWidget", "QTableWidget",
        "QTreeWidget", "QListView", "QTreeView", "QTableView", "QColumnView", "QUndoView", "QKeySequenceEdit",
        "QCalendarWidget", "QGraphicsView", "QScrollArea", "QTabWidget", "QDialogButtonBox", "QLabel", "QGroupBox",
        "QFrame", "QWidget", "QStackedWidget", "QToolBox", "QMdiArea", "QProgressBar", "QLCDNumber", "QSplitter",
    ],
)
def test_takes_tab_focus_matches_the_class_default_policy(qapp, class_name: str) -> None:  # type: ignore[no-untyped-def]
    del qapp
    from app.features.form_builder.engine.ui4.nodes import WidgetNode

    real = getattr(QtWidgets, class_name)()
    expected = bool(int(real.focusPolicy()) & int(QtCore.Qt.TabFocus))
    real.deleteLater()
    node = open_log(
        '<?xml version="1.0" encoding="UTF-8"?>\n<ui version="4.0">\n <class>Form</class>\n'
        ' <widget class="QWidget" name="Form">\n  <widget class="%s" name="probe"/>\n </widget>\n'
        " <resources/>\n <connections/>\n</ui>\n" % class_name
    ).document
    probe = node.get(node.by_name("probe")[0])
    assert isinstance(probe, WidgetNode)
    assert takes_tab_focus(probe) is expected
