# pyright: reportAttributeAccessIssue=false
"""M6.R follow-ups: a picker does not pile up, and the banner fits its sentence."""

from __future__ import annotations

import weakref

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.features.form_builder.qtside.canvas.banner import ModeBanner  # noqa: E402
from app.features.form_builder.qtside.pickers.popover import EventPicker  # noqa: E402
from app.features.form_builder.qtside.theme.chrome import default_chrome  # noqa: E402
from app.qt.QtCore import QCoreApplication, QEvent  # noqa: E402
from app.qt.QtWidgets import QApplication, QLabel, QWidget  # noqa: E402

SENTENCE = (
    "Drag from a widget to the widget it should act on. "
    "Drop on the form's background to act on the form."
)


def test_ten_event_pickers_are_gone_after_they_close(qapp: QApplication) -> None:
    parent = QWidget()
    chrome = default_chrome()
    refs = []
    for _ in range(10):
        picker = EventPicker(parent, chrome, lambda _gesture: None)
        picker.show()
        refs.append(weakref.ref(picker))
        picker.release()
        del picker
    qapp.processEvents()
    QCoreApplication.sendPostedEvents(None, int(QEvent.Type.DeferredDelete.value))
    qapp.processEvents()
    assert [ref() for ref in refs if ref() is not None] == []


def test_the_banner_grows_to_fit_its_sentence(qapp: QApplication) -> None:
    parent = QWidget()
    parent.resize(236, 400)
    banner = ModeBanner(parent)
    banner.show_mode("connect", "Connections", SENTENCE, "", None, lambda: None)
    parent.show()
    qapp.processEvents()
    height = banner.fitted_height(236)
    banner.resize(236, height)
    label = banner.findChild(QLabel, "formBuilder.overlayBannerText")
    assert label is not None
    assert height >= label.height()
    assert SENTENCE == banner.sentence()
    font = banner.font()
    font.setPointSize(max(font.pointSize(), 8) * 2)
    banner.setFont(font)
    label.setFont(font)
    tall = banner.fitted_height(236)
    assert tall >= height
