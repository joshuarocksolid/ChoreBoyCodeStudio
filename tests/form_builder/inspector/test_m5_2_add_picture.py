# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
"""Add picture in the picker and the image rows (UX-RES-001, 002, 005; K17)."""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Iterator, List, Tuple

import pytest

from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.project.forms import classify_form
from app.features.form_builder.engine.project.fs import OsFileSystem
from app.features.form_builder.engine.project.qrc_write import add_pictures
from app.features.form_builder.engine.project.save import write_generated
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.reader import read_ui
from app.features.form_builder.qtside.inspector import InspectorPane
from app.features.form_builder.qtside.inspector.api import GroupId
from app.features.form_builder.qtside.inspector.editors._picture_picker import PicturePicker
from app.features.form_builder.qtside.realize import Realizer
from app.qt.QtCore import Qt
from app.qt.QtTest import QTest
from app.qt.QtUiTools import QUiLoader
from app.qt.QtWidgets import QApplication, QFileDialog, QLabel, QPushButton, QWidget
from tests.form_builder.inspector.test_m43c_pictures import (
    _CHROME,
    _close,
    _open_row,
    _png_bytes,
    _search,
    _select,
)

pytestmark = [pytest.mark.unit, pytest.mark.usefixtures("qapp")]

_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Till</class>
 <widget class="QWidget" name="Till">
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QLabel" name="logo"/>
   </item>
   <item>
    <widget class="QPushButton" name="payButton">
     %s
    </widget>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


class _Toasts:
    def __init__(self) -> None:
        self.sentences: List[str] = []

    def show_plain(self, sentence: str) -> None:
        self.sentences.append(sentence)


def _open(qapp: QApplication, root: Path, extra: str = "") -> Tuple[QWidget, InspectorPane, FormSession, Realizer, _Toasts]:
    ui = root / "forms" / "till.ui"
    (root / "forms").mkdir(parents=True, exist_ok=True)
    text = _FORM % extra
    ui.write_text(text, encoding="utf-8")
    scope = classify_form(str(ui), project_root=str(root))
    session = FormSession.open(text, path=str(ui), scope=scope)
    realizer = Realizer(session)
    realizer.build()
    toasts = _Toasts()
    window = QWidget()
    from app.qt.QtWidgets import QVBoxLayout

    window.show_plain = toasts.show_plain  # the form tab's toast, found by walking up from the row
    pane = InspectorPane(session, realizer, data_tab=False, on_leave=lambda: None, parent=window)
    pane.apply_chrome(_CHROME)
    layout = QVBoxLayout(window)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(pane)
    window.resize(1400, 900)
    window.show()
    qapp.setActiveWindow(window)
    qapp.processEvents()
    pane.set_group_expanded(GroupId.ALL, True)
    pane.flush()
    return window, pane, session, realizer, toasts


@pytest.fixture()
def shop(tmp_path: Path) -> Iterator[Path]:
    root = tmp_path / "shop"
    root.mkdir()
    desktop = tmp_path / "desktop"
    desktop.mkdir()
    (desktop / "logo.png").write_bytes(_png_bytes())
    yield root


def _fixture(root: Path) -> str:
    return str(root.parent / "desktop" / "logo.png")


def _footer(qapp: QApplication) -> QPushButton:
    qapp.processEvents()
    found = [w for w in QApplication.allWidgets() if w.objectName() == "formBuilder.pictureAdd" and w.isVisible()]
    assert found
    return found[-1]


