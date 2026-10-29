"""Stock widget classes and their bases, for type selectors and the row rules. Qt-free.

``engine/ui4/data/qt_classes.json`` (the class table) is not in the tree yet,
so a type selector would match nothing. This map is the Qt class hierarchy for
the widgets a form can hold; when the class table has the class, its chain is
used instead. A promoted widget (``<customwidget>``) resolves through its base.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from app.features.form_builder.engine.ui4.defaults import QtClassTable
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import CustomWidgetNode, WidgetNode

_BASE: Dict[str, str] = {
    "QAbstractButton": "QWidget",
    "QPushButton": "QAbstractButton",
    "QCommandLinkButton": "QPushButton",
    "QToolButton": "QAbstractButton",
    "QCheckBox": "QAbstractButton",
    "QRadioButton": "QAbstractButton",
    "QAbstractSlider": "QWidget",
    "QSlider": "QAbstractSlider",
    "QScrollBar": "QAbstractSlider",
    "QDial": "QAbstractSlider",
    "QAbstractSpinBox": "QWidget",
    "QSpinBox": "QAbstractSpinBox",
    "QDoubleSpinBox": "QAbstractSpinBox",
    "QDateTimeEdit": "QAbstractSpinBox",
    "QDateEdit": "QDateTimeEdit",
    "QTimeEdit": "QDateTimeEdit",
    "QComboBox": "QWidget",
    "QFontComboBox": "QComboBox",
    "QLineEdit": "QWidget",
    "QKeySequenceEdit": "QWidget",
    "QGroupBox": "QWidget",
    "QFrame": "QWidget",
    "Line": "QFrame",
    "QLabel": "QFrame",
    "QLCDNumber": "QFrame",
    "QSplitter": "QFrame",
    "QStackedWidget": "QFrame",
    "QToolBox": "QFrame",
    "QAbstractScrollArea": "QFrame",
    "QScrollArea": "QAbstractScrollArea",
    "QMdiArea": "QAbstractScrollArea",
    "QGraphicsView": "QAbstractScrollArea",
    "QTextEdit": "QAbstractScrollArea",
    "QTextBrowser": "QTextEdit",
    "QPlainTextEdit": "QAbstractScrollArea",
    "QAbstractItemView": "QAbstractScrollArea",
    "QListView": "QAbstractItemView",
    "QListWidget": "QListView",
    "QTreeView": "QAbstractItemView",
    "QTreeWidget": "QTreeView",
    "QTableView": "QAbstractItemView",
    "QTableWidget": "QTableView",
    "QColumnView": "QAbstractItemView",
    "QHeaderView": "QAbstractItemView",
    "QUndoView": "QListView",
    "QTabWidget": "QWidget",
    "QTabBar": "QWidget",
    "QProgressBar": "QWidget",
    "QDialogButtonBox": "QWidget",
    "QCalendarWidget": "QWidget",
    "QMenuBar": "QWidget",
    "QMenu": "QWidget",
    "QStatusBar": "QWidget",
    "QToolBar": "QWidget",
    "QDockWidget": "QWidget",
    "QMainWindow": "QWidget",
    "QDialog": "QWidget",
    "QWizard": "QDialog",
    "QMessageBox": "QDialog",
    "QInputDialog": "QDialog",
    "QFileDialog": "QDialog",
    "QColorDialog": "QDialog",
    "QFontDialog": "QDialog",
    "QProgressDialog": "QDialog",
    "QWizardPage": "QWidget",
    "QOpenGLWidget": "QWidget",
    "QWidget": "QObject",
}


def stock_chain(class_name: str) -> Tuple[str, ...]:
    """``class_name`` and every base, most derived first. A class this map doesn't know has no bases."""
    found: List[str] = []
    current: Optional[str] = class_name
    while current and current not in found:
        found.append(current)
        current = _BASE.get(current)
    return tuple(found)


def widget_chain(document: UiDocument, node: WidgetNode, table: Optional[QtClassTable] = None) -> Tuple[str, ...]:
    """The classes a widget is, own class first: ``MyEdit, QLineEdit, QWidget, QObject``."""
    names: List[str] = [node.class_name]
    start = node.class_name
    custom = document.custom_widget(node.class_name)
    if isinstance(custom, CustomWidgetNode) and custom.extends:
        start = custom.extends.split("::")[-1]
    shared = table if table is not None else QtClassTable.shared()
    known = tuple(info.name for info in shared.chain(start))
    for name in known or stock_chain(start):
        if name not in names:
            names.append(name)
    if "QWidget" not in names:
        names.extend(("QWidget", "QObject"))
    return tuple(names)


def is_a(chain: Tuple[str, ...], *classes: str) -> bool:
    return any(name in chain for name in classes)


def effective_class(chain: Tuple[str, ...]) -> str:
    """The first class of ``chain`` that is a Qt stock class (a promoted widget's base)."""
    for name in chain:
        if name in _BASE or name == "QObject":
            return name
    return "QWidget"
