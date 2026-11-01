# pyright: reportAttributeAccessIssue=false
"""A rename outside Code Studio offers Repair, and Repair is one undo step."""

from __future__ import annotations

import pytest

from app.features.form_builder.engine.logic.repair import RepairFix
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.engine.ui4.values import StringValue
from app.features.form_builder.integration.workbench_ext.repair_refs import offer_repair
from app.features.form_builder.qtside.dialogs.repair_refs import RepairDialog
from app.qt.QtCore import Qt, QTimer
from app.qt.QtTest import QTest
from app.qt.QtWidgets import QApplication, QComboBox, QPushButton, QWidget
from tests.form_builder.qtside.support import form
from tests.unit.features.form_builder.test_workbench import _open

pytestmark = [pytest.mark.unit, pytest.mark.usefixtures("qapp")]

FORM = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>320</width><height>180</height></rect></property>
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QLineEdit" name="fresh">
     <property name="cbcsValue"><string>oldName</string></property>
    </widget>
   </item>
  </layout>
""",
)
PREVIOUS = {"oldName": "QLineEdit"}


def pump() -> None:
    app = QApplication.instance()
    assert app is not None
    for _ in range(8):
        app.processEvents()


def _value(surface: object) -> str:
    document = surface.session.document  # type: ignore[attr-defined]
    node = document.node(document.by_name("fresh")[0])
    assert isinstance(node, WidgetNode)
    value = node.value("cbcsValue")
    assert isinstance(value, StringValue)
    return value.text


def _host(tmp_path: object, qapp: QApplication) -> tuple:
    del qapp
    host = QWidget()
    host.resize(960, 640)
    host.show()
    surface = _open(host, FORM, tmp_path / "form.ui")  # type: ignore[operator]
    pump()
    return host, surface


def test_a_renamed_widget_shows_the_repair_sentence(tmp_path, qapp: QApplication) -> None:
    host, surface = _host(tmp_path, qapp)
    try:
        before = _value(surface)
        offer_repair(surface.workbench, PREVIOUS)
        pump()
        banner = surface.workbench.canvas.banner
        assert banner.sentence() == "1 rule points at a widget that was renamed outside Code Studio."
        assert banner.findChild(QWidget, "formBuilder.overlayBannerName").text() == "Repair"  # type: ignore[union-attr]
        extra = banner.findChild(QPushButton, "formBuilder.overlayBannerExtra")
        assert extra is not None and extra.text() == "Repair\u2026"
        assert _value(surface) == before == "oldName"
    finally:
        surface.close()
        host.close()
        pump()


def test_the_dialog_lists_the_pair_and_escape_writes_nothing(tmp_path, qapp: QApplication) -> None:
    host, surface = _host(tmp_path, qapp)
    try:
        offer_repair(surface.workbench, PREVIOUS)
        pump()
        extra = surface.workbench.canvas.banner.findChild(QPushButton, "formBuilder.overlayBannerExtra")
        assert extra is not None

        def cancel() -> None:
            dialog = QApplication.activeModalWidget()
            assert isinstance(dialog, RepairDialog)
            assert dialog.windowTitle() == "Repair references"
            label = dialog.findChild(QWidget, "formBuilder.repairName.oldName")
            combo = dialog.findChild(QComboBox, "formBuilder.repairChoice.oldName")
            assert label is not None and label.text() == "oldName"  # type: ignore[attr-defined]
            from app.core.constants import UI_EDITOR_FONT_FAMILY_DEFAULT
            from app.qt.QtGui import QFont

            assert label.font().family() == UI_EDITOR_FONT_FAMILY_DEFAULT or label.font().styleHint() == QFont.Monospace  # type: ignore[attr-defined]
            assert combo is not None and combo.currentData() == "fresh"
            assert combo.currentText() == "fresh \u00b7 Line edit"
            sentence = dialog.findChild(QWidget, "formBuilder.repairSentence")
            uses = dialog.findChild(QWidget, "formBuilder.repairUses.oldName")
            assert sentence is not None and sentence.text() == (  # type: ignore[attr-defined]
                "These rules use names that no longer exist. Pick the widget each name should point at."
            )
            assert uses is not None and uses.text() == "Value on fresh"  # type: ignore[attr-defined]
            assert dialog.findChild(QWidget, "formBuilder.repairTitle") is not None
            QTest.keyClick(dialog, Qt.Key.Key_Escape)

        QTimer.singleShot(0, cancel)
        extra.click()
        pump()
        assert _value(surface) == "oldName"
    finally:
        surface.close()
        host.close()
        pump()


def test_repair_is_one_undo_step(tmp_path, qapp: QApplication) -> None:
    host, surface = _host(tmp_path, qapp)
    try:
        offer_repair(surface.workbench, PREVIOUS)
        pump()
        extra = surface.workbench.canvas.banner.findChild(QPushButton, "formBuilder.overlayBannerExtra")
        assert extra is not None
        depth = len(surface.session.log.entries())

        def accept() -> None:
            dialog = QApplication.activeModalWidget()
            assert isinstance(dialog, RepairDialog)
            button = dialog.findChild(QPushButton, "formBuilder.repairAccept")
            assert button is not None and button.isEnabled()
            button.click()

        QTimer.singleShot(0, accept)
        extra.click()
        pump()
        log = surface.session.log
        assert _value(surface) == "fresh"
        assert len(log.entries()) == depth + 1
        assert log.entries()[-1].label == "Repair references"
        assert log.undo()
        assert _value(surface) == "oldName"
        assert len(log.entries()) == depth
        assert log.redo()
        assert _value(surface) == "fresh"
    finally:
        surface.close()
        host.close()
        pump()


def test_repair_stays_disabled_until_every_name_is_chosen(qapp: QApplication) -> None:
    del qapp
    dialog = RepairDialog(
        (
            RepairFix("owner", "cbcsValue", "oldName", ("fresh", "other")),
            RepairFix("owner", "cbcsEnabledWhen", "gone", ("fresh",)),
        )
    )
    dialog.show()
    pump()
    accept = dialog.findChild(QPushButton, "formBuilder.repairAccept")
    assert accept is not None and not accept.isEnabled()
    old = dialog.findChild(QComboBox, "formBuilder.repairChoice.oldName")
    assert old is not None
    gone = dialog.findChild(QComboBox, "formBuilder.repairChoice.gone")
    assert gone is not None and gone.currentData() == "fresh"
    old.setCurrentIndex(old.findData("other"))
    pump()
    assert accept.isEnabled()
    dialog.reject()
