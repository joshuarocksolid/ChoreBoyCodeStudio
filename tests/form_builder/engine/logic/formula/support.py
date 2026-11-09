"""Shared formula fixtures. The env is built without a document, as M7.1b will."""

from __future__ import annotations

from typing import Optional

from app.features.form_builder.engine.logic.formula import FormulaEnv, SlotKind, WidgetFacts
from app.features.form_builder.engine.logic.formula.types import (
    DATE,
    DATETIME,
    MONEY,
    NUMBER,
    PAGE,
    TEXT,
    TIME,
    WHOLE,
    YESNO,
)
from app.features.form_builder.engine.project.window_facts import MethodFacts


def _chain(class_name: str) -> tuple:
    if class_name == "MySpin":
        return ("MySpin", "QSpinBox", "QWidget")
    return (class_name,)


def demo_env(*, data: Optional[object] = None) -> FormulaEnv:
    widgets = {
        "qtySpin": WidgetFacts("QSpinBox", display="Qty"),
        "priceSpin": WidgetFacts("QDoubleSpinBox", display="Price", prefix="$", decimals=2),
        "rateSpin": WidgetFacts("QDoubleSpinBox", display="Rate"),
        "nameEdit": WidgetFacts("QLineEdit", display="Name"),
        "wholeEdit": WidgetFacts("QLineEdit", kind="whole"),
        "percentEdit": WidgetFacts("QLineEdit", kind="percent"),
        "badKind": WidgetFacts("QLineEdit", kind="nope", display="Bad"),
        "notesEdit": WidgetFacts("QPlainTextEdit"),
        "bodyEdit": WidgetFacts("QTextEdit"),
        "titleLabel": WidgetFacts("QLabel", kind="text"),
        "discountCheck": WidgetFacts("QCheckBox", display="Discount"),
        "triCheck": WidgetFacts("QCheckBox", tristate=True),
        "rushRadio": WidgetFacts("QRadioButton"),
        "shipGroup": WidgetFacts("QButtonGroup"),
        "customerCombo": WidgetFacts("QComboBox", display="Customer", has_items_data=True, also=("terms_days",)),
        "plainCombo": WidgetFacts("QComboBox"),
        "invoiceDate": WidgetFacts("QDateEdit", display="Invoice date"),
        "whenEdit": WidgetFacts("QTimeEdit"),
        "stampEdit": WidgetFacts("QDateTimeEdit"),
        "detailTabs": WidgetFacts("QTabWidget", pages=("shippingPage",)),
        "stack": WidgetFacts("QStackedWidget", pages=("summaryPage",)),
        "itemsList": WidgetFacts("QListWidget"),
        "itemsGrid": WidgetFacts("QTableView", display="Items"),
        "progress": WidgetFacts("QProgressBar"),
        "dial": WidgetFacts("QDial"),
        "slider": WidgetFacts("QSlider"),
        "blankSpin": WidgetFacts("QSpinBox", allow_blank=True),
        "mySpin": WidgetFacts("MySpin"),
        "éSpin": WidgetFacts("QSpinBox", display="Café"),
    }
    methods = {
        "is_manager": MethodFacts("is_manager", 10, 12),
        "price_for": MethodFacts("price_for", 14, 20, params=("product", "qty"), required=2),
        "untagged": MethodFacts("untagged", 22, 24),
        "optional": MethodFacts("optional", 26, 28, params=("label",), required=0),
    }
    return FormulaEnv.for_test(
        widgets,
        methods,
        data=data,
        returns={"is_manager": "bool", "price_for": "Decimal", "optional": "str"},
        class_chain=_chain,
        class_name="InvoiceWindow",
        window_file="invoice_window.py",
    )


SLOTS = {
    "cond": SlotKind.condition(),
    "check": SlotKind.check(),
    "when": SlotKind.when(),
    "message": SlotKind.message(),
    "text": SlotKind.value(TEXT),
    "whole": SlotKind.value(WHOLE),
    "number": SlotKind.value(NUMBER),
    "money": SlotKind.value(MONEY),
    "yesno": SlotKind.value(YESNO),
    "date": SlotKind.value(DATE),
    "time": SlotKind.value(TIME),
    "datetime": SlotKind.value(DATETIME),
    "page": SlotKind.value(PAGE),
}


ENV = demo_env()
ENV_DATA = demo_env(data=object())
