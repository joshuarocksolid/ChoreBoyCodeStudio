"""Form tab chrome: history, save, recovery, breakpoints, theme."""

from __future__ import annotations

import os

import logging
from pathlib import Path

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.editors.editor_manager import EditorManager  # noqa: E402
from app.features.form_builder.engine.codegen.api import generate_form_module  # noqa: E402
from app.features.form_builder.engine.project.create import create_form  # noqa: E402
from app.features.form_builder.engine.project.forms import classify_form  # noqa: E402
from app.features.form_builder.engine.project.fs import OsFileSystem  # noqa: E402
from app.features.form_builder.engine.ui4.writer import write_ui  # noqa: E402
from app.features.form_builder.integration.content_source import open_document_log  # noqa: E402
from app.features.form_builder.integration.provider import FormTabProvider  # noqa: E402
from app.features.form_builder.integration.surface import FormSurface  # noqa: E402
from app.persistence.autosave_store import DraftEntry  # noqa: E402
from app.persistence.local_history_store import LocalHistoryStore  # noqa: E402
from app.qt.QtCore import QRect  # noqa: E402
from app.qt.QtGui import QPalette  # noqa: E402
from app.features.form_builder.integration.workbench import FormWorkbench  # noqa: E402
from app.qt.QtWidgets import (  # noqa: E402
    QApplication,
    QFrame,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QShortcut,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QWidget,
)
from app.shell.document_safety import dirty_buffer_snapshots  # noqa: E402
from app.shell.local_history_workflow import LocalHistoryWorkflow  # noqa: E402
from app.shell.tab_content_providers import TabSurfaceRequest  # noqa: E402
from app.shell.theme_tokens import tokens_from_palette  # noqa: E402
from tests.support.local_history_editor_host_stub import LocalHistoryEditorHostStub  # noqa: E402

pytestmark = pytest.mark.unit

_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QPushButton" name="okButton">
     <property name="text">
      <string>OK</string>
     </property>
    </widget>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""

_BAD = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="class"/>
 <resources/>
 <connections/>
