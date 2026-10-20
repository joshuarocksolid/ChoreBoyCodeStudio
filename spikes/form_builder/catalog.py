"""Widget box entries. Layout tools and spacers are not widgets."""

from __future__ import annotations

from dataclasses import dataclass

MIME = "application/x-cbcs-form-widget"


@dataclass(frozen=True)
class Entry:
    label: str
    class_name: str
    kind: str
    category: str


CATALOG = (
    Entry("Vertical layout", "QVBoxLayout", "layout", "Layouts"),
    Entry("Horizontal layout", "QHBoxLayout", "layout", "Layouts"),
    Entry("Grid layout", "QGridLayout", "layout", "Layouts"),
    Entry("Form layout", "QFormLayout", "layout", "Layouts"),
    Entry("Horizontal spacer", "Qt::Horizontal", "spacer", "Layouts"),
    Entry("Vertical spacer", "Qt::Vertical", "spacer", "Layouts"),
    Entry("Label", "QLabel", "widget", "Display"),
    Entry("Push button", "QPushButton", "widget", "Buttons"),
    Entry("Tool button", "QToolButton", "widget", "Buttons"),
    Entry("Check box", "QCheckBox", "widget", "Buttons"),
    Entry("Radio button", "QRadioButton", "widget", "Buttons"),
    Entry("Dialog button box", "QDialogButtonBox", "widget", "Buttons"),
    Entry("Line edit", "QLineEdit", "widget", "Input"),
    Entry("Plain text", "QPlainTextEdit", "widget", "Input"),
    Entry("Spin box", "QSpinBox", "widget", "Input"),
    Entry("Double spin box", "QDoubleSpinBox", "widget", "Input"),
    Entry("Combo box", "QComboBox", "widget", "Input"),
    Entry("Date", "QDateEdit", "widget", "Input"),
    Entry("Date and time", "QDateTimeEdit", "widget", "Input"),
    Entry("Time", "QTimeEdit", "widget", "Input"),
    Entry("Slider", "QSlider", "widget", "Input"),
    Entry("Group box", "QGroupBox", "widget", "Containers"),
    Entry("Frame", "QFrame", "widget", "Containers"),
    Entry("Tab widget", "QTabWidget", "widget", "Containers"),
    Entry("Stacked widget", "QStackedWidget", "widget", "Containers"),
    Entry("Scroll area", "QScrollArea", "widget", "Containers"),
    Entry("Splitter", "QSplitter", "widget", "Containers"),
    Entry("List", "QListWidget", "widget", "Item views"),
    Entry("Table", "QTableWidget", "widget", "Item views"),
    Entry("Tree", "QTreeWidget", "widget", "Item views"),
    Entry("Progress bar", "QProgressBar", "widget", "Display"),
)


def fuzzy(query: str, label: str) -> bool:
    if not query:
        return True
    haystack = label.lower().replace(" ", "")
    cursor = 0
    for char in query.lower().replace(" ", ""):
        found = haystack.find(char, cursor)
        if found < 0:
            return False
        cursor = found + 1
    return True
