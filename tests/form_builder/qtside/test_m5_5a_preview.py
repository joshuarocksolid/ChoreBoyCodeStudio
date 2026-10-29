# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportOptionalMemberAccess=false, reportOptionalCall=false, reportIndexIssue=false
"""Preview options, Save image, Print and View Python code in a real main window (M5.5a).

The Aa menu, the Form menu, the Add a screen dialog, the preview child (real, over pipes),
the picture Save image takes from an open Preview, a PDF print, and the code split.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, List

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.features.form_builder.engine.commands.catalog import Rename  # noqa: E402
from app.features.form_builder.engine.ipc.timing import DirectorConfig  # noqa: E402
from app.features.form_builder.engine.query.selection import SelectionSource  # noqa: E402
from app.features.form_builder.integration import image_export  # noqa: E402
from app.features.form_builder.integration.memory import PreviewOptionsStore  # noqa: E402
from app.features.form_builder.integration.preview_options import CAPTION, clean_profile  # noqa: E402
from app.features.form_builder.qtside.preview.launch import (  # noqa: E402
    current_runtime_python,
    python_preview_command,
    repo_root,
)
from app.features.form_builder.qtside.preview.pool import PreviewPool  # noqa: E402
from app.qt.QtGui import QImage  # noqa: E402
from app.qt.QtTest import QTest  # noqa: E402
from app.qt.QtWidgets import QApplication, QDialog, QMenu, QPushButton  # noqa: E402
from tests.form_builder.qtside.test_m3_keyboard_scripts import Kb, _close, _key, _NoMouse, _session  # noqa: E402

pytestmark = [pytest.mark.unit, pytest.mark.timeout(300)]

_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Customer</class>
 <widget class="QWidget" name="Customer">
  <property name="geometry"><rect><x>0</x><y>0</y><width>480</width><height>420</height></rect></property>
  <layout class="QVBoxLayout" name="mainLayout">
   <item><widget class="QLabel" name="nameLabel"><property name="text"><string>Name:</string></property></widget></item>
   <item><widget class="QLineEdit" name="nameEdit"/></item>
   <item><widget class="QPushButton" name="saveButton"><property name="text"><string>Save</string></property></widget></item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


def _pump_until(qapp: QApplication, predicate: Callable[[], bool], seconds: float = 25.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        qapp.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return False


def _real_pool() -> PreviewPool:
    pool = PreviewPool(
        command=python_preview_command(current_runtime_python(), repo_root()),
        config=DirectorConfig(handshake_timeout=20.0, request_timeout=15.0, shutdown_grace=0.4, ping_interval=30.0, prewarm=True),
        root=repo_root(),
    )
    PreviewPool._shared = pool
    return pool


_NAMES = {
    "Style": "formBuilder.previewStyleMenu",
    "Screen": "formBuilder.previewScreenMenu",
    "Preview options": "formBuilder.menu.Preview options",
}


def _submenu(menu: QMenu, title: str) -> QMenu:
    """A submenu by object name. (A QMenu taken from ``QAction.menu()`` goes stale when that action wrapper is collected.)"""
    name = _NAMES[title]
    if title == "Screen" and menu.objectName() == "formBuilder.menu.Preview options":
        name = "formBuilder.menu.Screen"
    found = menu.findChild(QMenu, name)
    assert found is not None, "no submenu %r" % title
    return found


def _rows(menu: QMenu) -> List[str]:
    return [a.text() for a in menu.actions() if not a.isSeparator() or a.text()]


def _aa_menu(surface) -> QMenu:  # noqa: ANN001
    menu = surface._toolbar.text_size.menu()
    menu.aboutToShow.emit()
    return menu


@pytest.mark.parity("R3-178", "R3-179")
def test_the_aa_menu_lists_styles_and_screens_with_the_caption_and_remembers_a_pick(
    tmp_path: Path, qapp: QApplication
) -> None:
    window, kb, guard = _session(tmp_path, qapp, _FORM)
    try:
        surface = kb.surface
        control = surface.preview_control
        menu = _aa_menu(surface)
        style_menu = _submenu(menu, "Style")
        screen_menu = _submenu(menu, "Screen")
        for sub in (style_menu, screen_menu):
            first = sub.actions()[0]
            assert first.isSeparator() and first.text() == CAPTION
        styles = [a for a in style_menu.actions() if a.isCheckable()]
        assert styles[0].text() == "Fusion · as on ChoreBoy" and styles[0].isChecked()
        assert [a.text() for a in styles[1:]]  # every other style the runtime reports, by name
        screens = [a for a in screen_menu.actions() if a.isCheckable()]
        assert [a.text() for a in screens] == [
            "ChoreBoy screen · 1366 × 768",
            "Small screen · 1024 × 600",
            "Full HD · 1920 × 1080",
        ]
        assert screens[0].isChecked()
        assert screen_menu.actions()[-1].text() == "Add a screen…"
        screens[1].trigger()
        assert control.choices.screen == "Small screen"
        menu = _aa_menu(surface)
        checked = [a.text() for a in _submenu(menu, "Screen").actions() if a.isCheckable() and a.isChecked()]
        assert checked == ["Small screen · 1024 × 600"]
        # Per user, not in the form: a new tab (new control) starts from the stored choice, and the file is unchanged.
        assert PreviewOptionsStore(str(tmp_path / "state")).load()[0].screen == "Small screen"
        assert "Small" not in kb.text()
        assert not kb.session.log.can_undo()
    finally:
        _close(window, qapp, guard)


@pytest.mark.parity("R3-179")
def test_add_a_screen_asks_for_six_fields_and_the_new_screen_joins_both_menus(tmp_path: Path, qapp: QApplication) -> None:
    window, kb, guard = _session(tmp_path, qapp, _FORM)
    try:
        surface = kb.surface
        control = surface.preview_control
        dialog = control.add_screen_dialog()
        qapp.processEvents()
        assert isinstance(dialog, QDialog)
        labels = ["Name", "Width", "Height", "Font", "Font size", "Scale"]
        fields = [
            dialog.name.accessibleName(),
            dialog.width_box.accessibleName(),
            dialog.height_box.accessibleName(),
            dialog.font.accessibleName(),
            dialog.font_size.accessibleName(),
            dialog.scale.accessibleName(),
        ]
        assert fields == labels
        assert (dialog.scale.minimum(), dialog.scale.maximum()) == (100, 200)
        add = dialog.findChild(QPushButton, "formBuilder.screenAdd")
        assert not add.isEnabled(), "the Add button waits for a name"
        dialog.name.setText("small screen")
        assert not add.isEnabled(), "a built-in screen's name is not available"
        dialog.name.setText("Till counter")
        assert add.isEnabled()
        dialog.width_box.setValue(1280)
        dialog.height_box.setValue(800)
        dialog.font_size.setValue(14)
        dialog.scale.setValue(150)
        add.click()
        qapp.processEvents()
        assert control.choices.screen == "Till counter"
        assert [p.name for p in control.user_profiles()] == ["Till counter"]
        menu = _aa_menu(surface)
        texts = [a.text() for a in _submenu(menu, "Screen").actions() if a.isCheckable()]
        assert texts[-1] == "Till counter · 1280 × 800"
        form = window.findChild(QMenu, "formBuilder.menu")
        form.aboutToShow.emit()
        in_form = [a.text() for a in _submenu(form, "Preview options").findChild(QMenu, "formBuilder.menu.Screen").actions()]
        assert "Till counter · 1280 × 800" in in_form and in_form[-1] == "Add a screen…"
        stored = PreviewOptionsStore(str(tmp_path / "state")).load()[1]
        assert (stored[0].width, stored[0].height, stored[0].font_size, stored[0].scale) == (1280, 800, 14, 150)
    finally:
        _close(window, qapp, guard)


@pytest.mark.parity("R3-177", "R3-180", "R3-181")
def test_the_form_menu_order_and_a_missing_print_support(
    tmp_path: Path, qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    window, kb, guard = _session(tmp_path, qapp, _FORM)
    try:
        form = window.findChild(QMenu, "formBuilder.menu")
        form.aboutToShow.emit()

        def titles() -> List[str]:
            return [a.text().split("\t")[0] for a in form.actions() if a.isVisible() and not a.isSeparator()]

        shown = titles()
        order = ["Preview", "Preview options", "View Python code", "View XML"]
        assert [t for t in shown if t in order] == order
        later = [t for t in shown if t in ("Save image…", "Print…", "Create window class…")]
        assert later == ["Save image…", "Print…", "Create window class…"]
        preview = next(a for a in form.actions() if a.text().startswith("Preview\t"))
        assert preview.text().endswith("Ctrl+Shift+R") and preview.isEnabled()
        code = next(a for a in form.actions() if a.text().startswith("View Python code"))
        assert code.text().endswith("Ctrl+K, C")
        monkeypatch.setattr(image_export, "print_available", lambda: False)
        form.aboutToShow.emit()
        assert "Print…" not in titles() and "Save image…" in titles()
    finally:
        _close(window, qapp, guard)


@pytest.mark.parity("R3-177", "R3-178", "R3-180")
def test_a_screen_change_reaches_the_open_window_and_save_image_takes_its_picture(
    tmp_path: Path, qapp: QApplication
) -> None:
    window, kb, guard = _session(tmp_path, qapp, _FORM)
    pool = _real_pool()
    try:
        surface = kb.surface
        control = surface.preview_control
        notices = surface.own_class_preview
        surface.preview_form()
        assert _pump_until(qapp, lambda: notices.last_response is not None)
        assert notices.last_response.ok, notices.last_response.detail
        assert notices.last_response.result["title"] == "Preview · customer.ui"
        spawned = len(pool.spawn_monotonic)
        # A pick while the window is open goes to the warm child: same process, new title, no new load.
        profile = control.profiles[1]
        control.set_screen(profile.name)
        assert _pump_until(qapp, lambda: control.last_look.get("title", "").endswith("Small screen"))
        assert len(pool.spawn_monotonic) == spawned
        # A 150% screen: the picture of the open window is 150% of the window, not the canvas page.
        control.add_profile(clean_profile("Tablet", 1280, 800, "", 0, 150))
        assert _pump_until(qapp, lambda: control.last_look.get("title", "").endswith("Tablet"))
        width, height = control.last_look["size"]
        target = tmp_path / "preview.png"
        image_export.write_image(surface, str(target))
        assert _pump_until(qapp, target.exists, 10.0)
        picture = QImage(str(target))
        assert (picture.width(), picture.height()) == (int(width * 1.5), int(height * 1.5))
        assert "Saved preview.png." in surface._command_toast._text.text()
    finally:
        PreviewPool.reset_shared()
        _close(window, qapp, guard)


@pytest.mark.parity("R3-180")
def test_print_paints_the_picture_centred_on_one_pdf_page(tmp_path: Path, qapp: QApplication) -> None:
    from app.qt.QtGui import QPageSize
    from app.qt.QtPrintSupport import QPrinter

    window, kb, guard = _session(tmp_path, qapp, _FORM)
    try:
        image = image_export.canvas_image(kb.surface)
        assert image is not None and not image.isNull()
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        out = tmp_path / "form.pdf"
        printer.setOutputFileName(str(out))
        image_export.paint_page(image, printer)
        data = out.read_bytes()
        assert data.startswith(b"%PDF") and data.count(b"/Type /Page\n") + data.count(b"/Type /Page ") >= 1
        assert not kb.session.log.can_undo(), "printing never changes the form"
    finally:
        _close(window, qapp, guard)


@pytest.mark.parity("R3-177")
def test_request_preview_goes_through_the_own_class_notice_with_the_chosen_screen(
    tmp_path: Path, qapp: QApplication
) -> None:
    own = _FORM.replace('<widget class="QLabel" name="nameLabel">', '<widget class="TillLabel" name="nameLabel">').replace(
        " <resources/>", ' <customwidgets>\n  <customwidget><class>TillLabel</class><extends>QLabel</extends>'
        "<header>widgets.till_label.h</header></customwidget>\n </customwidgets>\n <resources/>"
    )
    window, kb, guard = _session(tmp_path, qapp, own)
    try:
        surface = kb.surface
        sent: List[object] = []

        class _Pool:
            def subscribe(self, view_id, listener):  # noqa: ANN001, ANN201
                return lambda: None

            def request(self, message, callback):  # noqa: ANN001, ANN201
                sent.append(message)
                return message.request_id

        surface.own_class_preview._pool = _Pool()
        surface.request_preview(str(kb.path))
        assert len(sent) == 1
        assert sent[0].appearance.title == "Preview · customer.ui"
        assert sent[0].promoted and sent[0].promoted[0].class_name == "TillLabel"
    finally:
        _close(window, qapp, guard)


@pytest.mark.parity("R3-181")
def test_the_code_split_follows_the_form_and_the_selection(tmp_path: Path, qapp: QApplication) -> None:
    window, kb, guard = _session(tmp_path, qapp, _FORM)
    try:
        surface = kb.surface
        workbench = surface._workbench
        view = workbench.code_view
        # Too narrow: refused with the spec's sentence, nothing opens.
        assert not view.open()
        assert surface._gesture_sentence == "Make the window wider to see the code beside the form."
        assert workbench.beside_canvas_key() == ""
        window.resize(1900, 900)
        kb.pump()
        assert view.open() and workbench.beside_canvas_key() == "code"
        panel = view.panel
        assert "class Ui_Customer" in panel.text() and panel.editor.isReadOnly()
        assert panel._title.text() == "ui_customer.py · as it will be saved"
        assert not panel._open.isVisibleTo(panel), "[Open file] waits for a saved form"
        # An unsaved edit shows within the 300 ms pause.
        node = kb.session.document.by_name("saveButton")[0]
        kb.session.selection.set((node,), source=SelectionSource.OUTLINE)
        kb.session.log.execute(Rename(node, "okButton"))
        assert _pump_until(qapp, lambda: "self.okButton = QPushButton" in panel.text(), 3.0)
        assert "saveButton" not in panel.text()
        marked = panel.marked_lines()
        assert marked and all("okButton" in panel.editor.document().findBlockByNumber(n).text() for n in marked)
        # A click on a code line that names a widget selects it.
        line = view._index.first_line("nameEdit")
        block = panel.editor.document().findBlockByNumber(line)
        cursor = panel.editor.textCursor()
        cursor.setPosition(block.position() + 4)
        panel.editor.setFocus()
        panel.editor.setTextCursor(cursor)
        kb.pump()
        assert kb.selected() == ("nameEdit",)
        # Esc inside the split closes it and focus returns to the canvas.
        QTest.keyClick(panel.editor, _key("Key_Escape"))
        kb.pump()
        assert workbench.beside_canvas_key() == ""
        assert kb.focus_in("formBuilder.canvas")
        assert kb.text().count("okButton") >= 1
    finally:
        _close(window, qapp, guard)


@pytest.mark.parity("R3-181")
def test_a_form_that_cannot_be_generated_shows_the_reason_instead_of_code(tmp_path: Path, qapp: QApplication) -> None:
    bad = _FORM.replace('name="nameEdit"', 'name="name edit"')
    window, kb, guard = _session(tmp_path, qapp, bad)
    try:
        window.resize(1900, 900)
        kb.pump()
        view = kb.surface._workbench.code_view
        assert view.open()
        panel = view.panel
        assert panel.error_text(), "the body says why there is no code"
        assert panel.editor.toPlainText() == panel.error_text()
        assert "class Ui_" not in panel.editor.toPlainText()
    finally:
        _close(window, qapp, guard)
