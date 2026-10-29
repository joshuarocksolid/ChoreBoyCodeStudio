# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportOptionalMemberAccess=false
"""Under the Fusion look, Text colour and Background show on every class that has the rows (UX-STYLE-010).

A class where the colour does not show in this render would lose the row, so
each class listed in the row table has to pass.
"""

from __future__ import annotations

from typing import Iterator, List, Tuple

import pytest

from app.features.form_builder.engine.style import colour_rows
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.qt.QtWidgets import QApplication, QStyleFactory
from tests.form_builder.qtside.support import opened

pytestmark = [pytest.mark.usefixtures("qapp"), pytest.mark.unit]

_TEXT = '<property name="text"><string>Wm Wm Wm</string></property>'
_ITEM = '<item><property name="text"><string>Wm Wm Wm</string></property></item>'

#: class, inner properties/children, whether the widget draws its own text
_CLASSES: List[Tuple[str, str, bool]] = [
    ("QLabel", _TEXT, True),
    ("QCheckBox", _TEXT, True),
    ("QRadioButton", _TEXT, True),
    ("QGroupBox", '<property name="title"><string>Wm Wm Wm</string></property>', True),
    ("QFrame", '<widget class="QLabel" name="inner">%s</widget>' % _TEXT, False),
    ("QWidget", '<widget class="QLabel" name="inner">%s</widget>' % _TEXT, False),
    ("QPushButton", _TEXT, True),
    ("QToolButton", _TEXT, True),
    ("QCommandLinkButton", _TEXT, True),
    ("QLineEdit", _TEXT, True),
    ("QTextEdit", '<property name="plainText"><string>Wm Wm Wm</string></property>', True),
    ("QPlainTextEdit", '<property name="plainText"><string>Wm Wm Wm</string></property>', True),
    ("QSpinBox", '<property name="value"><number>88</number></property>', True),
    ("QDoubleSpinBox", '<property name="value"><double>88.0</double></property>', True),
    ("QDateEdit", "", True),
    ("QTimeEdit", "", True),
    ("QDateTimeEdit", "", True),
    ("QListWidget", _ITEM, True),
    ("QTreeWidget", "", True),
    (
        "QTableWidget",
        '<column><property name="text"><string>Wm Wm</string></property></column>'
        '<row><property name="text"><string>Wm</string></property></row>'
        '<item row="0" column="0"><property name="text"><string>Wm Wm Wm</string></property></item>',
        True,
    ),
    ("QComboBox", _ITEM, True),
    ("QComboBox", '<property name="editable"><bool>true</bool></property>' + _ITEM, True),
]


@pytest.fixture(autouse=True)
def _fusion() -> Iterator[None]:
    app = QApplication.instance()
    previous = app.style().objectName()
    if "Fusion" in QStyleFactory.keys():
        app.setStyle("Fusion")
    yield
    for name in QStyleFactory.keys():
        if name.lower() == previous.lower():
            app.setStyle(name)
            break


def _form(class_name: str, inner: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n<ui version="4.0">\n <class>Form</class>\n'
        ' <widget class="QWidget" name="Form">\n  <layout class="QVBoxLayout" name="mainLayout">\n'
        '   <item><widget class="%s" name="subject">%s</widget></item>\n  </layout>\n </widget>\n</ui>\n'
    ) % (class_name, inner)


def _count(widget, matches) -> int:  # type: ignore[no-untyped-def]
    widget.ensurePolished()
    image = widget.grab().toImage()
    found = 0
    for y in range(image.height()):
        for x in range(image.width()):
            color = image.pixelColor(x, y)
            if matches(color.red(), color.green(), color.blue()):
                found += 1
    return found


def _is_green(red: int, green: int, blue: int) -> bool:
    return green > 170 and red < 90 and blue < 90


def _is_red(red: int, green: int, blue: int) -> bool:
    return red > 200 and green < 70 and blue < 70


@pytest.mark.parametrize("class_name,inner,draws_text", _CLASSES, ids=[row[0] + ("-editable" if "editable" in row[1] else "") for row in _CLASSES])
def test_background_and_text_colour_show_on_every_class_with_the_rows(class_name: str, inner: str, draws_text: bool) -> None:
    with opened(_form(class_name, inner)) as (session, realizer):
        document = session.document
        subject = document.by_name("subject")[0]
        node = document.node(subject)
        assert isinstance(node, WidgetNode) and colour_rows.roles_for(document, node) is not None
        widget = realizer.widget_for(subject)
        realizer.root_widget.resize(300, 300)
        widget.resize(220, 90)
        for command in colour_rows.background_commands(document, subject, (0, 200, 0), "Change background"):
            session.log.execute(command)
        QApplication.processEvents()
        assert _count(widget, _is_green) > 200, class_name
        for command in colour_rows.text_color_commands(document, subject, (255, 0, 0), "Change text colour"):
            session.log.execute(command)
        QApplication.processEvents()
        target = widget if draws_text else realizer.widget_for(document.by_name("inner")[0])
        assert _count(target, _is_red) > 8, class_name


def test_the_form_itself_shows_a_background_and_hands_its_text_colour_to_what_is_inside() -> None:
    with opened(_form("QLabel", _TEXT)) as (session, realizer):
        document = session.document
        root = document.root.id
        realizer.root_widget.resize(240, 140)
        for command in colour_rows.background_commands(document, root, (0, 200, 0), "Change background"):
            session.log.execute(command)
        for command in colour_rows.text_color_commands(document, root, (255, 0, 0), "Change text colour"):
            session.log.execute(command)
        QApplication.processEvents()
        assert _count(realizer.root_widget, _is_green) > 1000
        assert _count(realizer.root_widget, _is_red) > 8
