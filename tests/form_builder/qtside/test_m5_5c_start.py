# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportOptionalMemberAccess=false
"""Start v2 (UX-START-002, UX-TMPL-004, UX-TMPL-005): Your templates first, the rail, the card menu, the new built-in."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.features.form_builder.engine.project import user_templates as ut
from app.features.form_builder.engine.project.fs import OsFileSystem
from app.features.form_builder.engine.project.templates import template_for, template_keys
from app.features.form_builder.qtside.start.panel import RAIL_MIN_WIDTH, RAIL_WIDTH, NewFormPanel
from app.qt.QtCore import Qt
from app.qt.QtGui import QColor, QPixmap
from app.qt.QtTest import QTest
from app.qt.QtWidgets import QApplication, QLabel, QMenu
from tests.unit.features.form_builder.test_new_form import _chrome

pytestmark = [pytest.mark.unit, pytest.mark.usefixtures("qapp")]

_FORM = (
    '<?xml version="1.0" encoding="UTF-8"?>\n<ui version="4.0">\n <class>Till</class>\n'
    ' <widget class="QWidget" name="Till"/>\n <resources/>\n <connections/>\n</ui>\n'
)


def _save(state: Path, name: str, **extra: object) -> ut.TemplateInfo:
    return ut.save_template(
        scope=extra.pop("scope", ut.SCOPE_USER),  # type: ignore[arg-type]
        state_root=str(state),
        project_root=extra.pop("project_root", None),  # type: ignore[arg-type]
        name=name,
        description=str(extra.pop("description", "")),
        ui_text=_FORM,
        thumbnail=b"",
        **extra,  # type: ignore[arg-type]
    )


def _panel(tmp_path: Path, width: int = 1000) -> NewFormPanel:
    root = tmp_path / "shop"
    (root / "forms").mkdir(parents=True, exist_ok=True)
    panel = NewFormPanel(project_root=str(root), directory=str(root / "forms"), fs=OsFileSystem(), chrome=_chrome())
    panel.resize(width, 800)
    panel.show()
    panel.activateWindow()
    QApplication.processEvents()
    return panel


def _load(panel: NewFormPanel, state: Path, project_root: object = None) -> None:
    panel.set_user_templates(ut.list_templates(str(state), project_root))  # type: ignore[arg-type]
    QApplication.processEvents()


def _thumbnail(path: Path) -> None:
    picture = QPixmap(200, 120)
    picture.fill(QColor("#336699"))
    assert picture.save(str(path), "PNG")


def test_no_group_without_a_saved_template(tmp_path: Path) -> None:
    panel = _panel(tmp_path)
    label = panel.findChild(QLabel, "formBuilder.newForm.group.yours")
    assert label is not None and label.isHidden()
    assert panel.user_template_keys() == ()


@pytest.mark.parity("R3-184")
def test_your_templates_is_the_first_group_and_cards_show_name_description_and_tag(tmp_path: Path) -> None:
    state = tmp_path / "state"
    shop = _save(state, "Shop window", description="Till and receipts")
    (tmp_path / "shop").mkdir()
    mine = _save(state, "This one", scope=ut.SCOPE_PROJECT, project_root=str(tmp_path / "shop"))
    _thumbnail(Path(shop.folder) / "thumbnail.png")
    panel = _panel(tmp_path)
    _load(panel, state, str(tmp_path / "shop"))
    label = panel.findChild(QLabel, "formBuilder.newForm.group.yours")
    assert label.isVisible() and label.text() == "Your templates"
    groups = [w.text() for w in panel.findChildren(QLabel) if w.objectName().startswith("formBuilder.newForm.group.") and w.isVisible()]
    assert groups[0] == "Your templates" and groups[1] == "Templates"
    first = panel.card(shop.card_key)
    assert (first.title(), first.description(), first.tag()) == ("Shop window", "Till and receipts", "")
    assert panel.card(mine.card_key).tag() == "This project"
    assert first.mapTo(panel, first.rect().topLeft()).y() < panel.card("data_entry").mapTo(panel, first.rect().topLeft()).y()


def test_tab_goes_from_the_name_row_to_your_templates_before_the_built_ins(tmp_path: Path) -> None:
    state = tmp_path / "state"
    shop = _save(state, "Shop window")
    panel = _panel(tmp_path)
    _load(panel, state)
    panel.focus_name()
    seen = []
    for _ in range(5):
        QTest.keyClick(QApplication.focusWidget(), Qt.Key_Tab)
        seen.append(getattr(QApplication.focusWidget(), "key", QApplication.focusWidget().objectName()))
    assert shop.card_key in seen and seen.index(shop.card_key) < seen.index("data_entry")


def test_ctrl_down_and_up_move_between_groups(tmp_path: Path) -> None:
    state = tmp_path / "state"
    shop = _save(state, "Shop window")
    panel = _panel(tmp_path)
    _load(panel, state)
    panel.card(shop.card_key).setFocus()
    QTest.keyClick(panel.card(shop.card_key), Qt.Key_Down, Qt.ControlModifier)
    assert QApplication.focusWidget() is panel.card("data_entry")
    QTest.keyClick(QApplication.focusWidget(), Qt.Key_Down, Qt.ControlModifier)
    assert QApplication.focusWidget() is panel.card("widget")
    QTest.keyClick(QApplication.focusWidget(), Qt.Key_Up, Qt.ControlModifier)
    assert QApplication.focusWidget() is panel.card("data_entry")
    QTest.keyClick(QApplication.focusWidget(), Qt.Key_Up, Qt.ControlModifier)
    assert QApplication.focusWidget() is panel.card(shop.card_key)


def test_shift_f10_offers_rename_description_and_delete(tmp_path: Path) -> None:
    state = tmp_path / "state"
    shop = _save(state, "Shop window")
    panel = _panel(tmp_path)
    _load(panel, state)
    got = []
    panel.template_action_requested.connect(lambda action, key: got.append((action, key)))
    card = panel.card(shop.card_key)
    card.setFocus()
    QTest.keyClick(card, Qt.Key_F10, Qt.ShiftModifier)
    menu = panel.findChild(QMenu, "formBuilder.newForm.templateMenu")
    assert [a.text() for a in menu.actions()] == ["Rename…", "Change description…", "Delete template…"]
    menu.actions()[2].trigger()
    assert got == [("delete", shop.card_key)]
    assert panel.card("data_entry").has_menu() is False


def test_a_template_that_cannot_be_read_is_one_card_with_delete_only(tmp_path: Path) -> None:
    state = tmp_path / "state"
    broken = state / "form_templates" / "oops"
    broken.mkdir(parents=True)
    (broken / "template.json").write_text("{", encoding="utf-8")
    panel = _panel(tmp_path)
    _load(panel, state)
    (key,) = panel.user_template_keys()
    card = panel.card(key)
    assert card.title() == "Can't open oops" and "template.json" in card.toolTip() and not card.isEnabled()
    menu = panel.open_template_menu(key)
    assert [a.text() for a in menu.actions()] == ["Delete template…"]


def test_a_card_is_not_clickable_while_the_name_is_refused(tmp_path: Path) -> None:
    state = tmp_path / "state"
    shop = _save(state, "Shop window")
    panel = _panel(tmp_path)
    _load(panel, state)
    asked = []
    panel.create_requested.connect(asked.append)
    panel.set_stem("not a name")
    assert not panel.card(shop.card_key).isEnabled()
    panel.set_stem("back_office")
    QTest.keyClick(panel.card(shop.card_key), Qt.Key_Return)
    assert asked == [shop.card_key]


def test_recent_forms_sit_in_a_240_px_rail_from_1180_px(tmp_path: Path) -> None:
    narrow = _panel(tmp_path, 1100)
    assert not narrow.rail_shown()
    wide = _panel(tmp_path, RAIL_MIN_WIDTH)
    box = wide.findChild(QLabel, "formBuilder.newForm.recentTitle").parentWidget()
    assert wide.rail_shown() and box.width() == RAIL_WIDTH
    column = wide.findChild(QLabel, "formBuilder.newForm.hero").parentWidget()
    assert box.mapTo(wide, box.rect().topLeft()).x() >= column.mapTo(wide, column.rect().topRight()).x()
    wide.resize(1000, 800)
    QApplication.processEvents()
    assert not wide.rail_shown() and box.parentWidget() is column


@pytest.mark.parity("R3-183")
def test_the_side_buttons_dialog_is_a_template_card(tmp_path: Path) -> None:
    assert "dialog_buttons_right" in template_keys()
    spec = template_for("dialog_buttons_right")
    assert spec.title == "Dialog with side buttons" and spec.root_class == "QDialog"
    from app.features.form_builder.engine.project.templates import build_template_ui

    text = build_template_ui("dialog_buttons_right", "Invoice")
    assert 'class="QHBoxLayout"' in text and "Qt::Orientation::Vertical" in text
    assert "<signal>accepted()</signal>" in text and "<signal>rejected()</signal>" in text
    assert _panel(tmp_path).card("dialog_buttons_right").title() == "Dialog with side buttons"


@pytest.mark.perf
def test_start_with_20_saved_templates_paints_in_150_ms_of_cpu(tmp_path: Path) -> None:
    state = tmp_path / "state"
    for number in range(20):
        info = _save(state, "Template %d" % number, description="One of twenty")
        _thumbnail(Path(info.folder) / "thumbnail.png")
    found = ut.list_templates(str(state), None)
    started = time.process_time()
    panel = _panel(tmp_path)
    panel.set_user_templates(found)
    QApplication.processEvents()
    panel.grab()
    elapsed = time.process_time() - started
    assert len(panel.user_template_keys()) == 20
    assert elapsed < 0.15, "%.0f ms of CPU" % (elapsed * 1000)