def test_k17_add_picture_makes_the_pictures_file_and_is_one_undo_step(
    qapp: QApplication, shop: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    window, pane, session, realizer, toasts = _open(qapp, shop)
    try:
        _select(session, "logo")
        pane.flush()
        steps = len(session.log.entries())
        _open_row(pane, "formBuilder.row.pixmap", qapp)
        button = _footer(qapp)
        assert button.text() == "Add picture…" and QApplication.focusWidget() is button
        monkeypatch.setattr(QFileDialog, "getOpenFileNames", staticmethod(lambda *a, **k: ([_fixture(shop)], "")))
        button.click()
        qapp.processEvents()
        qrc = shop / "forms" / "resources.qrc"
        assert "<file>pictures/logo.png</file>" in qrc.read_text(encoding="utf-8")
        assert (shop / "forms" / "pictures" / "logo.png").read_bytes() == _png_bytes()
        assert "<pixmap>:/pictures/logo.png</pixmap>" in session.text()
        assert 'location="resources.qrc"' in session.text()
        assert len(session.log.entries()) == steps + 1
        assert session.log.undo_label() == "Add picture logo.png"
        assert toasts.sentences == ["Made forms/resources.qrc for this project's pictures and added logo.png."]
        # The files are not on the undo stack.
        assert session.log.undo()
        assert "logo.png" not in session.text() and "resources.qrc" not in session.text()
        assert qrc.is_file() and (shop / "forms" / "pictures" / "logo.png").is_file()
        assert session.log.redo()
        assert "<pixmap>:/pictures/logo.png</pixmap>" in session.text()
    finally:
        _close(window, pane, realizer, session, qapp)


def test_k17_saved_form_writes_the_picture_module_and_a_loader_shows_the_picture(
    qapp: QApplication, shop: Path
) -> None:
    ui = shop / "forms" / "till.ui"
    (shop / "forms").mkdir()
    add_pictures(str(shop), str(shop / "forms" / "resources.qrc"), [_fixture(shop)])
    text = (_FORM % "").replace(
        '<widget class="QLabel" name="logo"/>',
        '<widget class="QLabel" name="logo"><property name="pixmap"><pixmap>:/pictures/logo.png</pixmap></property></widget>',
    ).replace("<resources/>", '<resources><include location="resources.qrc"/></resources>')
    ui.write_text(text, encoding="utf-8")
    scope = classify_form(str(ui), project_root=str(shop))
    document = read_ui(text, allocator=IdAllocator()).document
    result = write_generated(scope, document, text.encode("utf-8"), OsFileSystem())
    rc = shop / "forms" / "resources_rc.py"
    assert result.text_written and rc.is_file()
    namespace = runpy.run_path(str(rc))
    try:
        loaded = QUiLoader().load(str(ui))
        label = loaded.findChild(QLabel, "logo")
        assert label is not None and not label.pixmap().isNull()
        loaded.deleteLater()
    finally:
        namespace["qCleanupResources"]()


def test_a_picture_from_another_pictures_file_adds_the_include_in_the_same_step(
    qapp: QApplication, shop: Path
) -> None:
    desktop = shop.parent / "desktop"
    add_pictures(str(shop), str(shop / "assets" / "more.qrc"), [str(desktop / "logo.png")])
    window, pane, session, realizer, _toasts = _open(qapp, shop)
    try:
        _select(session, "logo")
        pane.flush()
        steps = len(session.log.entries())
        _open_row(pane, "formBuilder.row.pixmap", qapp)
        search = _search(qapp)
        picker = search.parent()
        assert isinstance(picker, PicturePicker)
        assert picker.grid.count() == 1
        QTest.keyClick(search, Qt.Key.Key_Down)
        QTest.keyClick(picker.grid, Qt.Key.Key_Return)
        qapp.processEvents()
        assert "<pixmap>:/pictures/logo.png</pixmap>" in session.text()
        assert 'location="../assets/more.qrc"' in session.text()
        assert len(session.log.entries()) == steps + 1
        assert session.log.undo()
        assert "more.qrc" not in session.text() and "logo.png" not in session.text()
    finally:
        _close(window, pane, realizer, session, qapp)


def test_two_pictures_files_show_where_new_pictures_go_and_the_change_menu_lists_them(
    qapp: QApplication, shop: Path
) -> None:
    desktop = shop.parent / "desktop"
    add_pictures(str(shop), str(shop / "forms" / "resources.qrc"), [str(desktop / "logo.png")])
    add_pictures(str(shop), str(shop / "assets" / "more.qrc"), [str(desktop / "logo.png")])
    window, pane, session, realizer, _toasts = _open(qapp, shop)
    try:
        _select(session, "logo")
        pane.flush()
        _open_row(pane, "formBuilder.row.pixmap", qapp)
        picker = _search(qapp).parent()
        assert picker.target_caption.text() == "New pictures go into forms/resources.qrc."
        assert [a.text() for a in picker._menu.actions()] == ["assets/more.qrc", "forms/resources.qrc"]
        picker._menu.actions()[0].trigger()
        assert picker.target_caption.text() == "New pictures go into assets/more.qrc."
    finally:
        _close(window, pane, realizer, session, qapp)


def test_a_file_path_icon_gets_a_fix_link_and_the_fix_is_one_step(qapp: QApplication, shop: Path) -> None:
    (shop / "forms" / "art").mkdir(parents=True)
    (shop / "forms" / "art" / "pay.png").write_bytes(_png_bytes())
    icon = '<property name="icon"><iconset><normaloff>art/pay.png</normaloff></iconset></property>'
    window, pane, session, realizer, toasts = _open(qapp, shop, icon)
    try:
        _select(session, "payButton")
        pane.flush()
        link = pane.findChild(QPushButton, "formBuilder.pictureAdopt")
        assert link is not None and link.isVisible() and link.text() == "Add to project pictures"
        steps = len(session.log.entries())
        link.click()
        qapp.processEvents()
        assert "<normaloff>:/art/pay.png</normaloff>" in session.text()
        assert len(session.log.entries()) == steps + 1
        assert session.log.undo_label() == "Add picture pay.png"
        assert toasts.sentences[-1].startswith("Made forms/resources.qrc")
        pane.flush()
        assert link.isVisible() is False
    finally:
        _close(window, pane, realizer, session, qapp)


@pytest.mark.xfail(
    strict=True,
    reason="integration/toast.py (no M5 lane owns it; orchestrator): notice_sentence() does not ask "
    "qtside.resources.notices, so the step 'Add picture x' toasts without Undo and without the sentence",
)
def test_the_toast_for_add_picture_carries_the_sentence_and_undo() -> None:
    from app.features.form_builder.integration.toast import notice_sentence
    from app.features.form_builder.qtside.resources import notices

    sentence = "Added logo.png to forms/resources.qrc. Undo keeps the copied file."
    notices.remember("Add picture logo.png", sentence)
    assert notice_sentence("Add picture logo.png") == sentence