</ui>
"""

_SIZES = ((1280, 800), (1080, 600), (800, 600), (700, 500), (1080, 420))


class _Editor:
    def __init__(self, parent: QWidget) -> None:
        from app.qt.QtWidgets import QPlainTextEdit

        self._widget = QPlainTextEdit(parent)

    def apply_theme(self, _tokens: object) -> None:
        return None

    def go_to_line(self, line_number: int) -> None:
        del line_number


def _request(parent: QWidget, text: str, path: str, project_root: str | None = None) -> TabSurfaceRequest:
    from app.qt.QtWidgets import QPlainTextEdit

    app = QApplication.instance()
    assert app is not None
    created: list[QPlainTextEdit] = []

    def create_source_editor() -> QPlainTextEdit:
        editor = QPlainTextEdit(parent)
        editor.setObjectName("shell.editorTabs.textEditor")
        created.append(editor)
        return editor

    return TabSurfaceRequest(
        file_path=path,
        initial_text=text,
        parent=parent,
        theme=tokens_from_palette(app.palette(), force_mode="light"),
        create_source_editor=create_source_editor,  # type: ignore[arg-type]
        open_linked_file=lambda _linked: None,
        project_root=project_root,
    )


def _open(parent: QWidget, text: str, path: Path, project_root: str | None = None) -> FormSurface:
    path.write_text(text, encoding="utf-8")
    return FormTabProvider().create_surface(_request(parent, text, str(path), project_root))


def _window_color(widget: QWidget) -> tuple[int, int, int, int]:
    role = getattr(getattr(QPalette, "ColorRole", QPalette), "Window")
    color = widget.palette().color(role)
    return color.getRgb()


def _toolbar_problems(toolbar: QWidget) -> list[str]:
    kids = [child for child in toolbar.children() if isinstance(child, QWidget) and child.isVisible()]
    problems: list[str] = []
    bounds = toolbar.rect()
    for index, child in enumerate(kids):
        rect = child.geometry()
        if not bounds.contains(rect) and not bounds.intersected(rect).contains(QRect(rect.x(), rect.y(), max(1, rect.width() - 1), max(1, rect.height() - 1))):
            if rect.right() > bounds.right() + 1 or rect.bottom() > bounds.bottom() + 1 or rect.left() < -1:
                problems.append("clipped %s" % child.objectName())
        for other in kids[index + 1 :]:
            overlap = rect.intersected(other.geometry())
            if overlap.width() > 2 and overlap.height() > 2:
                problems.append("overlap %s %s" % (child.objectName(), other.objectName()))
    return problems


def test_new_open_save_and_close_prompt(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    del qapp
    created = create_form(str(tmp_path), "invoice", OsFileSystem())
    assert created.scope is not None
    ui_path = Path(created.scope.ui_path)
    before = ui_path.read_bytes()
    parent = QWidget()
    surface = _open(parent, ui_path.read_text(encoding="utf-8"), ui_path, str(tmp_path))
    assert surface.content_source().serialize_count == 0
    manager = EditorManager()
    tab = manager.open_file(str(ui_path)).tab
    tab.content_source = surface.content_source()

    manager.save_tab(str(ui_path))
    assert ui_path.read_bytes() == before

    toggle = surface.findChild(QToolButton, "formBuilder.viewXml")
    assert toggle is not None
    toggle.setChecked(True)
    editor = surface.source_editor()
    assert editor is not None
    editor.setPlainText(editor.toPlainText().replace(">Invoice<", ">Edited<", 1))
    toggle.setChecked(False)
    assert tab.is_dirty is True
    snapshots = dirty_buffer_snapshots([tab])
    assert [item.file_path for item in snapshots] == [str(ui_path)]

    surface.release()
    with pytest.raises(RuntimeError):
        surface.undo()


def test_outline_selection_shows_on_the_inspector(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    del qapp
    canonical = write_ui(open_document_log(_FORM).document).text
    surface = _open(QWidget(), canonical, tmp_path / "invoice.ui")
    from app.qt.QtWidgets import QTreeWidget

    tree = surface.findChild(QTreeWidget, "formBuilder.structure")
    assert tree is not None

    def walk(item):  # type: ignore[no-untyped-def]
        if "okButton" in item.text(0):
            return item
        for index in range(item.childCount()):
            found = walk(item.child(index))
            if found is not None:
                return found
        return None

    chosen = None
    for index in range(tree.topLevelItemCount()):
        chosen = walk(tree.topLevelItem(index))
        if chosen is not None:
            break
    assert chosen is not None
    tree.setCurrentItem(chosen)
    name = surface.findChild(QLineEdit, "formBuilder.inspectorName")
    kind = surface.findChild(QLabel, "formBuilder.inspectorClass")
    assert name is not None and kind is not None
    assert name.text() == "okButton"
    assert "QPushButton" in kind.text()
    surface.release()


def test_two_tabs_do_not_share_history(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    del qapp
    canonical = write_ui(open_document_log(_FORM).document).text
    first = _open(QWidget(), canonical, tmp_path / "one.ui")
    second = _open(QWidget(), canonical, tmp_path / "two.ui")
    toggle = first.findChild(QToolButton, "formBuilder.viewXml")
    assert toggle is not None
    toggle.setChecked(True)
    editor = first.source_editor()
    assert editor is not None
    editor.setPlainText(editor.toPlainText().replace(">OK<", ">Save<"))
    toggle.setChecked(False)

    assert first.undo() is True
    assert second.undo() is False
    first.release()
    second.release()


def test_edit_undo_uses_the_command_name(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    from app.qt.QtWidgets import QAction

    class _Registry:
        def __init__(self, parent: QWidget) -> None:
            self.undo = QAction("Undo", parent)
            self.redo = QAction("Redo", parent)

        def action(self, action_id: str) -> QAction | None:
            if action_id.endswith(".undo"):
                return self.undo
            if action_id.endswith(".redo"):
                return self.redo
            return None

    class _Window(QWidget):
        def __init__(self) -> None:
            super().__init__()
            self._registry = _Registry(self)

        def menu_registry(self) -> _Registry:
            return self._registry

    canonical = write_ui(open_document_log(_FORM).document).text
    window = _Window()
    surface = _open(window, canonical, tmp_path / "invoice.ui")
    window.resize(1280, 800)
    window.show()
    qapp.processEvents()
    toggle = surface.findChild(QToolButton, "formBuilder.viewXml")
    assert toggle is not None
    toggle.setChecked(True)
    editor = surface.source_editor()
    assert editor is not None
    editor.setPlainText(editor.toPlainText().replace(">OK<", ">Save<"))
    toggle.setChecked(False)
    qapp.processEvents()
    tree = surface.findChild(QTreeWidget, "formBuilder.structure")
    assert tree is not None
    qapp.setActiveWindow(window)
    tree.setFocus()
    qapp.processEvents()

    assert window._registry.undo.text() == "Undo XML edits"
    assert window._registry.undo.isEnabled() is True
    window._registry.undo.trigger()
    assert ">OK<" in surface.content_source().current_text()
    surface.release()
    window.close()


def test_save_writes_generated_bytes_and_a_refusal_still_saves(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    del qapp
    forms = tmp_path / "forms"
    forms.mkdir()
    ui_path = forms / "invoice.ui"
    parent = QWidget()
    surface = _open(parent, _FORM, ui_path, str(tmp_path))
    manager = EditorManager()
    tab = manager.open_file(str(ui_path)).tab
    tab.content_source = surface.content_source()
    saved = manager.save_tab(str(ui_path))
    scope = classify_form(str(ui_path), project_root=str(tmp_path))
    expected = generate_form_module(
        surface.content_source().log.document,
        scope=scope,
        source_bytes=ui_path.read_bytes(),
    ).text
    assert expected is not None
    assert Path(scope.generated_path or "").read_bytes() == expected.encode("utf-8")
    assert saved.is_dirty is False

    bad_path = forms / "broken.ui"
    bad_parent = QWidget()
    bad = _open(bad_parent, _BAD, bad_path, str(tmp_path))
    bad_tab = manager.open_file(str(bad_path)).tab
    bad_tab.content_source = bad.content_source()
    manager.save_tab(str(bad_path))
    assert bad_path.read_bytes() == _BAD.encode("utf-8")
    assert not (forms / "ui_broken.py").exists()
    assert bad_tab.is_dirty is False
    label = bad.findChild(QLabel, "formBuilder.saveState")
    assert label is not None
    assert "not written" in label.text()
    surface.release()
    bad.release()


def test_external_change_choices_and_invalid_xml(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    del qapp
    canonical = write_ui(open_document_log(_FORM).document).text
    parent = QWidget()
    surface = _open(parent, canonical, tmp_path / "invoice.ui")
    calls: list[str] = []
    surface.offer_external_change(
        "invoice.ui",
        lambda: calls.append("reload"),
        lambda: calls.append("keep"),
        lambda: calls.append("compare"),
    )
    notice = surface.findChild(QLabel, "formBuilder.noticeText")
    assert notice is not None and notice.isVisibleTo(surface)
    assert notice.text() == "invoice.ui changed on disk."
    buttons = [button.text() for button in surface.findChildren(QPushButton, "formBuilder.noticeButton")]
    assert buttons == ["Reload from disk", "Keep mine", "Compare…"]
    surface.findChildren(QPushButton, "formBuilder.noticeButton")[2].click()
    assert calls == ["compare"]
    assert notice.isVisibleTo(surface) is True
    surface.findChildren(QPushButton, "formBuilder.noticeButton")[1].click()
    assert calls == ["compare", "keep"]
    assert notice.isVisibleTo(surface) is False

    toggle = surface.findChild(QToolButton, "formBuilder.viewXml")
    assert toggle is not None
    toggle.setChecked(True)
    assert surface.external_change_needs_bar("<not-xml") is True
    surface.restore_text("<not-xml", "external_reload")
    banner = surface.findChild(QLabel, "formBuilder.xmlBannerText")
    editor = surface.source_editor()
    assert banner is not None and editor is not None
    assert editor.toPlainText() == "<not-xml"
    assert banner.isVisibleTo(surface) is True
    assert surface.content_source().mode == "xml"
    surface.release()


def test_recovered_draft_can_be_discarded(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    canonical = write_ui(open_document_log(_FORM).document).text
    project = tmp_path / "project"
    project.mkdir()
    ui_path = project / "invoice.ui"
    parent = QWidget()
    surface = _open(parent, canonical, ui_path)
    drafted = canonical.replace(">OK<", ">Later<")
    manager = EditorManager()
    tab = manager.open_file(str(ui_path)).tab
    tab.content_source = surface.content_source()

    class _Store:
        def __init__(self) -> None:
            self.entry = DraftEntry(file_path=str(ui_path), content=drafted, saved_at="2026-03-24T14:02:00")
            self.deleted = False

        def load_draft(self, file_path: str, **_kwargs: object) -> DraftEntry | None:
            del file_path
            return self.entry

        def delete_draft(self, file_path: str, **_kwargs: object) -> None:
            del file_path
            self.deleted = True
            self.entry = None  # type: ignore[assignment]

        def save_draft(self, file_path: str, content: str, **_kwargs: object) -> None:
            del file_path, content

    store = _Store()
    host = LocalHistoryEditorHostStub(parent=parent)
    host.surface_for_path = lambda _path: surface  # type: ignore[attr-defined]
    workflow = LocalHistoryWorkflow(
        host=host,
        local_history_store=LocalHistoryStore(state_root=tmp_path / "state"),
        autosave_store=store,  # type: ignore[arg-type]
        editor_manager=manager,
        logger=logging.getLogger("test.form_draft"),
    )
    workflow.maybe_restore_draft(tab, None)  # type: ignore[arg-type]
    qapp.processEvents()
    notice = surface.findChild(QLabel, "formBuilder.noticeText")
    assert notice is not None
    assert notice.text() == "Recovered unsaved changes from 14:02."
    assert ">Later<" in surface.content_source().current_text()
    toggle = surface.findChild(QToolButton, "formBuilder.viewXml")
    assert toggle is not None
    toggle.setChecked(True)
    editor = surface.source_editor()
    assert editor is not None
    editor.setPlainText(editor.toPlainText().replace(">Later<", ">Edited<"))
    toggle.setChecked(False)
    assert ">Edited<" in surface.content_source().current_text()
    discard = [button for button in surface.findChildren(QPushButton, "formBuilder.noticeButton") if button.text() == "Discard"]
    assert discard
    discard[0].click()
    assert ">OK<" in surface.content_source().current_text()
    assert ">Later<" not in surface.content_source().current_text()
    assert ">Edited<" not in surface.content_source().current_text()
    assert store.deleted is True
    surface.release()


def _wide_host(state_root: Path) -> QWidget:
    from app.qt.QtWidgets import QVBoxLayout

    host = QWidget()
    host._state_root = str(state_root)  # type: ignore[attr-defined]
    layout = QVBoxLayout(host)
    layout.setContentsMargins(0, 0, 0, 0)
    host.resize(1280, 800)
    return host


def test_pane_widths_persist(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    canonical = write_ui(open_document_log(_FORM).document).text
    state = tmp_path / "state"
    host = _wide_host(state)
    surface = _open(host, canonical, tmp_path / "invoice.ui")
    host.layout().addWidget(surface)  # type: ignore[union-attr]
    host.show()
    qapp.processEvents()
    assert surface.width() >= 1180
    from app.qt.QtWidgets import QSplitter

    splitter = surface.findChild(QSplitter, "formBuilder.splitter")
    assert splitter is not None
    splitter.setSizes([200, max(0, splitter.width() - 480), 280])
    left, _canvas, inspector = splitter.sizes()
    splitter.splitterMoved.emit(left, 1)
    surface.release()

    host2 = _wide_host(state)
    again = _open(host2, canonical, tmp_path / "invoice.ui")
    host2.layout().addWidget(again)  # type: ignore[union-attr]
    host2.show()
    qapp.processEvents()
    assert again.layout_plan().density == "wide"
    assert again.layout_plan().left_width == left
    assert again.layout_plan().inspector_width == inspector
    again.release()
    host.close()
    host2.close()


def test_breakpoint_layouts_do_not_clip_the_toolbar(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    canonical = write_ui(open_document_log(_FORM).document).text
    parent = QWidget()
    surface = _open(parent, canonical, tmp_path / "invoice.ui")
    surface.show()
    for width, height in _SIZES:
        surface.resize(width, height)
        qapp.processEvents()
        toolbar = surface.findChild(QWidget, "formBuilder.toolbar")
        assert toolbar is not None
        assert toolbar.height() == 36
        assert _toolbar_problems(toolbar) == []
        assert surface.layout_plan().density in ("wide", "compact", "rail", "drawer")
    surface.release()


def test_theme_changes_chrome_and_not_the_page(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    canonical = write_ui(open_document_log(_FORM).document).text
    parent = QWidget()
    surface = _open(parent, canonical, tmp_path / "invoice.ui")
    page = surface.page_widget()
    assert page is not None
    light = tokens_from_palette(qapp.palette(), force_mode="light")
    surface.apply_theme(light)
    runtime = _window_color(page)
    light_sheet = surface.findChild(QWidget, "formBuilder.toolbar").styleSheet()  # type: ignore[union-attr]
    chrome_marks = ("formBuilder", "#E9EBEF", "#16191D", "#D3D8DF", "#262B31")
    for mode in ("light", "dark", "high_contrast_light", "high_contrast_dark"):
        surface.apply_theme(tokens_from_palette(qapp.palette(), force_mode=mode))
        qapp.processEvents()
        assert _window_color(page) == runtime
        blob = _widget_stylesheets(page).lower()
        for mark in chrome_marks:
            assert mark.lower() not in blob
    assert surface.findChild(QWidget, "formBuilder.toolbar").styleSheet() != light_sheet  # type: ignore[union-attr]
    surface.release()


def test_theme_screenshots(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    corpus = (
        Path(__file__).resolve().parents[4]
        / "tests/form_builder/corpus/qt_examples/qtbase/examples/sql/sqlbrowser/qsqlconnectiondialog.ui"
    )
    text = corpus.read_text(encoding="utf-8")
    out = Path(os.environ.get("CBCS_FB_SCREENSHOT_DIR") or tmp_path)
    out.mkdir(parents=True, exist_ok=True)
    host = QWidget()
    surface = _open(host, text, tmp_path / "connection.ui")
    host.show()
    surface.show()
    _select_outline_child(surface)
    qapp.processEvents()
    for mode in ("light", "dark", "high_contrast_light", "high_contrast_dark"):
        surface.apply_theme(tokens_from_palette(qapp.palette(), force_mode=mode))
        for width, height in ((1280, 800), (1080, 600), (800, 600)):
            host.resize(width, height)
            surface.resize(width, height)
            qapp.processEvents()
            if width <= 800:
                bench = surface.findChild(FormWorkbench, "formBuilder.workbench")
                assert bench is not None
                bench.open_left()
                qapp.processEvents()
                drawer = surface.findChild(QFrame, "formBuilder.drawer")
                assert drawer is not None and drawer.width() >= 200, drawer.geometry()
            tree = surface.findChild(QTreeWidget, "formBuilder.structure")
            assert tree is not None and tree.isVisibleTo(surface)
            _select_outline_child(surface)
            qapp.processEvents()
            assert "·" in surface.editor_status_sentence()
            image = surface.grab()
            assert (image.width(), image.height()) == (width, height)
            image.save(str(out / ("form-tab-%s-%dx%d.png" % (mode, width, height))))
    surface.release()
    host.close()


def _widget_stylesheets(widget: QWidget) -> str:
    sheets = [widget.styleSheet()]
    for child in widget.findChildren(QWidget):
        sheets.append(child.styleSheet())
    return "\n".join(sheets)


def _select_outline_child(surface: QWidget) -> None:
    tree = surface.findChild(QTreeWidget, "formBuilder.structure")
    if tree is None:
        return

    def walk(item: QTreeWidgetItem) -> QTreeWidgetItem | None:
        label = item.text(0)
        if item.parent() is not None and "Layout" not in label and "Spacer" not in label:
            return item
        for index in range(item.childCount()):
            child = item.child(index)
            if child is None:
                continue
            found = walk(child)
            if found is not None:
                return found
        return None

    top = tree.topLevelItem(0)
    target = None if top is None else walk(top)
    if target is not None:
        tree.setCurrentItem(target)


def test_unknown_xml_offers_the_problems_link(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    text = _FORM.replace("</widget>", "<zzunk n=\"kept\"/></widget>", 1)
    parent = QWidget()
    surface = _open(parent, text, tmp_path / "invoice.ui")
    qapp.processEvents()
    body = surface.findChild(QLabel, "formBuilder.inspectorProblems")
    assert body is not None
    assert "Show in Problems" in body.text()
    assert "problem" in body.text()
    surface.release()


def test_reveal_selects_the_named_widget(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    parent = QWidget()
    surface = _open(parent, _FORM, tmp_path / "invoice.ui")
    assert surface.reveal(1, {"fb_object": "okButton"})
    sentence = surface.editor_status_sentence()
    assert sentence.startswith("okButton · Push button")
    surface.release()


def _esc_enabled(surface: QWidget) -> bool:
    for shortcut in surface.findChildren(QShortcut):
        if shortcut.key().toString() == "Esc":
            return bool(shortcut.isEnabled())
    return False


def _edit_xml(surface: FormSurface, old: str, new: str) -> None:
    toggle = surface.findChild(QToolButton, "formBuilder.viewXml")
    assert toggle is not None
    toggle.setChecked(True)
    editor = surface.source_editor()
    assert editor is not None
    editor.setPlainText(editor.toPlainText().replace(old, new))
    toggle.setChecked(False)


def test_shell_undo_follows_the_focused_form(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    from app.qt.QtWidgets import QAction, QHBoxLayout

    class _Registry:
        def __init__(self, parent: QWidget) -> None:
            self.undo = QAction("Undo", parent)
            self.redo = QAction("Redo", parent)

        def action(self, action_id: str) -> QAction | None:
            if action_id.endswith(".undo"):
                return self.undo
            if action_id.endswith(".redo"):
                return self.redo
            return None

    class _Window(QWidget):
        def __init__(self) -> None:
            super().__init__()
            self._registry = _Registry(self)

        def menu_registry(self) -> _Registry:
            return self._registry

    canonical = write_ui(open_document_log(_FORM).document).text
    window = _Window()
    layout = QHBoxLayout(window)
    layout.setContentsMargins(0, 0, 0, 0)
    first = _open(window, canonical, tmp_path / "one.ui")
    second = _open(window, canonical, tmp_path / "two.ui")
    layout.addWidget(first)
    layout.addWidget(second)
    window.resize(1600, 800)
    window.show()
    qapp.processEvents()
    _edit_xml(first, ">OK<", ">Aaa<")
    _edit_xml(second, ">OK<", ">Bbb<")
    second.hide()
    qapp.processEvents()
    second.show()
    qapp.processEvents()
    tree = first.findChild(QTreeWidget, "formBuilder.structure")
    assert tree is not None
    qapp.setActiveWindow(window)
    tree.setFocus()
    qapp.processEvents()

    assert window._registry.undo.isEnabled() is True
    window._registry.undo.trigger()
    assert ">OK<" in first.content_source().current_text()
    assert ">Aaa<" not in first.content_source().current_text()
    assert ">Bbb<" in second.content_source().current_text()
    first.release()
    second.release()
    window.close()


def test_keep_recovered_draft_survives_a_crash(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    from app.persistence.autosave_store import AutosaveStore

    canonical = write_ui(open_document_log(_FORM).document).text
    project = tmp_path / "project"
    project.mkdir()
    ui_path = (project / "invoice.ui").resolve()
    parent = QWidget()
    surface = _open(parent, canonical, ui_path)
    drafted = canonical.replace(">OK<", ">Later<")
    store = AutosaveStore(state_root=tmp_path / "state")
    store.save_draft(str(ui_path), drafted)
    manager = EditorManager()
    tab = manager.open_file(str(ui_path)).tab
    tab.content_source = surface.content_source()
    host = LocalHistoryEditorHostStub(parent=parent)
    host.surface_for_path = lambda _path: surface  # type: ignore[attr-defined]
    workflow = LocalHistoryWorkflow(
        host=host,
        local_history_store=LocalHistoryStore(state_root=tmp_path / "history"),
        autosave_store=store,
        editor_manager=manager,
        logger=logging.getLogger("test.form_keep"),
    )
    workflow.maybe_restore_draft(tab, None)  # type: ignore[arg-type]
    qapp.processEvents()
    assert ">Later<" in surface.content_source().current_text()
    workflow.note_source_changed(tab.file_path)
    workflow.flush_pending_autosaves()
    keep = [button for button in surface.findChildren(QPushButton, "formBuilder.noticeButton") if button.text() == "Keep recovered"]
    assert keep
    keep[0].click()
    workflow.note_source_changed(tab.file_path)
    workflow.flush_pending_autosaves()
    assert store.load_draft(str(ui_path)) is not None
    surface.release()

    parent2 = QWidget()
    again = _open(parent2, canonical, ui_path)
    manager2 = EditorManager()
    tab2 = manager2.open_file(str(ui_path)).tab
    tab2.content_source = again.content_source()
    host2 = LocalHistoryEditorHostStub(parent=parent2)
    host2.surface_for_path = lambda _path: again  # type: ignore[attr-defined]
    crashed = LocalHistoryWorkflow(
        host=host2,
        local_history_store=LocalHistoryStore(state_root=tmp_path / "history"),
        autosave_store=store,
        editor_manager=manager2,
        logger=logging.getLogger("test.form_keep_again"),
    )
    crashed.maybe_restore_draft(tab2, None)  # type: ignore[arg-type]
    qapp.processEvents()
    assert ">Later<" in again.content_source().current_text()
    notice = again.findChild(QLabel, "formBuilder.noticeText")
    assert notice is not None and notice.isVisibleTo(again)
    again.release()


def test_stale_recovered_draft_is_dropped(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    from app.persistence.autosave_store import AutosaveStore

    del qapp
    canonical = write_ui(open_document_log(_FORM).document).text
    ui_path = (tmp_path / "invoice.ui").resolve()
    parent = QWidget()
    surface = _open(parent, canonical, ui_path)
    store = AutosaveStore(state_root=tmp_path / "state")
    store.save_draft(str(ui_path), surface.content_source().current_text())
    manager = EditorManager()
    tab = manager.open_file(str(ui_path)).tab
    tab.content_source = surface.content_source()
    host = LocalHistoryEditorHostStub(parent=parent)
    host.surface_for_path = lambda _path: surface  # type: ignore[attr-defined]
    workflow = LocalHistoryWorkflow(
        host=host,
        local_history_store=LocalHistoryStore(state_root=tmp_path / "history"),
        autosave_store=store,
        editor_manager=manager,
        logger=logging.getLogger("test.form_stale"),
    )
    workflow.maybe_restore_draft(tab, None)  # type: ignore[arg-type]
    notice = surface.findChild(QLabel, "formBuilder.noticeText")
    assert notice is not None
    assert notice.isVisibleTo(surface) is False
    assert store.load_draft(str(ui_path)) is None
    assert ">OK<" in surface.content_source().current_text()
    surface.release()


def test_xml_edit_keeps_crlf_on_disk(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    del qapp
    canonical = write_ui(open_document_log(_FORM).document).text
    crlf = canonical.replace("\n", "\r\n")
    path = tmp_path / "invoice.ui"
    parent = QWidget()
    surface = _open(parent, crlf, path)
    manager = EditorManager()
    tab = manager.open_file(str(path)).tab
    tab.content_source = surface.content_source()
    _edit_xml(surface, ">OK<", ">Save<")
    manager.save_tab(str(path))
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    assert ">Save<" in text
    assert "\r\n" in text
    assert "\n" not in text.replace("\r\n", "")
    surface.release()


def test_reload_does_not_write_generated_python(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    from app.shell.editor_sync_workflow import EditorDiskSyncSource, EditorSyncWorkflow

    del qapp
    forms = tmp_path / "forms"
    forms.mkdir()
    ui_path = forms / "invoice.ui"
    parent = QWidget()
    surface = _open(parent, _FORM, ui_path, str(tmp_path))
    manager = EditorManager()
    tab = manager.open_file(str(ui_path)).tab
    tab.content_source = surface.content_source()

    class _Host:
        def editor_widget_for_path(self, _file_path: str) -> None:
            return None

        def advance_buffer_revision(self, _file_path: str) -> int:
            return 1

        def apply_detected_indentation(self, _file_path: str, _editor: object, _text: str) -> None:
            return None

        def tab_index_for_path(self, _file_path: str) -> int:
            return -1

        def refresh_tab_presentation(self, _file_path: str) -> None:
            return None

        def has_editor_tabs_widget(self) -> bool:
            return False

        def surface_for_path(self, _file_path: str) -> FormSurface:
            return surface

    sync = EditorSyncWorkflow(editor_manager=manager, host=_Host())  # type: ignore[arg-type]
    applied = sync.apply_disk_content(
        str(ui_path),
        surface.content_source().current_text(),
        source=EditorDiskSyncSource.EXTERNAL_RELOAD,
    )
    assert applied is True
    assert not (forms / "ui_invoice.py").exists()
    label = surface.findChild(QLabel, "formBuilder.saveState")
    assert label is not None
    assert "Saved" not in label.text()
    surface.release()


def test_generation_failure_names_the_file(qapp, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:  # type: ignore[no-untyped-def]
    del qapp
    forms = tmp_path / "forms"
    forms.mkdir()
    ui_path = forms / "invoice.ui"
    parent = QWidget()
    surface = _open(parent, _FORM, ui_path, str(tmp_path))
    manager = EditorManager()
    tab = manager.open_file(str(ui_path)).tab
    tab.content_source = surface.content_source()

    def boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("disk full")

    monkeypatch.setattr("app.features.form_builder.integration.save_pipeline.write_generated", boom)
    with caplog.at_level(logging.ERROR, logger="app.features.form_builder.integration.save_pipeline"):
        manager.save_tab(str(ui_path))
    notice = surface.content_source().save_notice
    assert notice.diagnostics
    assert notice.diagnostics[0].code == "FB509"
    assert "ui_invoice.py" in notice.diagnostics[0].message
    label = surface.findChild(QLabel, "formBuilder.saveState")
    assert label is not None
    assert "ui_invoice.py" in label.text()
    assert any("ui_invoice.py" in record.getMessage() for record in caplog.records)
    surface.release()


def test_outline_rail_opens_a_visible_drawer(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    canonical = write_ui(open_document_log(_FORM).document).text
    host = QWidget()
    surface = _open(host, canonical, tmp_path / "invoice.ui")
    host.show()
    surface.show()
    host.resize(800, 600)
    surface.resize(800, 600)
    qapp.processEvents()
    assert (surface.width(), surface.height()) == (800, 600)
    outline = surface.findChild(QToolButton, "formBuilder.leftRail.outline")
    insert = surface.findChild(QToolButton, "formBuilder.leftRail.insert")
    assert outline is not None and insert is not None
    assert outline.accessibleName() == "Outline"
    assert insert.accessibleName() == "Insert"
    qapp.setActiveWindow(host)
    outline.click()
    qapp.processEvents()
    tree = surface.findChild(QTreeWidget, "formBuilder.structure")
    assert tree is not None
    assert tree.isVisibleTo(surface)
    assert tree.width() > 20 and tree.height() > 20
    drawer = surface.findChild(QFrame, "formBuilder.drawer")
    assert drawer is not None and drawer.width() >= 200, None if drawer is None else drawer.geometry()
    assert qapp.focusWidget() is tree
    assert _esc_enabled(surface) is True
    surface.release()
    host.close()


def test_insert_rail_opens_the_short_drawer(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    canonical = write_ui(open_document_log(_FORM).document).text
    host = QWidget()
    surface = _open(host, canonical, tmp_path / "invoice.ui")
    host.show()
    surface.show()
    host.resize(700, 500)
    surface.resize(700, 500)
    qapp.processEvents()
    assert (surface.width(), surface.height()) == (700, 500)
    insert = surface.findChild(QToolButton, "formBuilder.leftRail.insert")
    assert insert is not None
    qapp.setActiveWindow(host)
    insert.click()
    qapp.processEvents()
    body = surface.findChild(QListWidget, "formBuilder.insertBody")
    assert body is not None
    assert body.isVisibleTo(surface)
    assert body.width() > 20 and body.height() > 20
    assert qapp.focusWidget() is body
    assert _esc_enabled(surface) is True
    right = surface.findChild(QToolButton, "formBuilder.rightRail.properties")
    assert right is not None
    assert right.accessibleName() == "Properties"
    right.click()
    qapp.processEvents()
    search = surface.findChild(QLineEdit, "formBuilder.inspectorSearch")
    assert search is not None and search.isVisibleTo(surface)
    assert qapp.focusWidget() is search
    tree = surface.findChild(QTreeWidget, "formBuilder.structure")
    assert tree is not None

    def walk(item):  # type: ignore[no-untyped-def]
        if "okButton" in item.text(0):
            return item
        for index in range(item.childCount()):
            found = walk(item.child(index))
            if found is not None:
                return found
        return None

    chosen = None
    for index in range(tree.topLevelItemCount()):
        chosen = walk(tree.topLevelItem(index))
        if chosen is not None:
            break
    assert chosen is not None
    tree.setCurrentItem(chosen)
    kind = surface.findChild(QLabel, "formBuilder.inspectorClass")
    name = surface.findChild(QLineEdit, "formBuilder.inspectorName")
    assert kind is not None and name is not None
    assert "\n" not in kind.text()
    assert name.text() == "okButton"
    assert "QPushButton" in kind.text()
    surface.release()
    host.close()
